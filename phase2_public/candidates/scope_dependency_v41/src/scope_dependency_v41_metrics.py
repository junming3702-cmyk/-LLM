"""Descriptive protocol/delivery counters; never expert/legal accuracy."""
from collections import Counter


def summarize_protocol_batch(gate_results):
    records = list(gate_results)
    raw_pass = normalized_pass = findings = raw_findings_pass = normalized_findings_pass = 0
    diagnostics_missing = normalizer_enabled = normalizer_changed = valid_verdicts = 0
    delivery = Counter()
    for result in records:
        d = result.get("protocol_diagnostics") if isinstance(result, dict) else None
        if not isinstance(d, dict):
            diagnostics_missing += 1
            delivery["diagnostics_unavailable"] += 1
            continue
        raw, normalized = d["raw"], d["normalized"]
        raw_pass += raw["valid"] is True
        normalized_pass += normalized["valid"] is True
        normalizer_enabled += d["enabled"] is True
        normalizer_changed += bool(d["actions"])
        findings += len(raw["findings"])
        raw_findings_pass += sum(not row["errors"] for row in raw["findings"])
        normalized_findings_pass += sum(not row["errors"] for row in normalized["findings"])
        response = result.get("response") or {}
        rows = response.get("findings") or [] if isinstance(response, dict) else []
        if not rows:
            delivery["no_deliverable_finding"] += 1
        for row in rows:
            if isinstance(row, dict):
                delivery[(row.get("nu_boundary_audit") or {}).get("processing_status", "not_evaluated")] += 1
        valid_verdicts += len(result.get("valid_legal_verdicts") or [])
    total = len(records)
    return {
        "responses_total_including_parse_failures": total,
        "raw_protocol_conformant_responses": raw_pass,
        "normalized_protocol_conformant_responses": normalized_pass,
        "raw_protocol_conformance_rate": raw_pass / total if total else None,
        "normalized_protocol_conformance_rate": normalized_pass / total if total else None,
        "diagnostics_unavailable_responses": diagnostics_missing,
        "observed_findings_denominator": findings,
        "raw_protocol_conformant_findings": raw_findings_pass,
        "normalized_protocol_conformant_findings": normalized_findings_pass,
        "normalizer_enabled_responses": normalizer_enabled,
        "normalizer_changed_responses": normalizer_changed,
        "delivery_status_counts": dict(delivery),
        "valid_legal_verdict_count_not_accuracy": valid_verdicts,
        "boundary": "Protocol and delivery counters only. No legal correctness, expert agreement or independent effectiveness estimate. Finding counts cannot account for missing expected findings without a separate input manifest.",
    }
