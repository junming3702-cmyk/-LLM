"""Input-only task-contract audit for the opt-in evidence-lineage candidate.

This is a conservative finite cue check, not Chinese legal interpretation.  A
negative phrase never edits the locked task; mismatches require human scope
review before inference.  In particular, a negated authenticity check is not
silently promoted into a positive actual-verification task.
"""

from __future__ import annotations

import re
from typing import Any

VERSION = "task-scope-audit-v2-candidate"
_CLAUSE = re.compile(r"[，,。；;！？!?\n]")
_CUES = {
    "authenticity": re.compile(r"(?:核验|核实|审查|检查|确认|判断).{0,12}?(?:业绩|证件|材料|人员)?真实性|真伪"),
    "submission_package_completeness": re.compile(r"(?:核验|核实|检查|确认|判断).{0,12}?(?:实际)?(?:提交|递交|送达|齐全)|是否(?:已|实际)(?:提交|递交|送达)"),
    "actual_performance": re.compile(r"(?:核验|核实|检查|确认|判断).{0,12}?(?:实际履行|实际到岗)|实际履行|实际到岗"),
}
_NEGATION = re.compile(r"(?:不|无需|无须|不需|不必|暂不|不再|不应|不得)(?:另行|进一步|再次|再)?$")
_DOUBLE = re.compile(r"不能不|不得不|并非不|不是不|不应不|不可不|无需不|无须不|不必不")
_CONDITIONAL = re.compile(r"如果|除非|假如|倘若|若需|如需|视情况")
_QUOTES = set("“”「」『』\"")


def _clause_start(question: str, position: int) -> int:
    return max((m.end() for m in _CLAUSE.finditer(question, 0, position)), default=0)


def audit_task(task: dict[str, Any]) -> dict[str, Any]:
    """Return a pre-inference scope decision without changing the task."""
    question = task.get("question")
    if not isinstance(question, str) or not question.strip():
        return {"version": VERSION, "status": "needs_scope_review", "issues": ["missing_locked_question"], "signals": []}
    exclusions = task.get("excluded_dependencies", [])
    claims = task.get("required_claims", [])
    if (not isinstance(exclusions, list) or not isinstance(claims, list)
            or any(not isinstance(x, str) for x in exclusions)):
        return {"version": VERSION, "status": "needs_scope_review", "issues": ["invalid_task_contract"], "signals": []}
    exclusion_set = set(exclusions)
    signals: list[dict[str, Any]] = []
    issues: list[str] = []
    for dependency, pattern in _CUES.items():
        for match in pattern.finditer(question):
            start = _clause_start(question, match.start())
            clause = question[start:next((m.start() for m in _CLAUSE.finditer(question, match.end())), len(question))]
            prefix = question[start:match.start()]
            negated = bool(_NEGATION.search(prefix[-12:]))
            ambiguous = bool(_DOUBLE.search(clause) or _CONDITIONAL.search(clause) or any(q in clause for q in _QUOTES))
            polarity = "unresolved" if ambiguous else "excluded" if negated else "active"
            signals.append({"dependency": dependency, "cue": match.group(), "span": [match.start(), match.end()], "polarity": polarity})
            if polarity == "unresolved":
                issues.append(f"ambiguous_question_scope:{dependency}")
            elif polarity == "excluded" and dependency not in exclusion_set:
                issues.append(f"question_exclusion_not_locked:{dependency}")
            elif polarity == "active" and dependency in exclusion_set:
                issues.append(f"active_question_dependency_excluded:{dependency}")
    for claim in claims:
        if (not isinstance(claim, dict) or not isinstance(claim.get("required_dependencies"), list)
                or any(not isinstance(x, str) for x in claim["required_dependencies"])):
            issues.append("invalid_required_claim")
            continue
        for dependency in claim["required_dependencies"]:
            if dependency in exclusion_set:
                issues.append(f"required_dependency_excluded:{claim.get('claim_id', '?')}:{dependency}")
    mode = task.get("review_mode")
    if mode in ("clause_design", "text_response_comparison"):
        for signal in signals:
            if signal["polarity"] == "active":
                issues.append(f"actual_verification_cue_in_text_task:{signal['dependency']}")
    elif mode == "actual_submission_check" and "submission_package_completeness" in exclusion_set:
        issues.append("submission_task_excludes_its_own_subject")
    # A missing cue is not proof that an explicit task dependency is absent.
    return {"version": VERSION, "status": "needs_scope_review" if issues else "task_contract_consistent",
            "issues": sorted(set(issues)), "signals": signals,
            "locked_task_unchanged": True, "semantic_task_correctness_verified": False}
