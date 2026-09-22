"""Opt-in, input-bound task contracts. No answer labels or issue-ID rules.

The contract is deterministic scope metadata, not human approval or a legal
truth oracle. It is built from the question BEFORE looking at a response.
"""
from copy import deepcopy
import hashlib
import json
import re

VERSION = "review-task-contract-v2.2-scope-citation-candidate"
CORE_GAPS = {"key_legal_source_missing", "decisive_applicability_missing",
             "comparison_value_missing", "unreadable_evidence"}
MATERIAL_GAPS = {"input_evidence_missing", "required_document_missing"}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def _binding(runtime):
    context = runtime.get("project_context") or runtime.get("runtime_project_context") or {}
    return {"question": context.get("review_question", ""),
            "document_stage": context.get("document_stage", ""),
            "evidence_boundary": context.get("evidence_boundary", ""),
            "contract_evidence": runtime.get("contract_evidence") or {}}


def source_spans(runtime):
    """Only declared source locators delimit text; redaction brackets do not.

    Multi-locator unsegmented text has no certified span. A single declared
    location can bind an entire unsegmented excerpt. Never merge adjacent lines
    or normalize quotations to manufacture a successful citation.
    """
    data = runtime.get("contract_evidence") or {}
    excerpt = str(data.get("document_excerpt") or "")
    declared = {x.strip() for x in str(data.get("document_location") or "").split(";") if x.strip()}
    markers = [m for m in re.finditer(r"\[([^\]\n]+)\]", excerpt) if m.group(1) in declared]
    spans = {}
    for i, marker in enumerate(markers):
        end = markers[i+1].start() if i+1 < len(markers) else len(excerpt)
        spans.setdefault(marker.group(1), []).append(excerpt[marker.end():end])
    if not markers and len(declared) == 1:
        spans[next(iter(declared))] = [excerpt]
    return spans


def build_contract(runtime):
    from scope_boundary_policy import task_contract
    from question_scope_signals import factual_question_audit
    data = _binding(runtime)
    question = str(data["question"])
    intent = factual_question_audit(question)
    legacy = task_contract(runtime, question_intent=intent)
    excerpt = str(data["contract_evidence"].get("document_excerpt") or "")
    locators = set(source_spans(runtime))
    declared_type = legacy["task_type"]
    factual = intent['has_active_factual_cue']
    internal = bool(re.search(r"(?:表达|表述|两处|两项|内部).{0,8}是否一致", question)) and len(locators) >= 2
    if factual or declared_type in {"actual_conduct", "document_completeness"}:
        scope = "actual_or_completeness"
    elif internal and declared_type in {"document_response", "clause_design"}:
        scope = "supplied_text_consistency"
    elif declared_type == "clause_design" and re.search(r"条款|约定|规则|要求", question):
        scope = "clause_design"
    else:
        scope = "scope_needs_confirmation"
    return {"version": VERSION, "input_sha256": digest(data),
            "question_verbatim": question, "document_stage_verbatim": data["document_stage"],
            "evidence_boundary_verbatim": data["evidence_boundary"],
            "declared_task_type": declared_type, "scope": scope,
            "scope_origin": "deterministic_input_only", "human_scope_approval": False,
            "question_rewritten": False, "evidence_package_extent": "not_certified_complete",
            "required_for_legal_conclusion": ["independent_applicable_rule", "grounded_comparison",
                                               "question_decisive_facts"],
            "excluded_inferences": ["unshown_means_absent", "promise_proves_performance",
                                    "no_hit_means_compliant"],
            "factual_question_audit": intent,
            "ambiguity_requires_review": scope == "scope_needs_confirmation" or intent['ambiguity_requires_review']}


def validate_contract(runtime, contract):
    # Recompute, so model-supplied or stale scope cannot widen the task.
    return isinstance(contract, dict) and contract == build_contract(runtime)


def gap_resolution(contract, gap):
    """A narrow dependency check, never a blanket 'false means nonblocking'."""
    kind = gap.get("kind")
    detail = str(gap.get("detail") or "")
    decision = {"original_kind": kind, "detail": detail,
                "model_blocks": gap.get("blocks_current_question"),
                "resolution": "preserve", "reason": "no_verified_scope_exclusion"}
    if kind in CORE_GAPS:
        decision["reason"] = "core_legal_or_comparison_dependency_preserved"
        return decision
    if gap.get("blocks_current_question") is not False:
        decision["reason"] = "model_reports_blocking_or_invalid_flag"
        return decision
    scope = contract["scope"]
    if scope not in {"supplied_text_consistency", "clause_design"}:
        return decision
    if kind not in MATERIAL_GAPS:
        return decision  # Existing follow-up safeguards stay in v1.
    # Never discard missing context/exception/priority that can change the rule.
    if re.search(r"例外|优先适用|效力层级|当前条款.{0,6}上下文|条款自身.{0,8}条件|签字|盖章|原件真伪", detail):
        decision["reason"] = "potential_rule_or_current_evidence_dependency"
        return decision
    if scope == "supplied_text_consistency" and re.search(r"招标文件.{0,24}(?:前附表|完整原文|全文)", detail):
        # This exclusion is limited to comparing two supplied expressions. It
        # does NOT establish satisfaction of the external tender requirement.
        decision.update(resolution="follow_up_only", reason="external_requirement_not_supplied_text_consistency")
    elif scope == "clause_design":
        if re.search(r"实际(?:履行|到岗|缴纳|委托|上传|开标|签约|投标行为)|真实上传日志", detail):
            decision.update(resolution="follow_up_only", reason="actual_event_not_clause_design")
        elif (re.search(r"完整招标文件.*(?:未提供|未纳入)", detail)
              and re.search(r"(?:核验|确认).*(?:是否已|有无).*(?:披露|明确|公布|公示)", detail)
              and not re.search(r"披露|公布|公示|完整性", contract["question_verbatim"])):
            decision.update(resolution="follow_up_only", reason="other_document_disclosure_not_clause_design")
    return decision


