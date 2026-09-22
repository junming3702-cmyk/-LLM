"""Explicit, opt-in task-dependency candidate. Never an independent legal oracle.

Scope specifications are trusted caller configuration prepared before inference,
not model output. A digest binds configuration and input; it is not a signature
or evidence of human approval. There are no case IDs or reference-answer rules.
"""
from copy import deepcopy
import re

from review_task_contract_v2 import digest, _binding, source_spans, evidence_binding_errors
from question_scope_signals import factual_question_audit
from exact_citation_fragments import check_document_binding

VERSION = "scope-dependency-v4-candidate"
TEXT_MODES = {"clause_design", "text_response_comparison"}
TARGETS = {"clause_design": "textual_pre_review", "text_response_comparison": "document_response",
           "actual_submission_check": "document_completeness", "actual_conduct_check": "actual_conduct"}
KINDS = {
    "submission_package_completeness": {"input_evidence_missing", "required_document_missing"},
    "authenticity": {"authenticity_unverified"},
    "actual_performance": {"future_performance_unverified"},
    "current_clause_context": {"input_evidence_missing", "required_document_missing"},
    "applicable_rule": {"key_legal_source_missing"},
    "regulatory_applicability": {"decisive_applicability_missing"},
    "comparison_operand": {"comparison_value_missing"},
    "readability": {"unreadable_evidence"},
    "other_undetermined": {"input_evidence_missing", "required_document_missing", "other_outside_question"},
}
CORE = {"applicable_rule", "regulatory_applicability", "comparison_operand", "readability", "current_clause_context"}
EXCLUDABLE = {"submission_package_completeness", "authenticity", "actual_performance"}


def validate_spec(runtime, spec):
    errors = []
    if not isinstance(spec, dict):
        return ["scope_spec_missing"]
    question = _binding(runtime)["question"]
    if not question or spec.get("question_verbatim") != question:
        errors.append("scope_spec_question_mismatch")
    mode = spec.get("review_mode")
    if not isinstance(mode, str) or mode not in TARGETS:
        errors.append("invalid_scope_mode")
        mode = "invalid"
    if not isinstance(spec.get("scope_basis"), str) or not spec["scope_basis"].strip():
        errors.append("scope_basis_missing")
    excluded = spec.get("excluded_dependencies")
    if not isinstance(excluded, list) or any(not isinstance(x, str) or x not in EXCLUDABLE for x in excluded):
        errors.append("invalid_scope_exclusion")
        excluded = []
    if mode not in TEXT_MODES and excluded:
        errors.append("factual_task_cannot_use_text_exclusions")
    intent = factual_question_audit(str(question))
    if mode in TEXT_MODES and (intent["has_active_factual_cue"] or intent["ambiguity_requires_review"]):
        errors.append("text_scope_conflicts_with_positive_or_ambiguous_factual_question")
    stage = re.split(r"[:：]", str(_binding(runtime)["document_stage"]), maxsplit=1)[0].strip()
    expected_stages = {"clause_design": {"clause_pre_review"},
                       "text_response_comparison": {"document_response"},
                       "actual_submission_check": {"document_completeness"},
                       "actual_conduct_check": {"performance_verification", "actual_conduct"}}
    if mode in expected_stages and stage not in expected_stages[mode]:
        errors.append("scope_mode_stage_conflict")
    claims = spec.get("required_claims")
    seen = set()
    if not isinstance(claims, list) or not claims:
        errors.append("required_claims_missing")
        claims = []
    for claim in claims:
        if not isinstance(claim, dict):
            errors.append("invalid_claim"); continue
        cid = claim.get("claim_id")
        deps = claim.get("required_dependencies")
        if not isinstance(cid, str) or not cid.strip() or cid in seen:
            errors.append("invalid_or_duplicate_claim_id")
        else:
            seen.add(cid)
        if not isinstance(claim.get("description"), str) or not claim["description"].strip():
            errors.append("claim_description_missing")
        if not isinstance(deps, list) or not deps or any(not isinstance(x, str) or x not in KINDS for x in deps):
            errors.append("invalid_claim_dependencies")
        elif set(deps) & set(excluded):
            errors.append("required_dependency_excluded")
    return errors


