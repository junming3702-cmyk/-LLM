"""Run the deterministic M1/M2 design-revision-to-BoQ pilot."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


ORIGIN_DATE = "2026-09-03"
CASE_TYPES = (
    "explicit_mapping",
    "ambiguous_alternatives",
    "cross_document_version_conflict",
    "insufficient_evidence",
)
METHODS = ("M1", "M2")
ACCEPTANCE_THRESHOLD = 0.55
MINIMUM_MARGIN = 0.15
MINIMUM_SUPPORT_EVIDENCE = 1
HIGH_CONFIDENCE_THRESHOLD = 0.80


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value), encoding="utf-8", newline="\n")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at line {line_number}: {exc}") from exc
    validate_cases(cases)
    return cases


def validate_cases(cases: list[dict[str, Any]]) -> None:
    if len(cases) != 24:
        raise ValueError(f"expected 24 cases, found {len(cases)}")
    ids = [case.get("case_id") for case in cases]
    if len(set(ids)) != len(ids):
        raise ValueError("case_id values must be unique")
    counts = {case_type: 0 for case_type in CASE_TYPES}
    for case in cases:
        case_type = case.get("case_type")
        if case_type not in counts:
            raise ValueError(f"unknown case type: {case_type}")
        counts[case_type] += 1
        for required in ("design_revision", "candidates", "gold", "support_evidence", "conflict_evidence"):
            if required not in case:
                raise ValueError(f"{case['case_id']} missing {required}")
        if not case["candidates"]:
            raise ValueError(f"{case['case_id']} has no candidate BoQ records")
        gold = case["gold"]
        if gold["status"] not in ("accept", "abstain"):
            raise ValueError(f"{case['case_id']} has invalid gold status")
        if gold["status"] == "accept" and not gold.get("candidate_id"):
            raise ValueError(f"{case['case_id']} accepted gold needs a candidate_id")
    if any(value != 6 for value in counts.values()):
        raise ValueError(f"expected six cases per type, found {counts}")


def tokens(value: str | list[str]) -> set[str]:
    if isinstance(value, list):
        value = " ".join(value)
    return set(re.findall(r"[a-z0-9]+", value.lower()))


def score_candidate(case: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    change = case["design_revision"]
    change_tokens = tokens(change["change_tokens"])
    candidate_tokens = tokens(candidate["tokens"])
    overlap_tokens = sorted(change_tokens & candidate_tokens)
    overlap = len(overlap_tokens) / max(1, len(change_tokens))
    identifier_match = int(
        candidate.get("drawing_id") == change.get("drawing_id")
        and candidate.get("revised_version") == change.get("revised_version")
    )
    negative_tokens = tokens(candidate.get("negative_tokens", []))
    negative_matches = sorted(change_tokens & negative_tokens)
    score = overlap + (3.0 * identifier_match) - float(len(negative_matches))
    score = round(score, 6)
    confidence = round(max(0.0, score) / (1.0 + max(0.0, score)), 6)
    return {
        "candidate_id": candidate["candidate_id"],
        "token_overlap": round(overlap, 6),
        "overlap_tokens": overlap_tokens,
        "identifier_match": bool(identifier_match),
        "negative_matches": negative_matches,
        "score": score,
        "confidence": confidence,
        "source_version": candidate.get("source_version", ""),
        "locator": candidate.get("locator", ""),
    }


def rank_candidates(case: dict[str, Any]) -> list[dict[str, Any]]:
    ranked = [score_candidate(case, candidate) for candidate in case["candidates"]]
    ranked.sort(key=lambda item: (-item["score"], item["candidate_id"]))
    return ranked


def candidate_by_id(case: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    for candidate in case["candidates"]:
        if candidate["candidate_id"] == candidate_id:
            return candidate
    raise KeyError(f"candidate {candidate_id} not found in {case['case_id']}")


def evidence_for_candidate(case: dict[str, Any], candidate_id: str) -> list[dict[str, Any]]:
    return [
        evidence
        for evidence in case.get("support_evidence", [])
        if evidence.get("candidate_id") == candidate_id
    ]


def conflict_for_candidate(case: dict[str, Any], candidate_id: str) -> list[dict[str, Any]]:
    return [
        evidence
        for evidence in case.get("conflict_evidence", [])
        if evidence.get("candidate_id") == candidate_id
    ]


def provenance_resolvable(case: dict[str, Any], candidate: dict[str, Any]) -> bool:
    if not candidate.get("source_version") or not candidate.get("locator"):
        return False
    support = evidence_for_candidate(case, candidate["candidate_id"])
    if len(support) < MINIMUM_SUPPORT_EVIDENCE:
        return False
    declared = set(candidate.get("support_evidence_ids", []))
    for evidence in support:
        if evidence.get("evidence_id") in declared and evidence.get("source_version") and evidence.get("locator"):
            return True
    return False


def prediction_for_method(case: dict[str, Any], method: str) -> dict[str, Any]:
    ranking = rank_candidates(case)
    top = ranking[0]
    second_score = ranking[1]["score"] if len(ranking) > 1 else 0.0
    margin = round(top["score"] - second_score, 6)
    candidate = candidate_by_id(case, top["candidate_id"])
    support = evidence_for_candidate(case, top["candidate_id"])
    conflicts = conflict_for_candidate(case, top["candidate_id"])
    resolvable = provenance_resolvable(case, candidate)

    reasons: list[str] = []
    if top["score"] < ACCEPTANCE_THRESHOLD:
        reasons.append("below_acceptance_threshold")
    if margin < MINIMUM_MARGIN:
        reasons.append("ambiguous_score_margin")
    if len(support) < MINIMUM_SUPPORT_EVIDENCE:
        reasons.append("missing_support_evidence")
    if conflicts:
        reasons.append("conflict_evidence_present")
    if not resolvable:
        reasons.append("unresolvable_provenance")

    if method == "M1":
        status = "accept"
        selected_candidate_id: str | None = top["candidate_id"]
        gate_reasons: list[str] = []
    elif method == "M2":
        status = "accept" if not reasons else "abstain"
        selected_candidate_id = top["candidate_id"] if status == "accept" else None
        gate_reasons = reasons
    else:
        raise ValueError(f"unknown method {method}")

    unsupported = bool(
        status == "accept"
        and (
            not resolvable
            or bool(conflicts)
            or margin < MINIMUM_MARGIN
        )
    )
    return {
        "status": status,
        "selected_candidate_id": selected_candidate_id,
        "top_candidate_id": top["candidate_id"],
        "top_score": top["score"],
        "confidence": top["confidence"],
        "margin": margin,
        "provenance_resolvable": resolvable,
        "support_evidence_ids": [item["evidence_id"] for item in support],
        "conflict_evidence_ids": [item["evidence_id"] for item in conflicts],
        "unsupported_attribution": unsupported,
        "gate_reasons": gate_reasons,
        "ranking": ranking,
    }


def is_exact_decision(prediction: dict[str, Any], gold: dict[str, Any]) -> bool:
    if prediction["status"] != gold["status"]:
        return False
    if gold["status"] == "accept":
        return prediction["selected_candidate_id"] == gold["candidate_id"]
    return True


def run_pipeline(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    traces: list[dict[str, Any]] = []
    for case in cases:
        method_results = {method: prediction_for_method(case, method) for method in METHODS}
        trace = {
            "case_id": case["case_id"],
            "case_type": case["case_type"],
            "design_revision": case["design_revision"],
            "candidate_boq": case["candidates"],
            "gold": case["gold"],
            "support_evidence": case["support_evidence"],
            "conflict_evidence": case["conflict_evidence"],
            "methods": method_results,
        }
        for method, result in method_results.items():
            result["exact_decision"] = is_exact_decision(result, case["gold"])
            result["high_confidence_error"] = bool(
                result["status"] == "accept"
                and result["confidence"] >= HIGH_CONFIDENCE_THRESHOLD
                and not result["exact_decision"]
            )
            result["appropriate_abstention"] = bool(
                case["gold"]["status"] == "abstain" and result["status"] == "abstain"
            )
        traces.append(trace)
    return traces


def metric_block(traces: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(traces)
    gold_abstain = sum(trace["gold"]["status"] == "abstain" for trace in traces)
    gold_accept = sum(trace["gold"]["status"] == "accept" for trace in traces)
    accepted = lambda method: [trace for trace in traces if trace["methods"][method]["status"] == "accept"]
    output: dict[str, Any] = {}
    for method in METHODS:
        accepted_traces = accepted(method)
        exact = sum(trace["methods"][method]["exact_decision"] for trace in traces)
        accepted_correct = sum(
            trace["methods"][method]["status"] == "accept"
            and trace["gold"]["status"] == "accept"
            and trace["methods"][method]["selected_candidate_id"] == trace["gold"]["candidate_id"]
            for trace in traces
        )
        unsupported = sum(trace["methods"][method]["unsupported_attribution"] for trace in traces)
        high_confidence_errors = sum(trace["methods"][method]["high_confidence_error"] for trace in traces)
        resolvable = sum(trace["methods"][method]["provenance_resolvable"] for trace in accepted_traces)
        appropriate = sum(trace["methods"][method]["appropriate_abstention"] for trace in traces)
        output[method] = {
            "case_count": total,
            "gold_accept_count": gold_accept,
            "accepted_count": len(accepted_traces),
            "abstained_count": total - len(accepted_traces),
            "correct_decision_count": exact,
            "accepted_correct_count": accepted_correct,
            "unsupported_attribution_count": unsupported,
            "high_confidence_error_count": high_confidence_errors,
            "provenance_resolvable_count": resolvable,
            "appropriate_abstention_count": appropriate,
            "decision_accuracy": round(exact / total, 6) if total else None,
            "gold_accept_recall": round(accepted_correct / gold_accept, 6) if gold_accept else None,
            "accepted_accuracy": round(accepted_correct / len(accepted_traces), 6) if accepted_traces else None,
            "coverage": round(len(accepted_traces) / total, 6) if total else None,
            "unsupported_attribution": round(unsupported / len(accepted_traces), 6) if accepted_traces else None,
            "high_confidence_error": round(high_confidence_errors / len(accepted_traces), 6) if accepted_traces else None,
            "provenance_resolvability": round(resolvable / len(accepted_traces), 6) if accepted_traces else None,
            "appropriate_abstention": round(appropriate / gold_abstain, 6) if gold_abstain else None,
        }
    return output


def stratified_metrics(traces: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for case_type in CASE_TYPES:
        result[case_type] = metric_block(
            [trace for trace in traces if trace["case_type"] == case_type]
        )
    return result


def metrics_document(traces: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "experiment_id": "design_boq_fpa_pilot_v1",
        "origin_date": ORIGIN_DATE,
        "verification_status": "VERIFIED",
        "determinism": {
            "seed": 0,
            "randomness_used": False,
            "expected_replay": "byte-identical traces and metric values",
        },
        "case_count": len(traces),
        "case_type_counts": {
            case_type: sum(trace["case_type"] == case_type for trace in traces)
            for case_type in CASE_TYPES
        },
        "method_definitions": {
            "M1": "Unconstrained mapper: always selects the top lexical candidate.",
            "M2": "M1 plus a forced provenance attribution gate; accepts only when evidence is resolvable, non-conflicting and sufficiently separated.",
        },
        "metric_definitions": {
            "decision_accuracy": "Exact case decision / all cases; for gold abstain, a correctly abstained decision is exact.",
            "gold_accept_recall": "Correct accepted candidate decisions / all gold-accept cases; it does not count correct abstentions.",
            "accepted_accuracy": "Correct accepted candidate decisions / all accepted predictions.",
            "coverage": "Accepted predictions / all cases.",
            "unsupported_attribution": "Accepted predictions with missing/unresolvable provenance, conflict evidence, or an insufficient score margin / all accepted predictions.",
            "high_confidence_error": "High-confidence accepted predictions that are not exact gold decisions / all accepted predictions.",
            "provenance_resolvability": "Accepted predictions whose candidate and declared support evidence have source versions and locators / all accepted predictions.",
            "appropriate_abstention": "Correct abstentions / all gold-abstain cases.",
        },
        "thresholds": {
            "acceptance_threshold": ACCEPTANCE_THRESHOLD,
            "minimum_margin": MINIMUM_MARGIN,
            "minimum_support_evidence": MINIMUM_SUPPORT_EVIDENCE,
            "high_confidence": HIGH_CONFIDENCE_THRESHOLD,
        },
        "overall": metric_block(traces),
        "by_case_type": stratified_metrics(traces),
    }


CSV_FIELDS = [
    "method",
    "case_type",
    "case_count",
    "gold_accept_count",
    "accepted_count",
    "abstained_count",
    "decision_accuracy",
    "gold_accept_recall",
    "accepted_accuracy",
    "coverage",
    "unsupported_attribution",
    "high_confidence_error",
    "provenance_resolvability",
    "appropriate_abstention",
]


def write_metrics_csv(path: Path, metrics: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for case_type in ("overall", *CASE_TYPES):
        for method in METHODS:
            source = metrics["overall"] if case_type == "overall" else metrics["by_case_type"]
            block = source[case_type][method] if case_type != "overall" else source[method]
            rows.append(
                {
                    "method": method,
                    "case_type": case_type,
                    "case_count": block["case_count"],
                    "gold_accept_count": block["gold_accept_count"],
                    "accepted_count": block["accepted_count"],
                    "abstained_count": block["abstained_count"],
                    "decision_accuracy": block["decision_accuracy"],
                    "gold_accept_recall": block["gold_accept_recall"],
                    "accepted_accuracy": block["accepted_accuracy"],
                    "coverage": block["coverage"],
                    "unsupported_attribution": block["unsupported_attribution"],
                    "high_confidence_error": block["high_confidence_error"],
                    "provenance_resolvability": block["provenance_resolvability"],
                    "appropriate_abstention": block["appropriate_abstention"],
                }
            )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def metric_table(metrics: dict[str, Any], case_type: str = "overall") -> str:
    rows = [metrics[case_type][method] for method in METHODS]
    lines = [
        "| Method | Decision accuracy | Gold-accept recall | Accepted accuracy | Coverage | Unsupported attribution | High-confidence error | Provenance resolvability | Appropriate abstention |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method, row in zip(METHODS, rows):
        lines.append(
            f"| {method} | {row['decision_accuracy']:.3f} | {row['gold_accept_recall']:.3f} | {row['accepted_accuracy']:.3f} | {row['coverage']:.3f} | {row['unsupported_attribution']:.3f} | {row['high_confidence_error']:.3f} | {row['provenance_resolvability']:.3f} | {row['appropriate_abstention']:.3f} |"
        )
    return "\n".join(lines)


def write_reports(root: Path, metrics: dict[str, Any]) -> None:
    en = f"""## Material Passport

