"""Opt-in v4.1: protocol conformance, task relation, legal answerability.

These are separate dimensions. A scope-review hold is not a successful legal
abstention. This checker does not certify the semantics of model explanations.
"""
from copy import deepcopy
import re

from scope_dependency_v41_schema import VERSION, DEPENDENCIES, SCHEMA, validate_basis, expected_review_target, is_text_mode
from scope_dependency_v41_spec import validate_spec
from review_task_contract_v2 import digest, _binding, source_spans, evidence_binding_errors
from exact_citation_fragments import check_document_binding
from question_scope_signals import factual_question_audit


def build_contract(runtime, spec):
    errors = validate_spec(runtime, spec)
    if errors:
        raise ValueError("; ".join(errors))
    payload = {"version": VERSION, "input": _binding(runtime),
               "project_context": runtime.get("project_context") or runtime.get("runtime_project_context") or {},
               "scope_spec": deepcopy(spec), "schema_sha256": digest(SCHEMA),
               "expected_review_target": expected_review_target(spec["review_mode"])}
    return {"version": VERSION, "input_scope_sha256": digest(payload),
            "schema_sha256": digest(SCHEMA), "scope_spec": deepcopy(spec),
            "expected_review_target": payload["expected_review_target"],
            "origin": "trusted_caller_before_inference",
            "human_approval_inferred": False, "input_completeness_certified": False}


def resolve_gap(gap, spec, spans, excerpt, *, material_aliases_v412=False):
    dep = gap.get("dependency_key")
    relation = gap.get("task_relation")
    affected = gap.get("affected_claim_ids")
    claims = {c["claim_id"]: c for c in spec.get("required_claims", []) if isinstance(c, dict) and isinstance(c.get("claim_id"), str)}
    result = {"gap_id": gap.get("gap_id"), "dependency_key": dep,
              "original_kind": gap.get("kind"), "detail": gap.get("detail"),
              "task_relation": relation, "affected_claim_ids": deepcopy(affected),
              "resolution": "scope_review_item", "reason": "relationship_undetermined",
              "legal_correctness_verified": False}
    def hold(reason):
        result["reason"] = reason
        return result
    if not isinstance(affected, list) or any(not isinstance(x, str) or x not in claims for x in affected):
        return hold("unknown_claim_binding")
    if any(dep not in claims[x].get("required_dependencies", []) for x in affected):
        return hold("dependency_not_declared_for_affected_claim")
    if dep == "other_undetermined" or relation == "undetermined":
        return hold("relationship_undetermined")
    detail = str(gap.get("detail") or "")
    # Advisory lexical guards cannot exhaustively recognize mixed natural language.
    signals = {
        "submission_package_completeness": r"递交包|提交包|整包|全包|完整承诺书|签署页",
        "authenticity": r"真实性|真伪|真实任职|实际任职",
        "actual_performance": r"后续履行|实际履行|实际到岗|履约",
        "current_clause_context": r"补遗|澄清|更正|优先顺序|解释顺序|条款上下文",
        "comparison_operand": r"关键数值|比较数值|项目金额|起算点",
        "readability": r"无法辨认|不可读|乱码",
    }
    signalled = {k for k, pattern in signals.items() if re.search(pattern, detail)}
    if material_aliases_v412:
        from scope_routing_v412 import recognize_material
        signalled, recognition, guard_reason = recognize_material(gap, signals)
        recognition["caller_excluded_dependencies"] = deepcopy(spec.get("excluded_dependencies", []))
        recognition["caller_review_mode"] = spec.get("review_mode")
        result["material_recognition"] = recognition
        if guard_reason:
            return hold(guard_reason)
    if len(signalled) > 1 or (signalled and dep not in signalled):
        return hold("mixed_or_misclassified_material_dependency")
    trigger = gap.get("dependency_trigger")
    if relation == "decisive_for_claim":
        if gap.get("blocks_current_question") is not True or not affected:
            return hold("decisive_relation_flag_or_claim_conflict")
        if trigger not in {"locked_requirement", "observed_context_conflict"}:
            return hold("generic_possibility_not_established_decisive_dependency")
        if trigger == "observed_context_conflict" and not gap.get("trigger_evidence"):
            return hold("observed_conflict_requires_source_pointer")
        result.update(resolution="blocking_gap", reason="declared_claim_dependency_with_specific_model_explanation")
        return result
    if relation == "outside_locked_scope":
        if gap.get("blocks_current_question") is not False or affected:
            return hold("outside_relation_flag_or_claim_conflict")
        if not is_text_mode(spec.get("review_mode")) or dep not in SCHEMA["text_excludable_dependencies"] or dep not in spec.get("excluded_dependencies", []):
            return hold("outside_relation_not_authorized_by_locked_scope")
        if trigger != "explicit_scope_exclusion":
            return hold("outside_relation_requires_explicit_scope_exclusion")
        if dep not in signalled:
            return hold("outside_material_not_textually_identifiable")
        result.update(resolution="out_of_scope_item", reason="explicit_exclusion_no_current_claim_dependency")
        return result
    return hold("invalid_relation")