def build_contract(runtime, spec):
    errors = validate_spec(runtime, spec)
    if errors:
        raise ValueError("; ".join(errors))
    payload = {"version": VERSION, "input": _binding(runtime),
               "project_context": runtime.get("project_context") or runtime.get("runtime_project_context") or {},
               "scope_spec": deepcopy(spec)}
    return {"version": VERSION, "input_scope_sha256": digest(payload),
            "scope_spec": deepcopy(spec), "origin": "trusted_caller_before_inference",
            "human_approval_inferred": False, "input_completeness_certified": False}


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def resolve_gap(gap, spec):
    """Fail closed on mixed, unknown, or decisive dependencies; never trust false alone."""
    result = {"dependency_key": gap.get("dependency_key"), "detail": gap.get("detail"),
              "original_kind": gap.get("kind"), "model_blocks": gap.get("blocks_current_question"),
              "affected_claim_ids": gap.get("affected_claim_ids"),
              "resolution": "blocking_gap", "reason": "no_verified_exclusion"}
    dep = gap.get("dependency_key")
    if not isinstance(dep, str):
        result["reason"] = "invalid_dependency_key"
        return result
    if dep in CORE:
        result["reason"] = "current_rule_fact_or_interpretation_dependency_preserved"
        return result
    if gap.get("blocks_current_question") is not False:
        result["reason"] = "model_reports_blocking_or_invalid_flag"
        return result
    if spec.get("review_mode") not in TEXT_MODES or dep not in spec.get("excluded_dependencies", []):
        return result
    if gap.get("affected_claim_ids") != [] or gap.get("kind") not in KINDS.get(dep, set()):
        result["reason"] = "affected_claim_or_kind_conflicts_with_exclusion"
        return result
    detail = str(gap.get("detail") or "") + " " + str(gap.get("reason") or "")
    # A conservative language guard supplements typed dependencies; it does not
    # claim general semantic entailment. Unknown wording remains blocking.
    if re.search(r"澄清|补遗|更正|例外|优先|效力|适用前提|起算|关键数值|条款.{0,8}上下文|无法辨认|乱码|不可读", detail):
        result["reason"] = "mixed_current_rule_or_readability_dependency"
        return result
    patterns = {
        "submission_package_completeness": r"(?:递交|提交|投标)(?:文件)?包.{0,16}(?:完整|齐全)|(?:完整|最终)(?:的)?(?:递交|提交)(?:文件)?包|签字.{0,6}盖章|签署页|完整承诺书",
        "authenticity": r"真伪|真实性|真实任职|实际任职",
        "actual_performance": r"实际履行|后续履行|实际到岗|履约",
    }
    if not re.search(patterns[dep], detail):
        result["reason"] = "excluded_dependency_not_textually_identifiable"
        return result
    result.update(resolution="out_of_scope_item", reason="explicit_input_scope_exclusion_and_no_current_claim_dependency")
    return result


