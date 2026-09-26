"""Bind existing gated legal results to bundle candidates and review export.

The original core response and three-layer response are never rewritten. A
presentation copy is made for the existing Excel exporter. No model calls.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import sys
from pathlib import Path
from typing import Any


PUBLIC_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PUBLIC_ROOT / "src"))
from export_review_excel import build_workbook  # noqa: E402


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def fmt_source(source: dict[str, Any] | None) -> str:
    if not source:
        return "未找到可核验的配对原文"
    page = f"第{source['page_number']}页" if source.get("physical_page_available") else "物理页码未建立"
    return f"{source['document_key']} / {page} / {source['source_locator']}：{source['quote']}"


def issue_boundary(issue: dict[str, Any], coverage: dict[str, Any]) -> str:
    lines = []
    pairing = issue.get("pairing") or {}
    if pairing.get("status") in {"not_found_in_reviewed_text", "ambiguous_needs_human_matching"}:
        lines.append("配对未完成；不得据此断言投标文件未响应。")
    for doc in coverage["documents"]:
        empty = doc.get("unreadable_or_empty_physical_pages") or []
        if empty:
            lines.append(f"{doc['document_key']}未识别的物理页：{empty}。")
        if doc.get("page_locator_limitation"):
            lines.append(f"{doc['document_key']}：{doc['page_locator_limitation']}。")
        count = len(doc.get("not_selected_for_semantic_review_block_ids") or [])
        if count:
            lines.append(f"{doc['document_key']}另有{count}个已解析块未选入语义审查；不代表无风险。")
    return "\n".join(lines) or "自动事项发现非穷尽；人工仍须核对完整文件包。"


def handoff_for_issue(issue: dict[str, Any], payload: dict[str, Any] | None, allowed_sources: dict[tuple[str, str], list[str]]) -> dict[str, Any]:
    issue_id = issue["issue_id"]
    if payload is None:
        return {"processing_status": "not_provided", "handoff_status": "not_available", "presentation_only": True}
    if payload.get("issue_id") != issue_id:
        raise ValueError(f"three_layer_issue_binding_mismatch:{issue_id}")
    ctx = payload.get("context")
    if not isinstance(ctx, dict) or not isinstance(ctx.get("sources"), list):
        raise ValueError(f"three_layer_context_missing:{issue_id}")
    expected_mode = "text_response_comparison" if issue["task"] == "bid_responsiveness" else "clause_design"
    if (ctx.get("task") or {}).get("review_mode") != expected_mode:
        raise ValueError(f"three_layer_task_mode_mismatch:{issue_id}")
    declared_sources = {(row.get("document_sha256"), row.get("locator")) for row in ctx["sources"]}
    primary = issue["primary_source"]
    required_sources = {(primary["document_sha256"], primary["source_locator"])}
    pair = issue.get("pairing") or {}
    if pair.get("status") == "provisional_match_needs_verification":
        paired = pair["candidate_matches"][0]["source"]
        required_sources.add((paired["document_sha256"], paired["source_locator"]))
    if not required_sources <= declared_sources:
        raise ValueError(f"three_layer_missing_required_document_side:{issue_id}")
    for source in ctx["sources"]:
        texts = allowed_sources.get((source.get("document_sha256"), source.get("locator")))
        if not texts or not any(str(source.get("text", "")) in text for text in texts):
            raise ValueError(f"three_layer_source_not_bound_to_parsed_bundle:{issue_id}")
    execution = payload.get("execution")
    if not isinstance(execution, dict) or set(execution) != {"finish_reason", "transport_ok"}:
        raise ValueError(f"three_layer_execution_metadata_missing:{issue_id}")
    sys.path.insert(0, str(PUBLIC_ROOT / "candidates" / "three_layer_handoff_v01"))
    from gate import evaluate  # noqa: PLC0415
    return evaluate(payload.get("raw_response"), ctx, **execution, normalization=False)


def assemble(issue_dir: Path, core_dir: Path | None = None, handoff_path: Path | None = None,
             pair_dir: Path | None = None) -> dict[str, Any]:
    issues = load_json(issue_dir / "candidates.json")
    coverage = load_json(issue_dir / "coverage.json")
    labels = {r["issue_id"]: r for r in (
        json.loads(line) for line in (issue_dir / "candidate_labels.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()
    )}
    intake = load_json(issue_dir / "bundle_intake.json")
    allowed_sources: dict[tuple[str, str], list[str]] = {}
    for doc in intake["documents"]:
        for block in (
            json.loads(line) for line in Path(doc["locator_map_path"]).read_text(encoding="utf-8").splitlines() if line.strip()
        ):
            allowed_sources.setdefault((doc["source_file_hash"], block["source_locator"]), []).append(block["text"])
    handoffs = {}
    if handoff_path:
        values = load_json(handoff_path)
        if not isinstance(values, list) or any(not isinstance(x, dict) for x in values):
            raise ValueError("three_layer_records_must_be_list")
        handoffs = {x["issue_id"]: x for x in values}
        if len(handoffs) != len(values):
            raise ValueError("duplicate_three_layer_issue_id")
    output = []
    for issue in issues:
        issue_id = issue["issue_id"]
        label = labels.get(issue_id)
        result_dir = pair_dir if issue["task"] == "bid_responsiveness" else core_dir
        core_path = result_dir / f"{issue_id}.json" if result_dir else None
        core = load_json(core_path) if core_path and core_path.exists() else None
        if core and label is None:
            raise ValueError(f"core_result_for_unpaired_issue_forbidden:{issue_id}")
        if core:
            runtime = core.get("runtime_input") or {}
            if (core.get("issue_id") != issue_id or runtime.get("review_task_kind") != issue["task"]
                    or runtime.get("bundle_evidence") != label["bundle_evidence"]
                    or (runtime.get("contract_evidence") or {}).get("document_excerpt") != label["document_excerpt"]
                    or (runtime.get("review_scope") or {}).get("documents_received") != label["bundle_evidence"]["documents_received"]):
                raise ValueError(f"core_result_bundle_binding_mismatch:{issue_id}")
            gate = core.get("post_llm_gate")
            if not isinstance(gate, dict) or not isinstance(gate.get("response"), dict):
                raise ValueError(f"core_gate_missing:{issue_id}")
            core_status = gate.get("status", "unknown")
            risk_response = deepcopy(gate["response"])
            raw_response = deepcopy(core.get("final_llm_response"))
        else:
            core_status = "not_eligible_unpaired" if label is None else "not_run"
            risk_response = {"findings": [{"issue_id": issue_id, "conclusion_type": "not_yet_assessed",
                "document_excerpt": label["document_excerpt"] if label else issue["primary_source"]["quote"],
                "risk_category": "not_assessed",
                "legal_evidence": [], "assistant_recommendation": "完成法规与招标要求核验后由专业人员复核；当前不得作合规结论。",
                "review_processing_label": "revised"}]}
            raw_response = None
        embedded_handoff = core.get("three_layer_protocol") if core else None
        if embedded_handoff is not None and issue_id in handoffs:
            raise ValueError(f"duplicate_three_layer_source_for_issue:{issue_id}")
        supplement = handoff_for_issue(issue, handoffs.get(issue_id, embedded_handoff), allowed_sources)
        boundary = issue_boundary(issue, coverage)
        for finding in risk_response.get("findings") or []:
            if not isinstance(finding, dict):
                continue
            existing = str(finding.get("evidence_boundary") or "").strip()
            finding["evidence_boundary"] = "\n".join(filter(None, [existing, boundary,
                f"三层交接：{supplement['handoff_status']}；此状态不替代风险判断。"]))
            if issue["task"] == "bid_responsiveness":
                pair = issue.get("pairing") or {}
                paired = pair["candidate_matches"][0]["source"] if pair.get("status") == "provisional_match_needs_verification" else None
                # This is presentation provenance, not a model-generated finding.
                finding["document_excerpt"] = "招标依据：" + fmt_source(issue["primary_source"]) + "\n投标原文：" + fmt_source(paired)
                finding["document_location"] = issue["primary_source"]["source_locator"] + (" / " + paired["source_locator"] if paired else "")
            else:
                finding["document_excerpt"] = fmt_source(issue["primary_source"])
                finding["document_location"] = issue["primary_source"]["source_locator"]
        output.append({
            "issue_id": issue_id, "task": issue["task"], "core_status": core_status,
            "risk_response_raw": raw_response, "risk_response_gated_unmodified": core.get("post_llm_gate") if core else None,
            "presentation_response": risk_response, "three_layer_handoff": supplement,
            "bundle_review": issue, "evidence_boundary": boundary,
            "excel_record": {"issue_id": issue_id, "gate_result": {"status": core_status,
                             "blocked": core_status == "blocked", "response": risk_response}},
        })
    return {"project_id": intake["project_id"], "coverage": coverage,
            "records": output, "core_result_count": sum(row["risk_response_gated_unmodified"] is not None for row in output),
            "three_layer_valid_count": sum(row["three_layer_handoff"]["processing_status"] == "valid" for row in output),
            "all_results_require_human_second_review": True,
            "independent_accuracy": None}


def excel_records(assembled: dict[str, Any]) -> list[dict[str, Any]]:
    records = [row["excel_record"] for row in assembled["records"]]
    for doc in assembled["coverage"]["documents"]:
        notes = []
        pages = doc.get("unreadable_or_empty_physical_pages") or []
        if pages:
            notes.append(f"未成功识别页：{pages}；需要OCR或人工核对。")
        if doc.get("page_locator_limitation"):
            notes.append(doc["page_locator_limitation"])
        skipped = doc.get("not_selected_for_semantic_review_block_ids") or []
        if skipped:
            notes.append(f"已解析但未选入语义审查的块数：{len(skipped)}；完整ID见coverage.json。")
        if not notes:
            continue
        records.append({"issue_id": "COVERAGE-" + doc["document_key"],
            "gate_result": {"status": "review_not_performed", "blocked": False,
                "response": {"findings": [{"issue_id": "COVERAGE-" + doc["document_key"],
                    "conclusion_type": "review_not_performed", "document_excerpt": doc["document_key"],
                    "risk_category": "coverage_notice_not_a_risk_finding", "legal_evidence": [],
                    "evidence_boundary": "\n".join(notes),
                    "assistant_recommendation": "人工补查未审部分；不得把未发现问题当作合规。",
                    "review_processing_label": "revised", "document_location": "coverage ledger"}]}}})
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-output", type=Path, required=True)
    parser.add_argument("--core-results", type=Path)
    parser.add_argument("--pair-results", type=Path)
    parser.add_argument("--handoff-records", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--excel", type=Path, help="Opt-in existing human-review Excel exporter")
    args = parser.parse_args()
    result = assemble(args.bundle_output, args.core_results, args.handoff_records, args.pair_results)
    if args.output.exists() or (args.excel and args.excel.exists()):
        raise FileExistsError("refuse_to_overwrite_existing_review_output")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.excel:
        build_workbook(excel_records(result), args.excel)
    print(json.dumps({"output": str(args.output), "excel": str(args.excel) if args.excel else None,
                      "candidate_count": len(result["records"]), "core_count": result["core_result_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
