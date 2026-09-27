"""Task-bound legal-effect review and typed gaps for full-bundle legal issues.

This supplements the legacy legal verdict; it never supplies a legal verdict by
itself. The prior three-layer candidate remains intact and is the single source
for the dependency/kind and task-relation vocabulary used here.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable


PUBLIC_ROOT = Path(__file__).resolve().parents[1]
if str(PUBLIC_ROOT) not in sys.path:
    sys.path.insert(0, str(PUBLIC_ROOT))

from candidates.three_layer_handoff_v01.spec import (  # noqa: E402
    DEPENDENCIES,
    EXCLUDABLE,
    MATERIAL_PATTERNS,
    RELATION_RULES,
    TASK_MODES,
)


VERSION = "bundle-professional-legal-review-v1"
CLAIM_ID = "CURRENT_CLAUSE_LEGALITY"
TASK_KINDS = {
    "tender_clause_legality": "招标文件当前条款的文本合规性，不推断实际通知、备案或履行已经发生",
    "bid_standalone_legality": "最终投标文件当前条款的文本合规性，不推断提交真实性或后续履行",
}
REQUIRED_DEPENDENCIES = (
    "current_clause_context",
    "applicable_rule",
    "regulatory_applicability",
    "comparison_operand",
    "readability",
)
NORMATIVE_RELATIONS = {
    "implements_or_clarifies", "separate_additional_duty",
    "genuine_norm_conflict", "no_same_obligation_pair", "unresolved",
}
EFFECT_RELATIONS = {
    "aligned_with_reviewed_rule", "concrete_contrary_effect",
    "decisive_gap", "no_admitted_applicable_rule",
}
COMPARISON_ELEMENTS = (
    "actor", "trigger_and_scope", "required_conduct", "timing_or_threshold",
    "exception_or_cure", "obligation_stage",
)
ELEMENT_RELATIONS = {
    "aligned", "concrete_contrary", "not_stated_nonexclusive",
    "unresolved_decisive", "not_applicable", "outside_locked_scope",
}
LEGAL_STATES = {"requires_human_legal_review", "requires_human_legal_confirm"}
NO_ISSUE = "no_supported_issue_found_within_review_scope"
INSUFFICIENT = "insufficient_information_needs_human_confirm"
NO_LAW = "no_applicable_legal_basis_found_needs_human_confirm"


def _sha(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_task_contract(label: dict[str, Any]) -> dict[str, Any] | None:
    """Lock the narrow question before inference; do not infer it from output."""

    if not isinstance(label.get("bundle_evidence"), dict):
        return None
    kind = label.get("review_task_kind")
    if kind not in TASK_KINDS:
        raise ValueError(f"unsupported_bundle_legal_task:{kind}")
    mode = "clause_design"
    contract = {
        "version": VERSION,
        "issue_id": label["issue_id"],
        "review_task_kind": kind,
        "review_mode": mode,
        "review_target": TASK_MODES[mode]["target"],
        "question": TASK_KINDS[kind],
        "required_claims": [{
            "claim_id": CLAIM_ID,
            "required_dependencies": list(REQUIRED_DEPENDENCIES),
        }],
        "excluded_from_this_text_task": list(EXCLUDABLE),
        "document_evidence_id": "CURRENT_DOCUMENT_EXCERPT",
        "input_sha256": _sha({
            "issue_id": label["issue_id"],
            "document_id": label["document_id"],
            "document_location": label["document_location"],
            "document_excerpt": label["document_excerpt"],
            "bundle_evidence": label["bundle_evidence"],
        }),
    }
    contract["contract_sha256"] = _sha(contract)
    return contract


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def selected_chunk_ids(level: dict[str, Any]) -> set[str]:
    """Read both the real cascade decision record and older flat fixtures."""

    phases = level.get("phases")
    if not isinstance(phases, list):
        return set()
    selected: set[str] = set()
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        decision = phase.get("decision")
        ids = decision.get("selected_chunk_ids") if isinstance(decision, dict) else phase.get("selected_chunk_ids")
        if isinstance(ids, list):
            selected.update(value for value in ids if _text(value))
    return selected


def cross_level_pair(runtime_input: dict[str, Any]) -> tuple[set[str], set[str]]:
    levels = {
        row.get("level"): row
        for row in (runtime_input.get("hierarchy_retrieval_audit") or {}).get("levels", [])
        if isinstance(row, dict)
    }
    higher, implementing = levels.get("Level 1") or {}, levels.get("Level 2") or {}
    if (higher.get("level_state") == "relevant_but_inconclusive"
            and implementing.get("level_state") == "no_usable_violation_found"):
        return selected_chunk_ids(higher), selected_chunk_ids(implementing)
    return set(), set()


def _validate_gap(gap: Any, contract: dict[str, Any], seen: set[str]) -> tuple[list[str], str | None]:
    errors: list[str] = []
    if not isinstance(gap, dict):
        return ["gap_not_object"], None
    required = ("gap_id", "kind", "dependency_key", "task_relation", "detail",
                "affected_claim_ids", "reason", "counterfactual_impact",
                "dependency_trigger", "next_step")
    for field in required:
        if field not in gap:
            errors.append(f"gap_missing_{field}")
    if errors:
        return errors, None
    gap_id = gap["gap_id"]
    if not _text(gap_id) or gap_id in seen:
        errors.append("gap_id_invalid_or_duplicate")
    else:
        seen.add(gap_id)
    dep, kind, relation = gap["dependency_key"], gap["kind"], gap["task_relation"]
    if not isinstance(dep, str) or dep not in DEPENDENCIES or kind not in DEPENDENCIES.get(dep, []):
        errors.append("gap_dependency_kind_mismatch")
    if not isinstance(relation, str) or relation not in RELATION_RULES:
        errors.append("gap_task_relation_invalid")
        return errors, None
    affected = gap["affected_claim_ids"]
    if not isinstance(affected, list) or any(not _text(x) for x in affected):
        errors.append("gap_affected_claim_ids_invalid")
        affected = []
    rule = RELATION_RULES[relation]
    if relation == "decisive_for_claim":
        if affected != [CLAIM_ID] or dep not in REQUIRED_DEPENDENCIES:
            errors.append("gap_not_bound_to_required_dependency")
    elif relation == "outside_locked_scope":
        if affected or dep not in contract["excluded_from_this_text_task"]:
            errors.append("out_of_scope_not_authorized")
    elif affected != [CLAIM_ID]:
        errors.append("unresolved_relation_not_bound_to_claim")
    if gap["dependency_trigger"] not in rule["triggers"]:
        errors.append("gap_trigger_relation_mismatch")
    for field in ("detail", "reason", "counterfactual_impact", "next_step"):
        if not _text(gap[field]):
            errors.append(f"gap_{field}_empty")
    detail = gap.get("detail")
    if _text(detail):
        hits = {d for d, pattern in MATERIAL_PATTERNS.items() if re.search(pattern, detail)}
        if len(hits) > 1:
            errors.append("known_mixed_material_requires_split")
        elif hits and dep not in hits:
            errors.append("known_material_dependency_mismatch")
    return errors, rule["group"]


def assess_protocol(
    gate_result: dict[str, Any],
    runtime_input: dict[str, Any],
    legal_admission_predicate: Callable[[dict[str, Any]], bool],
) -> dict[str, Any]:
    """Validate output structure and task relationships, not legal semantics."""

    contract = runtime_input.get("review_task_contract_v1")
    if not isinstance(contract, dict):
        return gate_result
    result = deepcopy(gate_result)
    if result.get("blocked"):
        result["professional_review_v1"] = {
            "status": "upstream_processing_hold", "u_cause_codes": [],
            "legal_semantics_verified": False,
        }
        return result
    findings = (result.get("response") or {}).get("findings") or []
    errors: list[str] = []
    conclusion: Any = None
    groups = {rule["group"]: [] for rule in RELATION_RULES.values()}
    u_causes: list[str] = []
    raw_findings = (result.get("raw_response") or {}).get("findings") if isinstance(result.get("raw_response"), dict) else None
    if not isinstance(raw_findings, list) or len(raw_findings) != 1 or not isinstance(raw_findings[0], dict):
        errors.append("raw_finding_structure_incomplete")
    else:
        raw_finding = raw_findings[0]
        if raw_finding.get("conclusion_type") not in LEGAL_STATES | {NO_ISSUE, INSUFFICIENT, NO_LAW}:
            errors.append("raw_conclusion_schema_invalid_not_legal_u")
        raw_coverage = raw_finding.get("legal_element_coverage")
        coverage_fields = {"subject", "conduct_or_condition", "jurisdiction_and_scope", "legal_consequence"}
        coverage_states = {"supported", "missing", "conflicting", "not_applicable"}
        if (not isinstance(raw_coverage, dict)
                or not coverage_fields <= set(raw_coverage)
                or any(not isinstance(raw_coverage.get(field), str)
                       or raw_coverage.get(field) not in coverage_states
                       for field in coverage_fields)):
            errors.append("raw_legal_element_coverage_incomplete_not_legal_u")
    if len(findings) != 1 or not isinstance(findings[0], dict):
        errors.append("single_finding_required")
    else:
        finding = findings[0]
        analysis = finding.get("professional_review")
        if not isinstance(analysis, dict):
            errors.append("professional_review_missing")
        else:
            if analysis.get("protocol_version") != VERSION:
                errors.append("protocol_version_mismatch")
            if analysis.get("task_contract_sha256") != contract.get("contract_sha256"):
                errors.append("task_contract_binding_mismatch")
            if analysis.get("claim_id") != CLAIM_ID:
                errors.append("claim_binding_mismatch")
            relation = analysis.get("normative_relation")
            effect = analysis.get("legal_effect_relation")
            if not isinstance(relation, str) or relation not in NORMATIVE_RELATIONS:
                errors.append("normative_relation_invalid")
            if not isinstance(effect, str) or effect not in EFFECT_RELATIONS:
                errors.append("legal_effect_relation_invalid")
            for field in ("governing_rule", "implementation_effect", "document_rule", "effect_comparison"):
                if not _text(analysis.get(field)):
                    errors.append(f"{field}_missing")
            norm_elements = analysis.get("normative_elements")
            if not isinstance(norm_elements, dict):
                errors.append("normative_elements_missing")
            else:
                for field in COMPARISON_ELEMENTS:
                    if not _text(norm_elements.get(field)):
                        errors.append(f"normative_{field}_missing")
            ids = analysis.get("applied_legal_chunk_ids")
            evidence_rows = finding.get("legal_evidence")
            if not isinstance(evidence_rows, list):
                errors.append("legal_evidence_not_list")
                evidence_rows = []
            cited = {
                str(row.get("chunk_id"))
                for row in evidence_rows
                if isinstance(row, dict) and row.get("chunk_id")
            }
            admitted = {
                str(row.get("chunk_id"))
                for row in evidence_rows
                if isinstance(row, dict) and row.get("chunk_id")
                and legal_admission_predicate(row)
            }
            if not isinstance(ids, list) or any(not _text(x) for x in ids):
                errors.append("applied_legal_chunk_ids_invalid")
                ids = []
            elif not set(ids) <= cited:
                errors.append("applied_law_not_cited_in_finding")
            if not set(ids) <= admitted:
                errors.append("applied_law_not_admitted_or_applicable")
            element_rows = analysis.get("element_comparisons")
            contrary_elements: list[str] = []
            contrary_quotes: list[str] = []
            unresolved_elements: list[str] = []
            aligned_elements: list[str] = []
            if not isinstance(element_rows, list):
                errors.append("element_comparisons_missing")
                element_rows = []
            seen_elements: set[str] = set()
            excerpt = (runtime_input.get("contract_evidence") or {}).get("document_excerpt") or ""
            for row in element_rows:
                if not isinstance(row, dict):
                    errors.append("element_comparison_not_object")
                    continue
                name, row_relation = row.get("element"), row.get("relation")
                if not isinstance(name, str) or name not in COMPARISON_ELEMENTS or name in seen_elements:
                    errors.append("element_comparison_name_invalid_or_duplicate")
                    continue
                seen_elements.add(name)
                if not isinstance(row_relation, str) or row_relation not in ELEMENT_RELATIONS:
                    errors.append("element_comparison_relation_invalid")
                    continue
                if not _text(row.get("explanation")):
                    errors.append("element_comparison_explanation_missing")
                law_id = row.get("legal_chunk_id")
                if row_relation in {"aligned", "concrete_contrary"} and law_id not in ids:
                    errors.append("element_comparison_law_not_applied")
                if row_relation == "concrete_contrary":
                    contrary_elements.append(name)
                    quote = row.get("document_quote")
                    if not _text(quote) or quote not in excerpt:
                        errors.append("element_contrary_quote_not_in_input")
                    else:
                        contrary_quotes.append(quote)
                if row_relation == "unresolved_decisive":
                    unresolved_elements.append(name)
                if row_relation == "aligned":
                    aligned_elements.append(name)
            if seen_elements != set(COMPARISON_ELEMENTS):
                errors.append("required_element_comparisons_incomplete")
            gaps = analysis.get("gaps")
            if not isinstance(gaps, list):
                errors.append("gap_ledger_missing")
                gaps = []
            seen: set[str] = set()
            for gap in gaps:
                gap_errors, group = _validate_gap(gap, contract, seen)
                errors.extend(gap_errors)
                if not gap_errors and group:
                    groups[group].append(gap["gap_id"])
                    if group == "blocking_gap":
                        u_causes.append(gap["dependency_key"])
            conclusion = finding.get("conclusion_type")
            if conclusion in LEGAL_STATES:
                if effect != "concrete_contrary_effect":
                    errors.append("risk_without_concrete_legal_effect_difference")
                if not contrary_elements:
                    errors.append("risk_without_contrary_legal_element")
                quote = analysis.get("contrary_document_quote")
                if not _text(quote) or quote not in excerpt:
                    errors.append("risk_without_exact_contrary_document_quote")
                elif quote not in contrary_quotes:
                    errors.append("risk_quote_not_bound_to_contrary_element")
                comparison = finding.get("fact_law_comparison")
                if (not isinstance(comparison, dict)
                        or comparison.get("supporting_chunk_id") not in ids
                        or not _text(comparison.get("difference_summary"))):
                    errors.append("risk_difference_not_bound_to_applied_law")
                if groups["blocking_gap"] or groups["scope_review_item"] or unresolved_elements:
                    errors.append("risk_claim_has_decisive_or_unresolved_gap")
            elif conclusion == NO_ISSUE:
                if effect != "aligned_with_reviewed_rule" or not ids:
                    errors.append("no_issue_without_bounded_rule_comparison")
                if not set(aligned_elements) & {
                    "trigger_and_scope", "required_conduct", "timing_or_threshold", "exception_or_cure"
                }:
                    errors.append("no_issue_without_material_element_comparison")
                raw_coverage = raw_findings[0].get("legal_element_coverage") if isinstance(raw_findings, list) and len(raw_findings) == 1 and isinstance(raw_findings[0], dict) else None
                if (not isinstance(raw_coverage, dict)
                        or raw_coverage.get("subject") in ("missing", "conflicting")
                        or raw_coverage.get("conduct_or_condition") in ("missing", "conflicting")):
                    errors.append("no_issue_with_unresolved_core_coverage")
                if contrary_elements:
                    errors.append("no_issue_contradicts_own_element_comparison")
                if groups["blocking_gap"] or groups["scope_review_item"] or unresolved_elements:
                    errors.append("no_issue_has_decisive_or_unresolved_gap")
            elif conclusion in {INSUFFICIENT, NO_LAW}:
                if effect not in {"decisive_gap", "no_admitted_applicable_rule"}:
                    errors.append("u_without_decisive_effect_gap")
                if effect == "no_admitted_applicable_rule" and ids:
                    errors.append("no_admitted_rule_conflicts_with_applied_law")
                if not groups["blocking_gap"]:
                    errors.append("u_without_typed_decisive_gap")
                if not unresolved_elements and effect != "no_admitted_applicable_rule":
                    errors.append("u_without_unresolved_legal_element")
                if groups["scope_review_item"]:
                    errors.append("scope_relation_pending_not_legal_u")
            else:
                errors.append("unsupported_legal_conclusion")
            if relation == "genuine_norm_conflict" and conclusion == NO_ISSUE:
                errors.append("no_issue_despite_unresolved_norm_conflict")
            higher, implementing = cross_level_pair(runtime_input)
            if higher and implementing and conclusion in LEGAL_STATES | {NO_ISSUE}:
                if set(ids).isdisjoint(higher):
                    errors.append("cross_level_governing_article_omitted")
                if set(ids).isdisjoint(implementing):
                    errors.append("cross_level_implementing_article_omitted")
                if conclusion in LEGAL_STATES and relation in {
                    "genuine_norm_conflict", "unresolved", "no_same_obligation_pair"
                }:
                    errors.append("cross_level_relation_unresolved_for_risk")
                if relation == "unresolved":
                    errors.append("cross_level_relation_unresolved_for_conclusion")
                if not any(chunk_id in str(analysis.get("governing_rule") or "") for chunk_id in higher):
                    errors.append("cross_level_governing_rule_not_source_bound")
                if not any(chunk_id in str(analysis.get("implementation_effect") or "") for chunk_id in implementing):
                    errors.append("cross_level_implementation_not_source_bound")
    result["professional_review_v1"] = {
        "status": "valid" if not errors else "protocol_hold",
        "review_mode": contract.get("review_mode"),
        "gap_groups": groups,
        "u_cause_codes": sorted(set(u_causes)) if not errors and conclusion in {INSUFFICIENT, NO_LAW} else [],
        "errors": errors,
        "legal_semantics_verified": False,
    }
    if errors:
        result["status"] = "blocked"
        result["blocked"] = True
        result["actions"] = list(result.get("actions", [])) + [
            "professional_review_v1: " + "; ".join(errors)
        ]
        result["pre_professional_gate_status"] = gate_result.get("status")
    return result


def prompt_addendum() -> str:
    """Generate the bundle-only output instruction from the same vocabulary."""

    dependency_pairs = json.dumps(DEPENDENCIES, ensure_ascii=False, sort_keys=True)
    excludable = json.dumps(EXCLUDABLE, ensure_ascii=False)
    return f"""