def audit_basis_v2(runtime, finding, usable_evidence):
    from nu_boundary_policy import audit_basis
    contract = runtime.get("review_task_contract_v2")
    valid = validate_contract(runtime, contract)
    normalized = deepcopy(finding)
    basis = normalized.get("decision_basis")
    resolutions = []
    if valid and isinstance(basis, dict) and isinstance(basis.get("gaps"), list):
        for gap in basis["gaps"]:
            if not isinstance(gap, dict):
                continue
            decision = gap_resolution(contract, gap)
            resolutions.append(decision)
            if decision["resolution"] == "follow_up_only":
                gap["kind"] = "other_outside_question"
    from question_scope_signals import factual_question_audit
    from exact_citation_fragments import check_document_binding
    spans = source_spans(runtime)
    excerpt = (runtime.get('contract_evidence') or {}).get('document_excerpt','')
    original_basis = finding.get('decision_basis')
    checks = original_basis.get('completed_checks',[]) if isinstance(original_basis,dict) else []
    bindings = [check_document_binding(c,spans,excerpt) if isinstance(c,dict) else
                {'bound':False,'errors':['invalid_completed_check']} for c in checks] if isinstance(checks,list) else []
    intent = factual_question_audit(str(_binding(runtime)['question']))
    audit = audit_basis(runtime, normalized, usable_evidence, locator_spans=spans,
                        question_intent=intent, citation_audits=bindings)
    audit['citation_binding_audits'] = bindings
    audit.update(version=VERSION, gap_resolutions=resolutions, contract_bound=valid,
                 normalized_basis_for_validation_only=True,
                 original_basis_preserved=True, legal_correctness_verified=False)
    if not valid:
        audit["schema_errors"].append("missing_stale_or_untrusted_runtime_task_contract")
        audit.update(schema_valid=False, force_insufficient=True, eligible_no_issue=False)
    if valid:
        audit["scope_needs_confirmation"] = contract["ambiguity_requires_review"]
    binding_errors = evidence_binding_errors(runtime, finding)
    audit["evidence_binding_errors"] = binding_errors
    # Provenance failures are technical evidence-validation failures, not a
    # successful legal abstention. A genuine missing rule remains legal U.
    audit["processing_status"] = ("schema_blocked" if not audit["schema_valid"] else
                                  "evidence_binding_blocked" if binding_errors else
                                  "valid")
    audit["scope_gap_policy"] = "input_bound_dependency_not_gap_name_or_model_flag_alone"
    return audit


def evidence_binding_errors(runtime, finding):
    """Separate invented/mislocated evidence from an ineligible legal basis.

    A supplied supplement or non-applicable rule is a semantic evidence gap,
    not a transport/schema failure. No semantic entailment is certified here.
    """
    data = runtime.get("contract_evidence") or {}
    excerpt = str(data.get("document_excerpt") or "")
    spans = source_spans(runtime)
    from exact_citation_fragments import check_document_binding
    supplied_ids = {e.get("chunk_id") for e in runtime.get("retrieved_legal_evidence", []) if isinstance(e, dict)}
    errors = []
    basis = finding.get("decision_basis") or {}
    checks = basis.get("completed_checks") if isinstance(basis, dict) else []
    for i, check in enumerate(checks if isinstance(checks, list) else []):
        if not isinstance(check, dict):
            continue  # The schema validator reports this separately.
        errors.extend(f'check_{i}:{e}' for e in check_document_binding(check,spans,excerpt)['errors'])
        ids = check.get("legal_chunk_ids")
        if isinstance(ids, list) and any(not isinstance(x, str) or x not in supplied_ids for x in ids):
            errors.append(f"check_{i}:legal_id_not_supplied")
    return errors


def build_handoff(original, gated):
    """Preserve useful, bounded observations without restoring blocked claims."""
    basis = original.get("decision_basis") or {}
    audit = gated.get("nu_boundary_audit") or {}
    comparison = original.get("fact_law_comparison") or {}
    if not isinstance(comparison, dict):
        comparison = {}
    checks = basis.get("completed_checks", []) if isinstance(basis, dict) else []
    notes = audit.get("blocking_reasons", []) + audit.get("schema_errors", []) + audit.get("evidence_binding_errors", [])
    return {"version": VERSION, "processing_status": audit.get("processing_status", "valid"),
            "decision_status": gated.get("conclusion_type"),
            "workflow_status": "requires_human_second_review",
            "scope_needs_confirmation": audit.get("scope_needs_confirmation", False),
            "completed_checks_reported_by_model": deepcopy(checks),
            "valid_completed_check_count": audit.get("completed_check_count", 0),
            "completed_check_boundary": "Provenance checks are not legal-entailment validation.",
            "citation_binding_audits": deepcopy(audit.get('citation_binding_audits', [])),
            "model_comparison_for_review": comparison.get("difference_summary") or original.get("reasoning_conclusion", ""),
            "model_comparison_status": "unverified_model_explanation_not_independent_legal_evidence",
            "blocking_reasons": deepcopy(notes),
            "follow_up_only": deepcopy(audit.get("follow_up_only", [])),
            "gap_resolutions": deepcopy(audit.get("gap_resolutions", [])),
            "evidence_roles": [{"chunk_id": e.get("chunk_id"), "law": e.get("law"),
                                "article": e.get("article"), "eligibility": e.get("legal_evidence_eligibility"),
                                "applicability_status": e.get("applicability_status")}
                               for e in gated.get("legal_evidence", []) if isinstance(e, dict)],
            "no_automatic_award_or_rejection": True}