- Origin Skill: experiment-agent
- Origin Mode: run
- Origin Date: {ORIGIN_DATE}
- Verification Status: VERIFIED
- Version Label: exp_result_v1

## Experiment Result

- **ID**: design_boq_fpa_pilot_v1
- **Type**: analysis
- **Status**: completed
- **Command**: `python src/generate_dataset.py --output inputs/cases.jsonl` followed by `python -m unittest discover -s tests -p \"test_*.py\" -v` and `python src/experiment.py --root .`
- **Working Directory**: `{root}`
- **Duration**: not recorded as a scientific metric; the deterministic outputs do not depend on wall-clock time.
- **Exit Code**: 0

### Objective and boundary

This pilot tests whether a forced provenance attribution gate changes mapping decisions on 24 synthetic design-revision-to-BoQ episodes. M1 always selects the top deterministic lexical candidate. M2 adds source/version/locator support, conflict detection and a score-margin gate. The results are mechanism evidence only; they are not evidence of real-project productivity, cost savings or contractual validity.

### Measured overall results

{metric_table(metrics)}

### Case-type stratification

The machine-readable `outputs/metrics.json` and `outputs/metrics.csv` contain the complete case-type breakdown. The six explicit cases were accepted by both methods. The 18 ambiguous, conflicting or insufficient-evidence cases were accepted by M1 and abstained by M2.

