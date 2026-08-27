#!/usr/bin/env python
"""Deterministic policy checks for the MinerU two-tier retrieval admission."""

from __future__ import annotations

import json
from pathlib import Path

from mineru_source_locator_adapter import (
    RETRIEVAL_ADMISSION_EXCLUDED,
    RETRIEVAL_ADMISSION_HIGH_TRUST,
    RETRIEVAL_ADMISSION_SUPPLEMENT,
    SUPPLEMENT_LLM_WARNING,
    assign_retrieval_admission,
)


def block(method: str) -> dict:
    return {"mapping": {"mapping_method": method}}


def main() -> None:
    checks = [
        (
            "tier1_reliable_block",
            assign_retrieval_admission(block("exact_block"), 0.80, "needs_human_review"),
            RETRIEVAL_ADMISSION_HIGH_TRUST,
        ),
        (
            "tier1_anchor_block",
            assign_retrieval_admission(block("anchor_match"), 0.92, "needs_human_review"),
            RETRIEVAL_ADMISSION_HIGH_TRUST,
        ),
        (
            "tier2_unmapped_block",
            assign_retrieval_admission(block("unmapped"), 0.60, "needs_human_review"),
            RETRIEVAL_ADMISSION_SUPPLEMENT,
        ),
        (
            "tier2_unmapped_upper_boundary",
            assign_retrieval_admission(block("unmapped"), 0.7999, "needs_human_review"),
            RETRIEVAL_ADMISSION_SUPPLEMENT,
        ),
        (
            "tier2_mapped_block_not_promoted",
            assign_retrieval_admission(block("anchor_match"), 0.70, "needs_human_review"),
            RETRIEVAL_ADMISSION_EXCLUDED,
        ),
        (
            "below_tier2_unmapped_block",
            assign_retrieval_admission(block("unmapped"), 0.59, "needs_human_review"),
            RETRIEVAL_ADMISSION_EXCLUDED,
        ),
    ]
    failures = []
    result = []
    for name, admission, expected in checks:
        actual = admission["retrieval_admission"]
        passed = actual == expected
        if not passed:
            failures.append(name)
        result.append({"check": name, "expected": expected, "actual": actual, "pass": passed})
    supplement = assign_retrieval_admission(block("unmapped"), 0.70, "needs_human_review")
    warning_ok = supplement["llm_warning"] == SUPPLEMENT_LLM_WARNING and not supplement["independent_evidence"] and supplement["human_review_required_if_used"]
    result.append({"check": "supplement_warning_and_review_flags", "pass": warning_ok})
    if not warning_ok:
        failures.append("supplement_warning_and_review_flags")
    output = {
        "policy": "MinerU two-tier retrieval admission",
        "checks": result,
        "status": "pass" if not failures else "fail",
        "failures": failures,
    }
    path = Path(__file__).resolve().parents[1] / "benchmarks" / "ocr" / "mineru_retrieval_admission_policy_v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not failures else 1)


if __name__ == "__main__":
    main()