## Task-bound professional legal-effect analysis ({VERSION})
The runtime `review_task_contract_v1` is caller-locked. Copy its
`contract_sha256` exactly; do not narrow or expand its review question.
Use an evidence-constrained legal analysis, not word overlap: identify the
regulated actor, trigger/scope, required conduct, timing, exception or lawful
remedy, and the stage when the duty operates. Read Level 1 as governing law;
read Level 2 as implementing detail when it addresses the same obligation.
Check Level 3 independently for any additional applicable duty. Explain the
legal effect of the document clause and compare effects only within the locked
task. A clause's silence about performance records or a non-exclusive duty is
not proof of nonperformance or contradiction.
If review_scope.project_location_evidence_status is
`provided_pending_confirmation`, the place is known but its provenance is
unconfirmed: do not describe it as "location absent". A located project
document can establish the place only through the existing applicability
gate; do not promote any Level 4 candidate merely from this display label.

For example, if a governing law requires written notice at least 15 days
before a deadline and an implementing regulation directs extension of the
deadline when a late change affects preparation, a tender clause requiring
that extension does not contradict the 15-day protection merely because it
mentions the original deadline. Review the effective extended deadline,
recipients and actual notices as separate conduct questions. Conversely,
an express instruction to make the affecting change without extension can be
a concrete text-level risk. Do not use this example to ignore an express
recipient exclusion, an independent applicable duty, or a contrary record.

