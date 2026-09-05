"""Offline evaluation of strict-cascade LLM/gate outputs.

Gold data are loaded only after all runtime result files exist. The conclusion
score is a documented deterministic mapping, not an independent legal verdict.
Reference-only/S2 citations are audited separately from independent legal
evidence so appropriate reviewer context is not counted as a false legal cite.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

try:
    from conclusion_contract_v2 import (
        CANONICAL_CONCLUSION_STATES,
        canonicalize_conclusion_type,
        legacy_three_class_label,
    )
except ImportError:  # pragma: no cover - preserves historical standalone use
    CANONICAL_CONCLUSION_STATES = (
        "requires_human_legal_confirm",
        "requires_human_legal_review",
        "insufficient_information_needs_human_confirm",
        "no_applicable_legal_basis_found_needs_human_confirm",
        "no_supported_issue_found_within_review_scope",
    )
    _CONCLUSION_ALIASES = {
        "requires_human_legal_confirm": "requires_human_legal_confirm",
        "requires_human_legal_review": "requires_human_legal_review",
        "potential_risk": "requires_human_legal_review",
        "insufficient_information": "insufficient_information_needs_human_confirm",
        "insufficient_information_needs_human_confirm": "insufficient_information_needs_human_confirm",
        "no_applicable_legal_basis_found": "no_applicable_legal_basis_found_needs_human_confirm",
        "no_applicable_legal_basis_found_needs_human_confirm": "no_applicable_legal_basis_found_needs_human_confirm",
        "valid_needs_human_confirm": "insufficient_information_needs_human_confirm",
        "no_supported_issue_found_within_review_scope": "no_supported_issue_found_within_review_scope",
    }

    def canonicalize_conclusion_type(value: Any) -> str | None:
        return _CONCLUSION_ALIASES.get(value.strip()) if isinstance(value, str) else None

    def legacy_three_class_label(value: Any) -> str | None:
        canonical = canonicalize_conclusion_type(value)
        return {
            "requires_human_legal_confirm": "risk_supported",
            "requires_human_legal_review": "risk_supported",
            "insufficient_information_needs_human_confirm": "insufficient_information",
            "no_applicable_legal_basis_found_needs_human_confirm": "insufficient_information",
            "no_supported_issue_found_within_review_scope": "no_supported_issue_found",
        }.get(canonical)


LEVELS = {"Level 1", "Level 2", "Level 3", "Level 4"}
LEVEL_ORDER = ("Level 1", "Level 2", "Level 3", "Level 4")
LEGACY_THREE_CLASS_LABELS = (
    "risk_supported",
    "no_supported_issue_found",
    "insufficient_information",
)
EXPECTED_OVERRIDES = {
    # Explicit user-reviewed exceptions recorded after promotion of the original
    # synthetic set. The source gold file itself remains immutable.
    "SYN-P1-G05-I35": "requires_human_legal_review",
    "SYN-P1-G06-I36": "insufficient_information",
}

OFFLINE_GROUNDING_NOT_EVALUATED_REASON = (
    "saved replay lacks complete runtime context; raw candidate flags are not effective evidence admission; "
    "do not interpret as hallucination/grounding quality"
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def expected_conclusion(gold: dict[str, Any]) -> str:
    issue_id = str(gold["issue_id"])
    if issue_id in EXPECTED_OVERRIDES:
        return EXPECTED_OVERRIDES[issue_id]
    risk = gold.get("risk_category")
    if risk == "no_issue_identified":
        return "no_supported_issue_found_within_review_scope"
    if risk in {"out_of_scope_or_unverifiable", "missing_or_insufficient_evidence"}:
        return "insufficient_information"
    if gold.get("legal_basis_chunk_ids"):
        return "requires_human_legal_review"
    return "insufficient_information"


def canonical_prediction(value: Any, *, blocked: bool = False) -> str:
    """Canonicalize a response without changing the stored native value."""

    if blocked:
        return "blocked"
    canonical = canonicalize_conclusion_type(value)
    if canonical:
        return canonical
    return str(value).strip() if value is not None and str(value).strip() else "unknown"


def legacy_expected_class(value: Any) -> str:
    """Map the immutable Stage 2 gold-derived class to a v2 comparison bucket."""

    return {
        "requires_human_legal_review": "risk_supported",
        "no_supported_issue_found_within_review_scope": "no_supported_issue_found",
        "insufficient_information": "insufficient_information",
    }.get(str(value), "unknown")


def legacy_predicted_class(value: Any, *, blocked: bool = False) -> str:
    if blocked:
        return "blocked"
    return legacy_three_class_label(value) or "unknown"


def possible_over_alert_fields(finding: dict[str, Any]) -> tuple[bool, str]:
    """Read runtime conflict flags without treating them as gold adjudication."""

    flag = bool(
        finding.get("possible_over_alert")
        or finding.get("possible_over_alert_flag")
        or finding.get("over_alert_flag")
    )
    reason = str(
        finding.get("possible_over_alert_reason")
        or finding.get("over_alert_reason")
        or ""
    ).strip()
    flags = finding.get("flags")
    if isinstance(flags, list) and any("over_alert" in str(item) for item in flags):
        flag = True
    if isinstance(flags, dict) and flags.get("possible_over_alert"):
        flag = True
    return flag, reason


def iter_triage_responses(result: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for level in result.get("cascade_execution_audit") or []:
        for phase in level.get("phases") or []:
            response = phase.get("llm_response")
            if isinstance(response, dict):
                yield response


def usage_totals(responses: Iterable[dict[str, Any]]) -> dict[str, int]:
    totals: Counter[str] = Counter()
    for response in responses:
        usage = response.get("usage") or {}
        for key in (
            "prompt_tokens", "completion_tokens", "total_tokens",
            "prompt_cache_hit_tokens", "prompt_cache_miss_tokens",
        ):
            value = usage.get(key)
            if isinstance(value, int):
                totals[key] += value
        details = usage.get("completion_tokens_details") or {}
        if isinstance(details.get("reasoning_tokens"), int):
            totals["reasoning_tokens"] += details["reasoning_tokens"]
    return dict(totals)


def independent_evidence(row: dict[str, Any]) -> bool:
    explicit = row.get("independent_legal_evidence")
    if explicit is not None:
        return bool(explicit)
    eligibility = str(row.get("legal_evidence_eligibility") or "").lower()
    if "supplement" in eligibility or "context" in eligibility:
        return False
    return (
        row.get("normative_level") in LEVELS
        and row.get("corpus_partition") in {"primary", "verification"}
    )


def ratio(numerator: int | float, denominator: int | float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def class_metrics(
    rows: list[dict[str, Any]],
    label: str,
    *,
    expected_field: str = "expected_conclusion",
    predicted_field: str = "predicted_conclusion",
) -> dict[str, float | int]:
    true_positive = sum(
        row.get(expected_field) == label and row.get(predicted_field) == label
        for row in rows
    )
    false_positive = sum(
        row.get(expected_field) != label and row.get(predicted_field) == label
        for row in rows
    )
    false_negative = sum(
        row.get(expected_field) == label and row.get(predicted_field) != label
        for row in rows
    )
    precision = ratio(true_positive, true_positive + false_positive)
    recall = ratio(true_positive, true_positive + false_negative)
    f1 = ratio(2 * precision * recall, precision + recall)
    return {"tp": true_positive, "fp": false_positive, "fn": false_negative, "precision": precision, "recall": recall, "f1": f1}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Write evaluation artifacts here; defaults to --run-root for historical standalone use.",
    )
    args = parser.parse_args()
    output_root = args.output_root or args.run_root
    output_root.mkdir(parents=True, exist_ok=True)
    replay_manifest = {}
    manifest_path = args.run_root / "manifest.json"
    if manifest_path.exists():
        try:
            replay_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            replay_manifest = {}
    replay_mode = replay_manifest.get("replay_mode")
    offline_saved_replay = replay_mode == "offline_saved60"
    gold_rows = load_jsonl(args.gold)
    corpus_by_id = {row["chunk_id"]: row for row in load_jsonl(args.corpus)}
    cases: list[dict[str, Any]] = []
    all_usage: Counter[str] = Counter()
    triage_finish_reasons: Counter[str] = Counter()
    final_finish_reasons: Counter[str] = Counter()
    selected_channels: Counter[str] = Counter()
    selected_parse_methods: Counter[str] = Counter()
    model_returned: Counter[str] = Counter()
    total_api_calls = 0

    for gold in gold_rows:
        path = args.run_root / f"{gold['issue_id']}.json"
        if not path.exists():
            cases.append({"issue_id": gold["issue_id"], "status": "missing_result"})
            continue
        result = json.loads(path.read_text(encoding="utf-8"))
        gate = (
            result.get("post_llm_gate")
            or result.get("stage3_gate_result")
            or result.get("gate")
            or {}
        )
        response = gate.get("response") or {}
        findings = response.get("findings") or []
        finding = findings[0] if findings and isinstance(findings[0], dict) else {}
        predicted_raw = "blocked" if gate.get("blocked") else finding.get("conclusion_type")
        predicted = canonical_prediction(predicted_raw, blocked=bool(gate.get("blocked")))
        predicted_legacy = legacy_predicted_class(
            predicted,
            blocked=bool(gate.get("blocked")),
        )
        expected = expected_conclusion(gold)
        expected_legacy = legacy_expected_class(expected)

        evidence_rows = [row for row in finding.get("legal_evidence", []) if isinstance(row, dict)]
        independent_rows = [row for row in evidence_rows if independent_evidence(row)]
        reference_rows = [row for row in evidence_rows if not independent_evidence(row)]
        cited = {str(row["chunk_id"]) for row in independent_rows if row.get("chunk_id")}
        reference_ids = {str(row["chunk_id"]) for row in reference_rows if row.get("chunk_id")}
        gold_ids = {str(value) for value in gold.get("legal_basis_chunk_ids", [])}
        true_positive_ids = cited & gold_ids
        runtime_input_value = result.get("runtime_input")
        runtime_input = runtime_input_value if isinstance(runtime_input_value, dict) else {}
        runtime_context_available = (
            bool(runtime_input) if offline_saved_replay else True
        )
        retrieval_audit = (
            runtime_input.get("hierarchy_retrieval_audit")
            or response.get("retrieval_audit")
            or {}
        )
        runtime_ids: set[str] = set()
        if runtime_context_available:
            runtime_ids = {
                str(row["chunk_id"])
                for row in runtime_input.get("retrieved_legal_evidence", [])
                if isinstance(row, dict) and row.get("chunk_id")
            }
            runtime_ids.update(
                str(chunk_id)
                for chunk_id in retrieval_audit.get("high_trust_candidates_used", [])
                if chunk_id
            )
        unsupported_runtime_ids = (
            cited - runtime_ids if runtime_context_available else None
        )
        gold_levels = sorted({
            str(corpus_by_id[chunk_id].get("normative_level"))
            for chunk_id in gold_ids if chunk_id in corpus_by_id
        })
        stopped_at = (
            retrieval_audit.get("stopped_at_level")
        )
        stop_index = LEVEL_ORDER.index(stopped_at) if stopped_at in LEVEL_ORDER else None
        gold_level_indexes = [LEVEL_ORDER.index(level) for level in gold_levels if level in LEVEL_ORDER]
        potential_premature_stop = bool(
            stop_index is not None
            and gold_level_indexes
            and stop_index < min(gold_level_indexes)
            and not true_positive_ids
        )

        final_response = (
            result.get("final_llm_response")
            or result.get("raw_stage2_final_llm_response")
            or {}
        )
        triage_responses = list(iter_triage_responses(result))
        api_responses = triage_responses + [final_response]
        total_api_calls += len(api_responses)
        recorded_response_slots = len(api_responses)
        case_usage = usage_totals(api_responses)
        for key, value in case_usage.items():
            all_usage[key] += value
        for item in triage_responses:
            triage_finish_reasons[item.get("finish_reason")] += 1
        final_finish_reasons[final_response.get("finish_reason")] += 1
        diagnostics = final_response.get("response_channel_diagnostics") or {}
        selected_channels[diagnostics.get("selected_channel")] += 1
        selected_parse_methods[diagnostics.get("selected_parse_method")] += 1
        model_returned[final_response.get("model_returned")] += 1

        over_alert_flag, over_alert_reason = possible_over_alert_fields(finding)
        legal_basis_locators = []
        for evidence in evidence_rows:
            locator = " ".join(
                str(part).strip()
                for part in (
                    evidence.get("law"),
                    evidence.get("article"),
                    f"[{evidence.get('normative_level')}]" if evidence.get("normative_level") else "",
                    evidence.get("source_locator"),
                )
                if str(part).strip()
            )
            if locator:
                legal_basis_locators.append(locator)

        cases.append({
            "issue_id": gold["issue_id"],
            "status": "scored",
            "expected_conclusion": expected,
            "expected_conclusion_source": (
                "explicit_user_review_override"
                if gold["issue_id"] in EXPECTED_OVERRIDES
                else "deterministic_gold_field_mapping"
            ),
            "predicted_conclusion_raw": predicted_raw,
            "predicted_conclusion": predicted,
            "predicted_legacy_three_class": predicted_legacy,
            "expected_conclusion_legacy_three_class": expected_legacy,
            "conclusion_match": predicted_legacy == expected_legacy,
            "canonical_conclusion_is_supported_by_gold": False,
            "gold_chunk_ids": sorted(gold_ids),
            "independent_cited_chunk_ids": sorted(cited),
            "reference_only_chunk_ids": sorted(reference_ids),
            "legal_basis_locators": legal_basis_locators,
            "substantive_recommendation": finding.get("assistant_recommendation") or finding.get("recommended_human_action") or "",
            "runtime_context_available": runtime_context_available,
            "runtime_retrieved_chunk_ids": sorted(runtime_ids),
            "unsupported_runtime_citation_ids": (
                sorted(unsupported_runtime_ids) if unsupported_runtime_ids is not None else None
            ),
            "evidence_hit": bool(true_positive_ids) if gold_ids else not cited,
            "evidence_precision": ratio(len(true_positive_ids), len(cited)) if cited else (1.0 if not gold_ids else 0.0),
            "evidence_recall": ratio(len(true_positive_ids), len(gold_ids)) if gold_ids else (1.0 if not cited else 0.0),
            "gate_status": gate.get("status"),
            "gate_blocked": bool(gate.get("blocked")),
            "gate_actions_count": len(gate.get("actions") or []),
            "final_response_ok": bool(final_response.get("ok")),
            "final_json_parsed": isinstance(final_response.get("parsed"), dict),
            "pre_gate_core_schema_valid": (
                isinstance(final_response.get("parsed"), dict)
                and isinstance((final_response.get("parsed") or {}).get("findings"), list)
            ),
            "finish_reason": final_response.get("finish_reason"),
            "selected_channel": diagnostics.get("selected_channel"),
            "selected_parse_method": diagnostics.get("selected_parse_method"),
            "human_review_status": finding.get("human_review_status"),
            "overall_review_status": response.get("overall_review_status"),
            "possible_over_alert_runtime_flag": over_alert_flag,
            "possible_over_alert_runtime_reason": over_alert_reason,
            "offline_gold_false_positive": (
                expected_legacy == "no_supported_issue_found"
                and predicted_legacy == "risk_supported"
            ),
            "gold_normative_levels": gold_levels,
            "stopped_at_level": stopped_at,
            "potential_premature_higher_level_stop": potential_premature_stop,
            "predicted_review_without_runtime_supported_citation": (
                predicted_legacy == "risk_supported"
                and (not cited or bool(unsupported_runtime_ids))
            ),
            "api_calls": 0 if offline_saved_replay else len(api_responses),
            "recorded_response_slots": recorded_response_slots,
            "usage": case_usage,
        })

    scored = [row for row in cases if row["status"] == "scored"]
    deliverable = [row for row in scored if not row["gate_blocked"]]
    expected_no_issue = [row for row in scored if row["expected_conclusion"] == "no_supported_issue_found_within_review_scope"]
    expected_insufficient = [row for row in scored if row["expected_conclusion"] == "insufficient_information"]
    expected_review = [row for row in scored if row["expected_conclusion"] == "requires_human_legal_review"]
    confusion = Counter(
        f"{row['expected_conclusion']} -> {row['predicted_conclusion']}"
        for row in scored
    )
    per_class = {
        label: class_metrics(
            scored,
            label,
            expected_field="expected_conclusion_legacy_three_class",
            predicted_field="predicted_legacy_three_class",
        )
        for label in LEGACY_THREE_CLASS_LABELS
    }
    macro_f1 = ratio(sum(values["f1"] for values in per_class.values()), len(per_class))
    independent_citation_count = sum(len(row["independent_cited_chunk_ids"]) for row in scored)
    runtime_context_unavailable = offline_saved_replay and any(
        not row.get("runtime_context_available") for row in scored
    )
    unsupported_runtime_citation_count = (
        None
        if runtime_context_unavailable
        else sum(len(row["unsupported_runtime_citation_ids"] or []) for row in scored)
    )
    predicted_risk_rows = [row for row in scored if row["predicted_legacy_three_class"] == "risk_supported"]
    summary = {
        "requested": len(gold_rows),
        "scored": len(scored),
        "missing": len(gold_rows) - len(scored),
        "deliverable_after_gate": len(deliverable),
        "gate_blocked_count": sum(row["gate_blocked"] for row in scored),
        "gate_blocked_rate": ratio(sum(row["gate_blocked"] for row in scored), len(scored)),
        "gate_correction_rate": ratio(sum(row["gate_status"] == "corrected" for row in scored), len(scored)),
        "conclusion_accuracy_on_documented_mapping": ratio(sum(row["conclusion_match"] for row in scored), len(scored)),
        "macro_f1_three_conclusion_classes": macro_f1,
        "per_class_metrics": per_class,
        "risk_supported_precision_confirm_and_review_mapped_together": per_class["risk_supported"]["precision"],
        "risk_supported_recall_confirm_and_review_mapped_together": per_class["risk_supported"]["recall"],
        "risk_supported_f1_confirm_and_review_mapped_together": per_class["risk_supported"]["f1"],
        "requires_review_exact_match": ratio(
            sum(row["predicted_legacy_three_class"] == "risk_supported" for row in expected_review),
            len(expected_review),
        ),
        "no_issue_exact_match": ratio(
            sum(row["predicted_legacy_three_class"] == "no_supported_issue_found" for row in expected_no_issue),
            len(expected_no_issue),
        ),
        "insufficient_information_exact_match": ratio(
            sum(row["predicted_legacy_three_class"] == "insufficient_information" for row in expected_insufficient),
            len(expected_insufficient),
        ),
        "over_alert_rate_on_expected_no_issue": ratio(
            sum(row["predicted_legacy_three_class"] == "risk_supported" for row in expected_no_issue),
            len(expected_no_issue),
        ),
        "mean_independent_evidence_precision": (
            None
            if offline_saved_replay
            else ratio(sum(row["evidence_precision"] for row in scored), len(scored))
        ),
        "mean_independent_evidence_recall": (
            None
            if offline_saved_replay
            else ratio(sum(row["evidence_recall"] for row in scored), len(scored))
        ),
        "independent_evidence_hit_rate": ratio(sum(row["evidence_hit"] for row in scored), len(scored)),
        "unsupported_runtime_citation_rate": (
            None
            if offline_saved_replay
            else ratio(unsupported_runtime_citation_count, independent_citation_count)
        ),
        "unsupported_runtime_citation_rate_reason": (
            OFFLINE_GROUNDING_NOT_EVALUATED_REASON if runtime_context_unavailable else None
        ),
        "predicted_review_without_runtime_supported_citation_rate": ratio(
            sum(row["predicted_review_without_runtime_supported_citation"] for row in predicted_risk_rows),
            len(predicted_risk_rows),
        ),
        "potential_premature_higher_level_stop_count": sum(
            row["potential_premature_higher_level_stop"] for row in scored
        ),
        "gate_status_counts": dict(Counter(row["gate_status"] for row in scored)),
        "final_finish_reason_counts": dict(final_finish_reasons),
        "triage_finish_reason_counts": dict(triage_finish_reasons),
        "final_response_ok_count": sum(row["final_response_ok"] for row in scored),
        "final_json_parsed_count": sum(row["final_json_parsed"] for row in scored),
        "pre_gate_core_schema_valid_count": sum(row["pre_gate_core_schema_valid"] for row in scored),
        "pre_gate_core_schema_valid_rate": ratio(sum(row["pre_gate_core_schema_valid"] for row in scored), len(scored)),
        "final_truncation_rate": ratio(sum(row["finish_reason"] != "stop" for row in scored), len(scored)),
        "response_selected_channel_counts": dict(selected_channels),
        "response_selected_parse_method_counts": dict(selected_parse_methods),
        "model_returned_counts": dict(model_returned),
        "total_api_calls": 0 if offline_saved_replay else total_api_calls,
        "recorded_response_slots": sum(row.get("recorded_response_slots", 0) for row in scored),
        "usage_totals": {} if offline_saved_replay else dict(all_usage),
        "usage_totals_replayed": dict(all_usage),
        "evaluation_mode": "offline_saved60_replay" if offline_saved_replay else "runtime_result_evaluation",
        "runtime_context_available": not runtime_context_unavailable,
        "grounding_metrics_reason": (
            OFFLINE_GROUNDING_NOT_EVALUATED_REASON if offline_saved_replay else None
        ),
        "new_api_calls": 0 if offline_saved_replay else total_api_calls,
        "all_deliverable_findings_require_review": all(
            row["human_review_status"] in {"review_required", "insufficient_information"}
            and row["overall_review_status"] == "requires_human_second_review"
            for row in deliverable
        ),
        "confusion_counts": dict(confusion),
        "canonical_conclusion_counts": dict(Counter(row["predicted_conclusion"] for row in scored)),
        "native_raw_conclusion_counts": dict(Counter(str(row["predicted_conclusion_raw"]) for row in scored)),
        "legacy_three_class_counts": dict(Counter(row["predicted_legacy_three_class"] for row in scored)),
        "expected_legacy_three_class_counts": dict(Counter(row["expected_conclusion_legacy_three_class"] for row in scored)),
        "runtime_possible_over_alert_flag_count": sum(row["possible_over_alert_runtime_flag"] for row in scored),
        "offline_gold_false_positive_count": sum(row["offline_gold_false_positive"] for row in scored),
        "canonical_subclass_accuracy_reported": False,
        "canonical_subclass_accuracy_boundary": "The immutable Stage 2 gold exposes three comparison classes only; five-state subclass accuracy is not inferred.",
    }
    output = {
        "summary": summary,
        "evaluation_mode": "offline_saved60_replay" if offline_saved_replay else "runtime_result_evaluation",
        "input_run_root": str(args.run_root),
        "output_root": str(output_root),
        "canonical_conclusion_states": list(CANONICAL_CONCLUSION_STATES),
        "legacy_three_class_mapping": {
            "requires_human_legal_confirm": "risk_supported",
            "requires_human_legal_review": "risk_supported",
            "insufficient_information_needs_human_confirm": "insufficient_information",
            "no_applicable_legal_basis_found_needs_human_confirm": "insufficient_information",
            "no_supported_issue_found_within_review_scope": "no_supported_issue_found",
            "blocked": "blocked",
        },
        "expected_conclusion_overrides": EXPECTED_OVERRIDES,
        "mapping_boundary": (
            "The original gold file is immutable. Native model/gate conclusions are retained as raw values and "
            "canonicalized to the approved five-state contract for distribution counts. Historical comparison uses "
            "the documented three-class mapping: requires_human_legal_confirm and requires_human_legal_review both "
            "map to risk_supported; the two human-confirm abstention states map to insufficient_information. This "
            "does not create five-class gold accuracy. It is not independently adjudicated legal-verdict accuracy. "
            "Reference-only/S2 citations are audited separately and are not scored as independent legal evidence. "
            "Evidence precision against sparse gold IDs is not the same as legal correctness; "
            "unsupported_runtime_citation_rate is the stricter supplied-evidence grounding check when complete "
            "runtime context is available. Offline saved60 replay without that context does not evaluate grounding "
            "quality."
        ),
        "cases": cases,
    }
    (output_root / "offline_gold_evaluation.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# Strict-cascade 60-gold LLM/gate evaluation", "",
        "| Metric | Value |", "|---|---:|",
    ]
    for key, value in summary.items():
        lines.append(f"| {key} | {json.dumps(value, ensure_ascii=False)} |")
    lines.extend(["", "## Case-level comparison", "", "| Issue | Expected | Predicted | Match | Gate | Evidence P | Evidence R |", "|---|---|---|---:|---|---:|---:|"])
    for row in cases:
        if row["status"] != "scored":
            lines.append(f"| {row['issue_id']} | — | — | 0 | missing | — | — |")
            continue
        lines.append(
            f"| {row['issue_id']} | {row['expected_conclusion']} | {row['predicted_conclusion_raw']} -> {row['predicted_conclusion']} | "
            f"{int(row['conclusion_match'])} | {row['gate_status']} | {row['evidence_precision']:.3f} | {row['evidence_recall']:.3f} |"
        )
    lines.extend(["", output["mapping_boundary"]])
    (output_root / "offline_gold_evaluation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