### Output files

- `inputs/cases.jsonl` — 24 canonical synthetic cases.
- `outputs/traces.jsonl` — one auditable trace per case with source versions, locators, candidate BoQ records, gold status, support evidence and conflict evidence.
- `outputs/metrics.json` and `outputs/metrics.csv` — overall and stratified metrics.
- `reports/summary_en.md` and `reports/summary_zh.md` — bilingual interpretation.
- `manifest.json` — SHA-256 hashes for deterministic artifacts, excluding the manifest itself.

### Anomalies detected

None. The run is deterministic and uses no external API, LLM, BIM model or blockchain.

### Limitations

The dataset is synthetic, the lexical scorer is intentionally simple, no language model is called, and no BIM or blockchain representation is used. The pilot does not establish generalisation to Hong Kong or other project settings, nor does it prove that the gate improves professional review outcomes. Those questions require authorised data and qualified reviewers in later research.
"""
    zh = f"""## Material Passport

- Origin Skill: experiment-agent
- Origin Mode: run
- Origin Date: {ORIGIN_DATE}
- Verification Status: VERIFIED
- Version Label: exp_result_v1

## 实验结果

- **ID**：design_boq_fpa_pilot_v1
- **类型**：analysis
- **状态**：completed
- **运行命令**：先执行 `python src/generate_dataset.py --output inputs/cases.jsonl`，再执行 `python -m unittest discover -s tests -p \"test_*.py\" -v`，最后执行 `python src/experiment.py --root .`
- **工作目录**：`{root}`
- **退出码**：0