For the one finding, add `professional_review` with exactly these fields:
{{
  "protocol_version": "{VERSION}",
  "task_contract_sha256": "copy review_task_contract_v1.contract_sha256",
  "claim_id": "{CLAIM_ID}",
  "applied_legal_chunk_ids": ["only supplied and cited chunk IDs"],
  "normative_elements": {{
    "actor": "regulated actor or not established",
    "trigger_and_scope": "applicability conditions and event",
    "required_conduct": "substantive duty",
    "timing_or_threshold": "time/threshold or none in cited rule",
    "exception_or_cure": "lawful exception/remedy or none in cited rule",
    "obligation_stage": "clause design, submission, procedure or performance"
  }},
  "element_comparisons": [{{
    "element": "one of {', '.join(COMPARISON_ELEMENTS)}; each exactly once",
    "relation": "{' | '.join(sorted(ELEMENT_RELATIONS))}",
    "legal_chunk_id": "applied chunk ID for aligned/concrete_contrary; else empty",
    "document_quote": "exact current excerpt substring for concrete_contrary; else empty",
    "explanation": "legal element -> clause effect -> why relation holds"
  }}],
  "governing_rule": "higher-level legal effect with chunk IDs",
  "normative_relation": "{' | '.join(sorted(NORMATIVE_RELATIONS))}",
  "implementation_effect": "what lower-level rule specifies with its chunk ID, or why none applies",
  "document_rule": "what the supplied clause legally requires/allows, including its conditions",
  "legal_effect_relation": "{' | '.join(sorted(EFFECT_RELATIONS))}",
  "effect_comparison": "rule effect -> document effect -> material equivalence/difference -> boundary",
  "contrary_document_quote": "exact excerpt substring only for a concrete risk; otherwise empty",
  "gaps": [{{
    "gap_id": "G1", "kind": "one material type from dependency_kind_pairs",
    "dependency_key": "one dependency from the locked contract",
    "task_relation": "decisive_for_claim | outside_locked_scope | undetermined",
    "affected_claim_ids": ["{CLAIM_ID} when decisive/undetermined; else empty"],
    "detail": "one missing material only",
    "reason": "why this material is relevant to this task",
    "counterfactual_impact": "which exact judgment changes if supplied",
    "dependency_trigger": "locked_requirement | observed_context_conflict | explicit_scope_exclusion | generic_unverified_possibility | undetermined",
    "next_step": "specific human check"
  }}]
}}
Use the existing three-layer dependency/kind pairs and task-relation rules.
Permitted dependency_key -> kind pairs: {dependency_pairs}
Outside-scope exclusions permitted for this text task: {excludable}.
Use `locked_requirement` for a decisive gap only if the caller-locked claim
requires that dependency; use `explicit_scope_exclusion` for a pure excluded
follow-up. Split mixed materials into separate gaps.
Keep top-level `legal_element_coverage`, `compliance_relation`,
`fact_law_comparison` and `conclusion_type` consistent with the element
comparison. An aligned text-level finding is bounded to this excerpt and
admitted rules, not a declaration that actual notification, filing or later
performance occurred. A concrete risk needs an opposite excerpt quote and
an admitted rule; `fact_law_comparison` must describe their legal-effect
difference, not merely name an article. If a decisive current-task input is
missing, mark the affected legal element unresolved and specify its typed gap.
Do not label a known project location as missing just because its scope
confirmation is pending.
For U, at least one `decisive_for_claim` gap must identify a missing input,
applicable rule, applicability condition, comparison operand or readability
that blocks THIS claim. An outside-scope follow-up never makes legal U.
If the relation is undetermined, request scope clarification rather than
asserting U or N. Malformed/partial output is processing failure, not legal U.
Keep `reasoning_conclusion` consistent with this structured comparison.
"""
