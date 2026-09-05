"""Shared conclusion-state contract for the Stage 3 decision gate.

The new contract separates an explicit, runtime-validated legal conflict from
an ordinary potential risk.  Legacy values remain accepted at the input
boundary so that frozen Stage 2 artefacts can be replayed without editing
their raw outputs.  They are canonicalised before a Stage 3 result is
delivered.

The legacy three-class mapping is intentionally kept in this small shared
module.  Downstream evaluators can compare historical metrics without
silently treating the new confirmation state as a fourth historical class.
"""

from __future__ import annotations

from typing import Any


CONCLUSION_CONTRACT_VERSION = "v2"

REQUIRES_HUMAN_LEGAL_CONFIRM = "requires_human_legal_confirm"
REQUIRES_HUMAN_LEGAL_REVIEW = "requires_human_legal_review"
INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM = (
    "insufficient_information_needs_human_confirm"
)
NO_APPLICABLE_LEGAL_BASIS_NEEDS_HUMAN_CONFIRM = (
    "no_applicable_legal_basis_found_needs_human_confirm"
)
NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE = (
    "no_supported_issue_found_within_review_scope"
)

CANONICAL_CONCLUSION_STATES = (
    REQUIRES_HUMAN_LEGAL_CONFIRM,
    REQUIRES_HUMAN_LEGAL_REVIEW,
    INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM,
    NO_APPLICABLE_LEGAL_BASIS_NEEDS_HUMAN_CONFIRM,
    NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE,
)

# These values have appeared in the frozen prompt, Stage 2 responses, or
# earlier user-reviewed drafts.  They are input aliases only.  In particular,
# ``potential_risk`` must not remain a final v2 conclusion when evidence is
# available, and ``insufficient_information`` must gain the human-confirm
# suffix in a canonical Stage 3 output.
LEGACY_CONCLUSION_ALIASES = {
    "requires_human_legal_confirm": REQUIRES_HUMAN_LEGAL_CONFIRM,
    "requires_human_legal_review": REQUIRES_HUMAN_LEGAL_REVIEW,
    "potential_risk": REQUIRES_HUMAN_LEGAL_REVIEW,
    "insufficient_information": INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM,
    "insufficient_information_needs_human_confirm": (
        INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM
    ),
    "no_applicable_legal_basis_found": (
        NO_APPLICABLE_LEGAL_BASIS_NEEDS_HUMAN_CONFIRM
    ),
    "no_applicable_legal_basis_found_needs_human_confirm": (
        NO_APPLICABLE_LEGAL_BASIS_NEEDS_HUMAN_CONFIRM
    ),
    "valid_needs_human_confirm": INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM,
    "no_supported_issue_found_within_review_scope": (
        NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE
    ),
}

# Exact historical table labels used by the Stage 2 review table.  The new
# confirmation and review states intentionally share the old risk-supported
# bucket for table-level comparisons.
LEGACY_THREE_CLASS_MAPPING = {
    REQUIRES_HUMAN_LEGAL_CONFIRM: "risk_supported",
    REQUIRES_HUMAN_LEGAL_REVIEW: "risk_supported",
    INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM: "insufficient_information",
    NO_APPLICABLE_LEGAL_BASIS_NEEDS_HUMAN_CONFIRM: "insufficient_information",
    NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE: "no_supported_issue_found",
}

# The frozen evaluator compares ``conclusion_type`` values, not table labels.
# Keep this mapping separate so a workbook label such as ``risk_supported`` is
# never accidentally written into the evaluator's old conclusion enum field.
LEGACY_THREE_CLASS_CONCLUSION_MAPPING = {
    REQUIRES_HUMAN_LEGAL_CONFIRM: REQUIRES_HUMAN_LEGAL_REVIEW,
    REQUIRES_HUMAN_LEGAL_REVIEW: REQUIRES_HUMAN_LEGAL_REVIEW,
    INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM: "insufficient_information",
    NO_APPLICABLE_LEGAL_BASIS_NEEDS_HUMAN_CONFIRM: "insufficient_information",
    NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE: NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE,
}

LEGACY_THREE_CLASS_LABELS = (
    "risk_supported",
    "no_supported_issue_found",
    "insufficient_information",
)


def canonicalize_conclusion_type(value: Any) -> str | None:
    """Return a v2 conclusion state for a legacy or canonical input value.

    Unknown values return ``None``.  The gate then decides whether the finding
    must abstain or be repaired; this helper never invents a legal conclusion.
    """

    if not isinstance(value, str):
        return None
    return LEGACY_CONCLUSION_ALIASES.get(value.strip())


def was_legacy_conclusion_alias(value: Any) -> bool:
    """Whether *value* is accepted but differs from its canonical v2 value."""

    canonical = canonicalize_conclusion_type(value)
    return canonical is not None and value != canonical


def legacy_three_class_label(value: Any) -> str | None:
    """Map a v2/legacy finding conclusion to the exact Stage 2 class.

    A gate-level ``blocked`` result has no finding-level semantic class and
    therefore returns ``None``.  Existing evaluators can count it separately
    as a schema/gate failure rather than silently folding it into a legal
    finding class.
    """

    canonical = canonicalize_conclusion_type(value)
    if canonical is None:
        return None
    return LEGACY_THREE_CLASS_MAPPING.get(canonical)


def legacy_three_class_conclusion(value: Any) -> str | None:
    """Map a v2 state to the frozen evaluator's old conclusion enum.

    This is deliberately different from :func:`legacy_three_class_label`,
    which returns the human-facing table buckets ``risk_supported`` and
    ``no_supported_issue_found``.  Gate-level ``blocked`` has no finding-level
    conclusion enum and returns ``None``.
    """

    canonical = canonicalize_conclusion_type(value)
    if canonical is None:
        return None
    return LEGACY_THREE_CLASS_CONCLUSION_MAPPING.get(canonical)


def legacy_test_result(value: Any) -> str:
    """Return the historical table label, including the separate blocked case."""

    label = legacy_three_class_label(value)
    return label if label is not None else "blocked"


def is_risk_conclusion(value: Any) -> bool:
    canonical = canonicalize_conclusion_type(value)
    return canonical in {
        REQUIRES_HUMAN_LEGAL_CONFIRM,
        REQUIRES_HUMAN_LEGAL_REVIEW,
    }


def is_insufficient_conclusion(value: Any) -> bool:
    canonical = canonicalize_conclusion_type(value)
    return canonical in {
        INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM,
        NO_APPLICABLE_LEGAL_BASIS_NEEDS_HUMAN_CONFIRM,
    }


def is_no_issue_conclusion(value: Any) -> bool:
    return canonicalize_conclusion_type(value) == (
        NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE
    )


def is_confirmation_conclusion(value: Any) -> bool:
    return canonicalize_conclusion_type(value) == REQUIRES_HUMAN_LEGAL_CONFIRM
