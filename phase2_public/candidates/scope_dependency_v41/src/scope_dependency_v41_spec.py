"""Trusted scope validation, driven by v4.1.x schema, not legacy TARGETS."""
import re

from review_task_contract_v2 import _binding
from question_scope_signals import factual_question_audit
from scope_dependency_v41_schema import SCHEMA, is_text_mode


def validate_spec(runtime, spec):
    # Preserve v4 scope safeguards while sourcing every mode rule from schema.
    if not isinstance(spec, dict):
        return ["scope_spec_missing"]
    errors = []
    question = _binding(runtime)["question"]
    if not question or spec.get("question_verbatim") != question:
        errors.append("scope_spec_question_mismatch")
    mode = spec.get("review_mode")
    rule = SCHEMA["task_modes"].get(mode) if isinstance(mode, str) else None
    if not rule:
        errors.append("invalid_scope_mode")
    if not isinstance(spec.get("scope_basis"), str) or not spec["scope_basis"].strip():
        errors.append("scope_basis_missing")
    excluded = spec.get("excluded_dependencies")
    if not isinstance(excluded, list) or any(not isinstance(x, str) or x not in SCHEMA["text_excludable_dependencies"] for x in excluded):
        errors.append("invalid_scope_exclusion")
        excluded = []
    if not is_text_mode(mode) and excluded:
        errors.append("factual_task_cannot_use_text_exclusions")
    intent = factual_question_audit(str(question))
    if is_text_mode(mode) and (intent["has_active_factual_cue"] or intent["ambiguity_requires_review"]):
        errors.append("text_scope_conflicts_with_positive_or_ambiguous_factual_question")
    stage = re.split(r"[:：]", str(_binding(runtime)["document_stage"]), maxsplit=1)[0].strip()
    if rule and stage not in rule["document_stages"]:
        errors.append("scope_mode_stage_conflict")
    claims = spec.get("required_claims")
    if not isinstance(claims, list) or not claims:
        errors.append("required_claims_missing")
        claims = []
    seen = set()
    for claim in claims:
        if not isinstance(claim, dict):
            errors.append("invalid_claim")
            continue
        cid, deps = claim.get("claim_id"), claim.get("required_dependencies")
        if not isinstance(cid, str) or not cid.strip() or cid in seen:
            errors.append("invalid_or_duplicate_claim_id")
        else:
            seen.add(cid)
        if not isinstance(claim.get("description"), str) or not claim["description"].strip():
            errors.append("claim_description_missing")
        if not isinstance(deps, list) or not deps or any(not isinstance(x, str) or x not in SCHEMA["dependency_kind_pairs"] for x in deps):
            errors.append("invalid_claim_dependencies")
        elif set(deps) & set(excluded):
            errors.append("required_dependency_excluded")
    return errors
