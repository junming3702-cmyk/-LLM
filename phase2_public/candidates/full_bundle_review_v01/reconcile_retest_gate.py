"""Re-apply the cross-level delivery guard to an immutable completed batch.

No model, embedding, network, or source-document call is made. Original
responses remain in the input directory; this writes only a compact ledger.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from run_hierarchy_gated_llm_smoke import require_cross_level_reconciliation  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def usage_total(record: dict) -> int:
    return int((record.get("usage") or {}).get("total_tokens") or 0)


def model_usage(record: dict) -> tuple[int, int]:
    calls = 0
    tokens = 0
    for level in record.get("cascade_execution_audit", []):
        for phase in level.get("phases", []):
            response = phase.get("llm_response")
            if isinstance(response, dict):
                calls += 1
                tokens += usage_total(response)
    preliminary = record.get("preliminary_llm_response")
    if isinstance(preliminary, dict):
        calls += 1
        tokens += usage_total(preliminary)
    if (record.get("external_recheck") or {}).get("final_reasoning_rerun"):
        response = record.get("final_llm_response")
        if isinstance(response, dict):
            calls += 1
            tokens += usage_total(response)
    return calls, tokens


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("refuse_to_overwrite_existing_reconciliation_ledger")
    audit_file = args.input_dir / "batch_audit.json"
    batch = json.loads(audit_file.read_text(encoding="utf-8"))
    rows = []
    for entry in batch.get("completed", []):
        issue_id = entry["issue_id"]
        path = args.input_dir / entry["route"] / f"{issue_id}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        old_gate = record["post_llm_gate"]
        new_gate = require_cross_level_reconciliation(old_gate, record["runtime_input"])
        old_findings = (old_gate.get("response") or {}).get("findings") or []
        calls, tokens = model_usage(record)
        rows.append({
            "issue_id": issue_id,
            "original_result_sha256": sha256(path),
            "original_gate_status": old_gate.get("status"),
            "original_conclusion": old_findings[0].get("conclusion_type") if old_findings else None,
            "reconciled_gate_status": new_gate.get("status"),
            "reconciled_blocked": bool(new_gate.get("blocked")),
            "deliverable_conclusion": None if new_gate.get("blocked") else
                (old_findings[0].get("conclusion_type") if old_findings else None),
            "reconciliation_reason": (new_gate.get("cross_level_reconciliation") or {}).get("reason", ""),
            "final_finish_reason": (record.get("final_llm_response") or {}).get("finish_reason"),
            "model_calls": calls,
            "model_total_tokens": tokens,
            "external_http_calls": int((record.get("external_retrieval_audit") or {}).get("http_call_count") or 0),
            "external_search_status": (record.get("external_retrieval_audit") or {}).get("external_search_status"),
            "external_recheck_attempted": bool((record.get("external_recheck") or {}).get("attempted")),
        })
    result = {
        "schema": "full_bundle_formal_retest_reconciliation_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_batch_audit_sha256": sha256(audit_file),
        "method": "offline_cross_level_delivery_guard_only_no_model_call",
        "approved_count": batch.get("approved_count"),
        "completed_count": len(rows),
        "failed_count": len(batch.get("failed", [])),
        "deliverable_conclusion_counts": dict(Counter(row["deliverable_conclusion"] or "blocked" for row in rows)),
        "total_model_calls": sum(row["model_calls"] for row in rows),
        "total_model_tokens": sum(row["model_total_tokens"] for row in rows),
        "total_external_http_calls": sum(row["external_http_calls"] for row in rows),
        "rows": rows,
        "not_a_whole_bundle_accuracy_test": True,
        "winning_bid_or_award_not_used_as_ground_truth": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in (
        "completed_count", "failed_count", "deliverable_conclusion_counts",
        "total_model_calls", "total_model_tokens", "total_external_http_calls"
    )}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
