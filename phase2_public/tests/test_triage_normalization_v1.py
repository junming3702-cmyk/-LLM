"""Regression tests for semantic consistency in triage state normalization."""

from __future__ import annotations

from run_hierarchy_gated_llm_smoke import normalize_triage


CANDIDATES = [{"chunk_id": "law-1"}]


def main() -> int:
    compliant = normalize_triage(
        {
            "parsed": {
                "level_state": "violation_or_inconsistency_detected",
                "selected_chunk_ids": ["law-1"],
                "reason": "期限共21天，满足不少于20日的要求，因此未发现不一致。",
                "missing_elements": [],
                "confidence": "high",
            }
        },
        CANDIDATES,
        phase="primary",
    )
    assert compliant["level_state"] == "no_usable_violation_found"
    assert "contradictory_violation_state_corrected_from_explicit_satisfaction_reason" in compliant["normalization_actions"]

    risk = normalize_triage(
        {
            "parsed": {
                "level_state": "violation_or_inconsistency_detected",
                "selected_chunk_ids": ["law-1"],
                "reason": "期限不满足法定要求，构成违规。",
                "missing_elements": [],
                "confidence": "high",
            }
        },
        CANDIDATES,
        phase="primary",
    )
    assert risk["level_state"] == "violation_or_inconsistency_detected"
    print("triage normalization fixtures: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