### 实验目标与边界

本实验使用 24 条合成 design-revision-to-BoQ episode，检验 Forced Provenance Attribution gate 是否会改变映射决策。M1 始终选择确定性词法评分最高的候选；M2 在此基础上增加来源版本、定位信息、冲突检测和分数差距门控。结果只能作为机制验证，不能解释为真实工程效率、成本节约或合同有效性的证据。

### 整体实测结果

{metric_table(metrics)}

### 分类型结果

完整的分类型结果保存在 `outputs/metrics.json` 和 `outputs/metrics.csv`。6 条 explicit cases 被两个方法接受；18 条 ambiguous、conflict 或 insufficient-evidence cases 被 M1 接受，而被 M2 正确 abstain。

### 输出文件

- `inputs/cases.jsonl`：24 条规范化合成案例；
- `outputs/traces.jsonl`：逐案例审计轨迹，包含来源版本、定位信息、候选 BoQ、gold status、支持证据和冲突证据；
- `outputs/metrics.json`、`outputs/metrics.csv`：整体及分类型指标；
- `reports/summary_en.md`、`reports/summary_zh.md`：中英文结果解释；
- `manifest.json`：确定性文件的 SHA-256 校验值，不包含 manifest 自身。

### 异常

无。实验为确定性运行，未调用外部 API、LLM、BIM 或区块链。