def audit_basis_v41(runtime, finding, usable_evidence, scope_spec, *, material_aliases_v412=False):
    from nu_boundary_policy import audit_basis
    spec = scope_spec if isinstance(scope_spec, dict) else {}
    errors = list(validate_spec(runtime, scope_spec))
    expected = build_contract(runtime, scope_spec) if not errors else None
    bound = expected is not None and runtime.get("review_task_contract_v41") == expected
    if not bound:
        errors.append("missing_stale_or_untrusted_v41_contract")
    original = finding.get("decision_basis")
    basis = original if isinstance(original, dict) else {}
    errors += validate_basis(original)
    if not expected or basis.get("task_scope_sha256") != expected["input_scope_sha256"]:
        errors.append("response_scope_binding_missing_or_stale")
    if basis.get("review_target") != expected_review_target(spec.get("review_mode")):
        errors.append("response_target_not_locked_mode")
    if errors:
        return {"version": VERSION, "schema_valid": False, "schema_errors": errors,
                "processing_status": "schema_blocked", "force_insufficient": True,
                "eligible_no_issue": False, "blocking_reasons": [], "follow_up_only": [],
                "completed_check_count": 0, "contract_bound": bound,
                "expected_review_target": expected_review_target(spec.get("review_mode")),
                "observed_review_target": basis.get("review_target"),
                "scope_needs_confirmation": not bound, "relation_errors": [],
                "gap_resolutions": [], "blocking_gaps": [], "out_of_scope_items": [],
                "scope_review_items": [], "text_observations": [], "citation_binding_audits": [],
                "evidence_binding_errors": [], "original_basis_preserved": True,
                "valid_legal_verdict_available": False, "legal_correctness_verified": False}
    claims = {c["claim_id"]: c for c in spec.get("required_claims", []) if isinstance(c, dict) and isinstance(c.get("claim_id"), str)}
    spans = source_spans(runtime)
    excerpt = (runtime.get("contract_evidence") or {}).get("document_excerpt", "")
    normalized = deepcopy(finding)
    normalized["decision_basis"] = deepcopy(basis)
    nb = normalized["decision_basis"]
    nb["gaps"] = []
    resolutions, relation_errors, trigger_errors = [], [], []
    gaps = basis.get("gaps")
    seen_gaps = set()
    for gap in gaps if isinstance(gaps, list) else []:
        if not isinstance(gap, dict):
            continue
        gid = gap.get("gap_id")
        if isinstance(gid, str) and gid not in seen_gaps:
            seen_gaps.add(gid)
        else:
            errors.append("invalid_or_duplicate_gap_id")
        for i, pointer in enumerate(gap.get("trigger_evidence") if isinstance(gap.get("trigger_evidence"), list) else []):
            if isinstance(pointer, dict):
                trigger_errors += [str(gid) + ":trigger_" + str(i) + ":" + e for e in check_document_binding(pointer, spans, excerpt)["errors"]]
        resolution = resolve_gap(gap, spec, spans, excerpt, material_aliases_v412=material_aliases_v412) if bound else {
            "resolution": "scope_review_item", "reason": "unbound_scope", "gap_id": gid, "detail": gap.get("detail")}
        resolutions.append(resolution)
        if resolution["resolution"] == "scope_review_item":
            relation_errors.append(resolution["reason"])
        # Legacy validator view only. Source/output records are never rewritten.
        adjusted = deepcopy(gap)
        if resolution["resolution"] == "out_of_scope_item":
            adjusted.update(kind="other_outside_question", blocks_current_question=False)
        else:
            adjusted["blocks_current_question"] = True
            if adjusted.get("kind") == "material_type_undetermined":
                adjusted["kind"] = "input_evidence_missing"
        nb["gaps"].append(adjusted)
    if basis.get("answerability") == "scope_unresolved":
        relation_errors.append("model_reports_scope_unresolved")
        nb["answerability"] = "decisive_gap" if nb["gaps"] else "sufficient"
    if any(r["resolution"] == "blocking_gap" for r in resolutions) and basis.get("answerability") == "sufficient":
        relation_errors.append("answerability_conflicts_with_decisive_dependency")
    if basis.get("answerability") == "decisive_gap" and not any(r["resolution"] == "blocking_gap" for r in resolutions):
        relation_errors.append("legal_U_without_established_current_dependency")
    legal_checks, legal_bindings, observations, bindings, covered = [], [], [], [], set()
    valid_ids = {e.get("chunk_id") for e in usable_evidence}
    seen_checks = set()
    checks = basis.get("completed_checks")
    for check in checks if isinstance(checks, list) else []:
        if not isinstance(check, dict):
            continue
        cid, ids, kind = check.get("check_id"), check.get("claim_ids"), check.get("check_kind")
        if not isinstance(cid, str) or cid in seen_checks:
            errors.append("invalid_or_duplicate_check_id")
        else:
            seen_checks.add(cid)
        if not isinstance(ids, list) or any(not isinstance(x, str) or x not in claims for x in ids):
            relation_errors.append("check_claim_binding_invalid")
            ids = []
        binding = check_document_binding(check, spans, excerpt)
        bindings.append(binding)
        if kind == "text_observation":
            if check.get("legal_chunk_ids") != [] or ids:
                errors.append("observation_cannot_claim_legal_coverage")
            observations.append({"check_id": cid, "source_bound": binding["bound"], "observation": deepcopy(check), "supports_legal_conclusion_alone": False})
        elif kind == "legal_comparison":
            if not ids:
                relation_errors.append("legal_check_claim_binding_missing")
            laws = check.get("legal_chunk_ids")
            if binding["bound"] and isinstance(laws, list) and laws and all(isinstance(x, str) and x in valid_ids for x in laws):
                covered.update(ids)
            legal_checks.append(check)
            legal_bindings.append(binding)
    nb["completed_checks"] = legal_checks
    intent = factual_question_audit(str(_binding(runtime)["question"]))
    audit = audit_basis(runtime, normalized, usable_evidence, locator_spans=spans,
                        question_intent=intent, citation_audits=legal_bindings)
    audit["schema_errors"].extend(errors)
    missing_claims = sorted(set(claims) - covered)
    if missing_claims:
        audit["blocking_reasons"].append("required_legal_claims_not_grounded:" + ",".join(missing_claims))
        if not any(r["resolution"] == "blocking_gap" for r in resolutions):
            relation_errors.append("missing_claim_coverage_without_declared_decisive_gap")
    if not legal_checks or not usable_evidence:
        audit["blocking_reasons"].append("no_independent_legal_comparison_for_final_conclusion")
    binding_errors = evidence_binding_errors(runtime, finding) + trigger_errors
    scope_review = bool(relation_errors)
    schema_valid = not audit["schema_errors"]
    status = ("schema_blocked" if not schema_valid else "evidence_binding_blocked" if binding_errors
              else "scope_review_required" if scope_review else "valid")
    audit.update(version=VERSION, contract_bound=bound, schema_valid=schema_valid,
                 processing_status=status, scope_needs_confirmation=scope_review or not bound,
                 relation_errors=relation_errors, evidence_binding_errors=binding_errors,
                 citation_binding_audits=bindings, gap_resolutions=resolutions,
                 blocking_gaps=[r for r in resolutions if r["resolution"] == "blocking_gap"],
                 out_of_scope_items=[r for r in resolutions if r["resolution"] == "out_of_scope_item"],
                 scope_review_items=[r for r in resolutions if r["resolution"] == "scope_review_item"],
                 text_observations=observations, required_claims_not_grounded=missing_claims,
                 original_basis_preserved=True, normalized_basis_for_validation_only=True,
                 legal_correctness_verified=False)
    audit["force_insufficient"] = bool(audit["schema_errors"] or audit["blocking_reasons"] or binding_errors or scope_review)
    audit["eligible_no_issue"] = bool(audit["eligible_no_issue"] and not audit["force_insufficient"])
    audit["valid_legal_verdict_available"] = status == "valid"
    return audit


def build_handoff(original, gated):
    from review_task_contract_v2 import build_handoff as base_handoff
    result = base_handoff(original, gated)
    audit = gated.get("nu_boundary_audit") or {}
    result.update(version=VERSION, text_observations=deepcopy(audit.get("text_observations", [])),
                  blocking_gaps=deepcopy(audit.get("blocking_gaps", [])),
                  out_of_scope_items=deepcopy(audit.get("out_of_scope_items", [])),
                  scope_review_items=deepcopy(audit.get("scope_review_items", [])),
                  relation_errors=deepcopy(audit.get("relation_errors", [])),
                  valid_legal_verdict_available=audit.get("processing_status") == "valid")
    if not result["valid_legal_verdict_available"]:
        result["compatibility_conclusion_not_a_legal_verdict"] = gated.get("conclusion_type")
        result["decision_status"] = None
    return result