def audit_basis_v4(runtime, finding, usable_evidence, scope_spec):
    from nu_boundary_policy import audit_basis
    errors = validate_spec(runtime, scope_spec)
    expected = None
    if not errors:
        expected = build_contract(runtime, scope_spec)
    bound = expected is not None and runtime.get("review_task_contract_v4") == expected
    if not bound:
        errors.append("missing_stale_or_untrusted_v4_contract")
    spec = scope_spec if isinstance(scope_spec, dict) else {}
    original = finding.get("decision_basis")
    basis = original if isinstance(original, dict) else {}
    if not expected or basis.get("task_scope_sha256") != expected["input_scope_sha256"]:
        errors.append("response_scope_binding_missing_or_stale")
    if basis.get("review_target") != TARGETS.get(spec.get("review_mode")):
        errors.append("response_target_not_locked_mode")
    raw_claims = spec.get("required_claims", [])
    raw_claims = raw_claims if isinstance(raw_claims, list) else []
    claims = {c["claim_id"]: c for c in raw_claims
              if isinstance(c, dict) and isinstance(c.get("claim_id"), str)}
    normalized = deepcopy(finding)
    normalized["decision_basis"] = deepcopy(basis)
    nb = normalized["decision_basis"]
    resolutions, extra_blocks = [], []
    gaps = basis.get("gaps", [])
    if isinstance(gaps, list):
        nb["gaps"] = []
        for gap in gaps:
            if not isinstance(gap, dict):
                errors.append("invalid_gap"); continue
            dep = gap.get("dependency_key")
            affected = gap.get("affected_claim_ids")
            if not isinstance(dep, str) or dep not in KINDS or gap.get("kind") not in KINDS.get(dep, set()):
                errors.append("gap_dependency_kind_mismatch")
            if not isinstance(affected, list) or any(not isinstance(x, str) or x not in claims for x in affected):
                errors.append("gap_claim_binding_invalid")
            elif any(dep not in claims[x].get("required_dependencies", []) for x in affected):
                # A dependency-contract failure, not a verified legal U.
                errors.append("gap_dependency_not_declared_for_affected_claim")
            if type(gap.get("blocks_current_question")) is not bool or not _nonempty(gap.get("detail")) or not _nonempty(gap.get("reason")):
                errors.append("invalid_gap_contract")
            decision = resolve_gap(gap, spec) if bound else {"resolution": "blocking_gap", "reason": "unbound_scope", "detail": gap.get("detail")}
            resolutions.append(decision)
            adjusted = deepcopy(gap)
            if decision["resolution"] == "out_of_scope_item":
                adjusted.update(kind="other_outside_question", blocks_current_question=False)
            else:
                # All non-excluded gaps require dependency resolution, including
                # hard gaps labelled false and vague 'other' gaps labelled false.
                adjusted["blocks_current_question"] = True
                if isinstance(affected, list) and not affected:
                    extra_blocks.append("unresolved_gap_has_no_claim_binding")
            nb["gaps"].append(adjusted)
    spans = source_spans(runtime)
    excerpt = (runtime.get("contract_evidence") or {}).get("document_excerpt", "")
    legal_checks, legal_bindings, observations, bindings, covered = [], [], [], [], set()
    checks = basis.get("completed_checks")
    if not isinstance(checks, list):
        errors.append("completed_checks_not_list"); checks = []
    valid_ids = {e.get("chunk_id") for e in usable_evidence}
    seen_checks = set()
    for check in checks:
        if not isinstance(check, dict):
            errors.append("invalid_completed_check"); continue
        cid = check.get("check_id")
        if not _nonempty(cid) or cid in seen_checks:
            errors.append("invalid_or_duplicate_check_id")
        else:
            seen_checks.add(cid)
        kind = check.get("check_kind")
        ids = check.get("claim_ids")
        if not isinstance(ids, list) or any(not isinstance(x, str) or x not in claims for x in ids):
            errors.append("check_claim_binding_invalid"); ids = []
        binding = check_document_binding(check, spans, excerpt)
        bindings.append(binding)
        if not _nonempty(check.get("check")) or not _nonempty(check.get("comparison")):
            errors.append("check_description_missing")
        if kind == "text_observation":
            if check.get("legal_chunk_ids") != [] or ids:
                errors.append("observation_cannot_claim_legal_coverage")
            observations.append({"check_id": cid, "source_bound": binding["bound"],
                                 "observation": deepcopy(check), "supports_legal_conclusion_alone": False})
        elif kind == "legal_comparison":
            if not ids:
                errors.append("legal_check_claim_binding_missing")
            law_ids = check.get("legal_chunk_ids")
            if binding["bound"] and isinstance(law_ids, list) and law_ids and all(isinstance(x, str) and x in valid_ids for x in law_ids):
                covered.update(ids)
            legal_checks.append(check); legal_bindings.append(binding)
        else:
            errors.append("check_kind_missing_or_unknown")
    nb["completed_checks"] = legal_checks
    intent = factual_question_audit(str(_binding(runtime)["question"]))
    audit = audit_basis(runtime, normalized, usable_evidence, locator_spans=spans,
                        question_intent=intent, citation_audits=legal_bindings)
    missing_claims = sorted(set(claims) - covered)
    if missing_claims:
        extra_blocks.append("required_legal_claims_not_grounded:" + ",".join(missing_claims))
    if not legal_checks or not usable_evidence:
        extra_blocks.append("no_independent_legal_comparison_for_final_conclusion")
    audit["schema_errors"].extend(errors)
    audit["blocking_reasons"].extend(extra_blocks)
    binding_errors = evidence_binding_errors(runtime, finding)
    audit.update(version=VERSION, contract_bound=bound, scope_needs_confirmation=not bound,
                 schema_valid=not audit["schema_errors"], evidence_binding_errors=binding_errors,
                 citation_binding_audits=bindings, gap_resolutions=resolutions,
                 blocking_gaps=[d for d in resolutions if d["resolution"] == "blocking_gap"],
                 out_of_scope_items=[d for d in resolutions if d["resolution"] == "out_of_scope_item"],
                 text_observations=observations, required_claims_not_grounded=missing_claims,
                 original_basis_preserved=True, normalized_basis_for_validation_only=True,
                 scope_gap_policy="trusted_input_scope_then_claim_dependency_then_evidence_binding",
                 legal_correctness_verified=False)
    audit["force_insufficient"] = bool(audit["schema_errors"] or audit["blocking_reasons"] or binding_errors)
    audit["eligible_no_issue"] = bool(audit["eligible_no_issue"] and not audit["force_insufficient"])
    audit["processing_status"] = "schema_blocked" if not audit["schema_valid"] else "evidence_binding_blocked" if binding_errors else "valid"
    return audit


def build_handoff(original, gated):
    from review_task_contract_v2 import build_handoff as v2_handoff
    result = v2_handoff(original, gated)
    audit = gated.get("nu_boundary_audit") or {}
    result.update(version=VERSION, text_observations=deepcopy(audit.get("text_observations", [])),
                  blocking_gaps=deepcopy(audit.get("blocking_gaps", [])),
                  out_of_scope_items=deepcopy(audit.get("out_of_scope_items", [])),
                  scope_dependency_boundary="Excluded checks remain visible, not proved satisfied; legal entailment unverified.")
    return result