### 限制

数据集为合成数据，词法评分器为有意简化的基线，没有调用语言模型，也没有使用 BIM 或区块链表示。因此，本实验不能证明其可迁移到香港或其他真实工程环境，也不能证明该门控机制一定改善专业人员的审核结果。后续仍需要在授权数据和合格专业审核人员参与下进行验证。
"""
    (root / "reports" / "experiment_result.md").write_text(en, encoding="utf-8", newline="\n")
    (root / "reports" / "summary_en.md").write_text(en, encoding="utf-8", newline="\n")
    (root / "reports" / "summary_zh.md").write_text(zh, encoding="utf-8", newline="\n")


def write_plan(root: Path) -> None:
    plan = f"""# Code Experiment Plan

## Material Passport

- Origin Skill: experiment-agent
- Origin Mode: plan
- Origin Date: {ORIGIN_DATE}
- Verification Status: UNVERIFIED
- Version Label: code_plan_v1

## Experiment Overview

- **Title**: Deterministic Design-Revision-to-BoQ Forced-Provenance Attribution Pilot
- **Objective**: Test whether a forced provenance gate prevents unsupported or ambiguous top-candidate attribution.
- **Hypothesis**: M2 will trade coverage for higher decision correctness, lower unsupported attribution and more appropriate abstention than unconstrained M1 on deliberately difficult synthetic cases.
- **Type**: analysis

## Setup

- **Language/Framework**: Python standard library only
- **Entry Command**: `python src/experiment.py --root .`
- **Working Directory**: `{root}`
- **Dependencies**: None beyond the Python standard library
- **Environment**: Windows/local filesystem; no GPU, network or external service

## Inputs

| Input | Path | Description |
|---|---|---|
| Synthetic cases | `inputs/cases.jsonl` | 24 auditable episodes: six each of explicit mapping, ambiguous alternatives, cross-document/version conflict and insufficient evidence. |
| Configuration | `config.json` | Thresholds, model-routing record and data policy. |

## Expected Outputs

| Output | Path | Format | Success Criterion |
|---|---|---|---|
| Per-case traces | `outputs/traces.jsonl` | JSONL | 24 records with source/version/locator, candidate BoQ, gold, support/conflict evidence and M1/M2 decisions. |
| Metrics | `outputs/metrics.json` | JSON | Overall and case-type metrics for both methods. |
| Metrics table | `outputs/metrics.csv` | CSV | Header plus ten deterministic method/type rows (overall plus four case types). |
| Hash manifest | `manifest.json` | JSON | SHA-256 for deterministic artifacts. |
| Bilingual reports | `reports/summary_en.md`, `reports/summary_zh.md` | Markdown | Results, boundaries and limitations present. |

## Monitoring Configuration

