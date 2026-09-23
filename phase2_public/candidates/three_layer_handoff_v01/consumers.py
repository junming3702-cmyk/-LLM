"""Shared view projection, no U/N/R coercion, no historical workbook edits."""
from collections import Counter
import json
import html
from spec import VERSION

COLUMNS = ["case_id", "claim_id", "claim_state", "finding", "question_completion",
           "handoff_status", "claim_gap_ids", "question_blocking_gap_ids", "human_review_required",
           "joint_handoff_effectiveness", "processing_status", "processing_reasons"]
def assert_candidate(result):
    if result.get("protocol_version") != VERSION:
        raise ValueError("unsupported_candidate_protocol")
    if result.get("human_review_required") is not True:
        raise ValueError("human_review_guard_missing")
    if result.get("joint_handoff_effectiveness") is not None or result.get("legacy_legal_verdict") is not None:
        raise ValueError("unapproved_effectiveness_or_legacy_projection")

def review_rows(case_id, result):
    assert_candidate(result)
    rows = []
    claims = result["claim_states"] or [None]
    for c in claims:
        rows.append({
            "case_id": case_id, "claim_id": c["claim_id"] if c else "",
            "claim_state": c["assessment_state"] if c else "不可计算",
            "finding": c["finding"] if c else None,
            "question_completion": result["question_completion"],
            "handoff_status": result["handoff_status"],
            "claim_gap_ids": list(c["gap_ids"]) if c else [],
            "question_blocking_gap_ids": list(result["gap_groups"]["blocking_gap"]),
            "human_review_required": True, "joint_handoff_effectiveness": None,
            "processing_status": result["processing_status"],
            "processing_reasons": result["technical_errors"] + [e["code"] for e in result["errors"]],
        })
    return rows

def excel_projection(case_id, result):
    """Canonical typed projection; actual new-protocol XLSX lives in export_review.py."""
    rows = review_rows(case_id, result)
    return [COLUMNS] + [[json.dumps(row[k], ensure_ascii=False) if isinstance(row[k], list) else row[k]
                        for k in COLUMNS] for row in rows]

def markdown(case_id, result):
    def cell(v):
        if v is None:
            return "未评/不可计算"
        return html.escape(str(v)).replace("|", r"\|").replace("\n", "<br>")
    grid = excel_projection(case_id, result)
    return "\n".join(["全部结果需人工二次审核；ready不等于法律正确或联合交接有效。",
                       "", "| " + " | ".join(grid[0]) + " |",
                       "|" + "|".join(["---"] * len(COLUMNS)) + "|"] +
                      ["| " + " | ".join(cell(v) for v in row) + " |" for row in grid[1:]])

def to_legacy_verdict_or_workbook(*args, **kwargs):
    raise ValueError("new_protocol_requires_new_consumer_do_not_project_U_or_N")

def summary(results):
    for r in results:
        assert_candidate(r)
    return {
        "execution_denominator": len(results),
        "raw_structure_valid": sum(r["raw_structure_valid"] for r in results),
        "normalized_structure_valid": sum(r["normalized_structure_valid"] for r in results),
        "processing_status_counts": dict(Counter(r["processing_status"] for r in results)),
        "completion_counts": dict(Counter(str(r["question_completion"]) for r in results)),
        "handoff_presentation_counts": dict(Counter(r["handoff_status"] for r in results)),
        "legal_accuracy": None, "expert_agreement": None, "joint_handoff_effectiveness": None,
        "denominator_is_software_fixtures_not_real_cases": True,
    }