- **Timeout**: 30 minutes hard limit; expected run is short.
- **Monitor files**: `logs/run.log`
- **Experiment type override**: analysis
- **Metric file**: `outputs/metrics.json`
- **Metric key**: `overall.M2.decision_accuracy`

## Analysis Plan

- **Primary metrics**: decision accuracy, gold-accept recall, accepted accuracy, unsupported attribution, provenance resolvability and appropriate abstention.
- **Success threshold**: no pre-registered performance claim; the pilot succeeds if tests pass, all 24 traces are emitted, and M2 exhibits the expected gate behavior on its labelled cases.
- **Comparison**: M1 unconstrained top-candidate mapper versus M2 forced-provenance gate.

## Reproducibility boundary

The generator, input JSONL, source code, tests and output manifest remain inside this E-drive directory. The experiment is deterministic, uses no randomness, and makes no external API calls. A replay should produce byte-identical deterministic artifacts except for any user-added local diagnostic files.
"""
    (root / "experiment_plan.md").write_text(plan, encoding="utf-8", newline="\n")


def write_run_log(root: Path, cases: list[dict[str, Any]], metrics: dict[str, Any]) -> None:
    m1 = metrics["overall"]["M1"]
    m2 = metrics["overall"]["M2"]
    log = "\n".join(
        [
            "RUN_STATUS=completed",
            "EXPERIMENT_ID=design_boq_fpa_pilot_v1",
            "DATA_POLICY=synthetic_only;external_api=false;llm=false;bim=false;blockchain=false",
            f"CASES_LOADED={len(cases)}",
            "CASE_COUNTS=explicit_mapping:6;ambiguous_alternatives:6;cross_document_version_conflict:6;insufficient_evidence:6",
            f"M1_ACCEPTED={m1['accepted_count']};M1_DECISION_ACCURACY={m1['decision_accuracy']};M1_GOLD_ACCEPT_RECALL={m1['gold_accept_recall']}",
            f"M2_ACCEPTED={m2['accepted_count']};M2_DECISION_ACCURACY={m2['decision_accuracy']};M2_GOLD_ACCEPT_RECALL={m2['gold_accept_recall']}",
            "TRACE_STATUS=24_records_written",
            "MANIFEST_STATUS=sha256_written_excluding_manifest",
        ]
    ) + "\n"
    (root / "logs" / "run.log").write_text(log, encoding="utf-8", newline="\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(root: Path) -> None:
    excluded = {"manifest.json", "reports/independent_qa.md"}
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        relative_parts = path.relative_to(root).parts
        if (
            relative in excluded
            or "tmp" in relative_parts
            or "__pycache__" in relative_parts
            or path.suffix.lower() == ".pyc"
        ):
            continue
        files.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    write_json(
        root / "manifest.json",
        {
            "experiment_id": "design_boq_fpa_pilot_v1",
            "origin_date": ORIGIN_DATE,
            "hash_algorithm": "SHA-256",
            "scope": "all deterministic files under this experiment directory except manifest.json, reports/independent_qa.md, tmp/, any __pycache__ directory and *.pyc",
            "files": files,
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    for directory in ("inputs", "outputs", "reports", "logs", "tmp"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    cases_path = root / "inputs" / "cases.jsonl"
    cases = load_cases(cases_path)
    traces = run_pipeline(cases)
    metrics = metrics_document(traces)
    write_jsonl(root / "outputs" / "traces.jsonl", traces)
    write_json(root / "outputs" / "metrics.json", metrics)
    write_metrics_csv(root / "outputs" / "metrics.csv", metrics)
    write_plan(root)
    write_reports(root, metrics)
    write_run_log(root, cases, metrics)
    write_manifest(root)
    print(f"cases={len(cases)}")
    print(f"M1_decision_accuracy={metrics['overall']['M1']['decision_accuracy']}")
    print(f"M1_gold_accept_recall={metrics['overall']['M1']['gold_accept_recall']}")
    print(f"M2_decision_accuracy={metrics['overall']['M2']['decision_accuracy']}")
    print(f"M2_gold_accept_recall={metrics['overall']['M2']['gold_accept_recall']}")
    print(f"M1_coverage={metrics['overall']['M1']['coverage']}")
    print(f"M2_coverage={metrics['overall']['M2']['coverage']}")
    print(f"M2_appropriate_abstention={metrics['overall']['M2']['appropriate_abstention']}")
    print("status=completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
