"""Fail-closed, opt-in three-layer evaluator. Never modifies inputs or calls APIs."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re
from spec import (VERSION, SPEC, TASK_MODES, DEPENDENCIES, EXCLUDABLE, CLAIM_RULES,
                  RELATION_RULES, COMPLETION_RULES, HANDOFF_RULES, MATERIAL_PATTERNS,
                  CURRENT_MATERIAL_PATTERN, RULES, digest, validate, normalize)

# Read-only reuse of the frozen input-only question classifier; no v4.1.2 route.
_factual_path = Path(__file__).resolve().parent.parent / "scope_dependency_v41/src/question_scope_signals.py"
_factual_spec = importlib.util.spec_from_file_location("_frozen_question_signals", _factual_path)
_factual = importlib.util.module_from_spec(_factual_spec)
_factual_spec.loader.exec_module(_factual)

def _text(v):
    return isinstance(v, str) and bool(v.strip())

def _strings(v):
    return isinstance(v, list) and all(_text(x) for x in v) and len(v) == len(set(v))

def _indexed(items, key):
    if not isinstance(items, list) or any(not isinstance(x, dict) or not _text(x.get(key)) for x in items):
        raise ValueError("invalid_registry")
    result = {x[key]: x for x in items}
    if len(result) != len(items):
        raise ValueError("duplicate_registry_id")
    return result

def seal_context(context):
    """Trusted caller / fixture helper BEFORE inference. Hash is NOT an approval/signature."""
    out = deepcopy(context)
    out["task_scope_sha256"] = digest(out["task"])
    out["input_sha256"] = digest({k: out[k] for k in ("sources", "evidence_registry", "laws")})
    return out

def context_errors(ctx):
    errors = []
    try:
        task = ctx["task"]
        if not isinstance(task, dict) or not _text(task.get("question")):
            raise ValueError("task_missing")
        mode = TASK_MODES.get(task.get("review_mode"))
        if not mode or task.get("review_target") != mode["target"] or task.get("document_stage") not in mode["stages"]:
            errors.append("task_mode_target_stage_mismatch")
        if ctx.get("task_scope_sha256") != digest(task):
            errors.append("task_hash_mismatch")
        if ctx.get("input_sha256") != digest({k: ctx[k] for k in ("sources", "evidence_registry", "laws")}):
            errors.append("input_hash_mismatch")
        excluded = task.get("excluded_dependencies")
        if not _strings(excluded) or not set(excluded) <= set(EXCLUDABLE):
            raise ValueError("invalid_exclusions")
        if mode and not mode["text_exclusions"] and excluded:
            errors.append("factual_task_cannot_exclude_text_dependencies")
        intent = _factual.factual_question_audit(task["question"])
        if mode and mode["text_exclusions"] and (intent["has_active_factual_cue"] or intent["ambiguity_requires_review"]):
            errors.append("factual_question_in_text_scope")
        claims = _indexed(task["required_claims"], "claim_id")
        if not claims:
            errors.append("empty_required_claims")
        for c in claims.values():
            deps = c.get("required_dependencies")
            if not _text(c.get("description")) or not _strings(deps) or not deps or not set(deps) <= set(DEPENDENCIES):
                errors.append("invalid_required_claim")
            elif set(deps) & set(excluded):
                errors.append("required_dependency_excluded")
        sources = _indexed(ctx["sources"], "source_id")
        evidence = _indexed(ctx["evidence_registry"], "evidence_id")
        _indexed(ctx["laws"], "chunk_id")
        for s in sources.values():
            if not all(_text(s.get(k)) for k in ("document_sha256", "locator", "text")) or not re.fullmatch(r"[0-9a-f]{64}", s["document_sha256"]):
                errors.append("invalid_source_record")
        for e in evidence.values():
            s = sources.get(e.get("source_id"))
            if not s or any(e.get(k) != s.get(k) for k in ("document_sha256", "locator")) or not _text(e.get("quote")) or e["quote"] not in s["text"]:
                errors.append("evidence_registry_source_mismatch")
        for law in ctx["laws"]:
            if not all(_text(law.get(k)) for k in ("text", "locator", "source_sha256")) or not re.fullmatch(r"[0-9a-f]{64}", law["source_sha256"]):
                errors.append("invalid_law_record")
            if type(law.get("admitted")) is not bool or type(law.get("independent_legal_basis")) is not bool:
                errors.append("invalid_law_admission_flags")
            if law.get("applicability_status") not in ("applicable", "unknown", "inapplicable"):
                errors.append("invalid_law_applicability_status")
            if law.get("temporal_status") not in ("valid", "unknown", "invalid"):
                errors.append("invalid_law_temporal_status")
    except (KeyError, TypeError, ValueError, AttributeError):
        errors.append("malformed_trusted_context")
    return errors

def _strict_json(text):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError("duplicate_json_key")
            out[k] = v
        return out
    def constant(value):
        raise ValueError("nonfinite_json_number")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)

def evaluate(raw, context, *, finish_reason, transport_ok=True, normalization=False):
    """Caller passes only final response; no reasoning channel, no secret/env access."""
    received = deepcopy(raw)
    errors, technical, actions = [], [], []
    def error(rule, code, path="$"):
        assert rule in RULES
        errors.append({"rule_id": rule, "code": code, "path": path})
    try:
        raw_hash = digest(received)
    except (TypeError, ValueError):
        raw_hash = None
        technical.append("non_json_serializable_input")
    if transport_ok is not True:
        technical.append("transport_failure")
    if finish_reason != "stop":
        technical.append("incomplete_finish_reason:" + str(finish_reason))
    parsed = deepcopy(received)
    if isinstance(parsed, str):
        try:
            parsed = _strict_json(parsed)
        except (ValueError, TypeError, RecursionError):
            parsed = None
            technical.append("invalid_complete_json")
    raw_structure = validate(parsed)
    candidate, actions = normalize(parsed, enabled=normalization)
    normalized_structure = validate(candidate)
    for msg in normalized_structure:
        error("S01", msg)
    for msg in context_errors(context):
        error("B01", msg, "trusted_context")
    # Processing failures never acquire canonical legal states from fragments.
    if not technical and not errors:
        _audit(candidate, context, error)
    processing = "technical_failure" if technical else "protocol_hold" if errors else "valid"
    valid = processing == "valid"
    claims = candidate["claim_assessments"] if valid else []
    gaps = candidate["gaps"] if valid else []
    checks = candidate["completed_checks"] if valid else []
    raw_claims = context.get("task", {}).get("required_claims") if isinstance(context, dict) and isinstance(context.get("task"), dict) else None
    n = len(raw_claims) if isinstance(raw_claims, list) else None
    # Ledger presence is not legal/protocol validity. A fully enumerated ledger
    # can still have an invalid citation or contradictory relationship.
    ledger_complete = None
    if not technical and isinstance(raw_claims, list) and isinstance(candidate, dict):
        try:
            required_ids = set(_indexed(raw_claims, "claim_id"))
            ledger_ids = set(_indexed(candidate.get("claim_assessments"), "claim_id"))
            ledger_complete = bool(required_ids) and required_ids == ledger_ids
        except ValueError:
            ledger_complete = False
    a = sum(c["assessment_state"] == "assessed" for c in claims) if valid else None
    groups = {r["group"]: [] for r in RELATION_RULES.values()}
    if valid:
        for g in gaps:
            groups[RELATION_RULES[g["task_relation"]]["group"]].append(g["gap_id"])
    facts = {
        "technical_failure": processing == "technical_failure",
        "protocol_hold": processing == "protocol_hold",
        "has_unresolved": valid and bool(groups["scope_review_item"]),
        "all_assessed": valid and a == n and n > 0,
        "some_assessed": valid and a > 0,
        "has_actionable_info": valid and bool(checks or groups["blocking_gap"]),
        "otherwise": True,
    }
    completion = next(v for cond, v in COMPLETION_RULES if facts[cond]) if valid else None
    handoff = next(v for cond, v in HANDOFF_RULES if facts[cond])
    reasons = []
    if valid:
        if groups["blocking_gap"]:
            reasons.append("decisive_gap")
        if groups["scope_review_item"]:
            reasons.append("scope_relation_pending")
        if any(c["assessment_state"] == "not_assessed" for c in claims):
            reasons.append("not_assessed")
    # A declaration retained for diagnostics is NOT a validated gap.
    declarations = []
    if isinstance(candidate, dict) and isinstance(candidate.get("gaps"), list):
        declarations = [g.get("gap_id") for g in candidate["gaps"] if isinstance(g, dict) and g.get("task_relation") == "decisive_for_claim"]
    return {
        "protocol_version": VERSION, "spec_sha256": digest(SPEC),
        "processing_status": processing, "technical_errors": technical, "errors": errors,
        "raw_response_sha256": raw_hash, "raw_received": received,
        "raw_structure_valid": not raw_structure, "raw_structure_errors": raw_structure,
        "normalization_enabled": normalization, "normalization_actions": actions,
        "normalized_structure_valid": not normalized_structure, "normalized_response": candidate,
        "raw_response_modified": False, "semantic_repairs_permitted": False,
        "claim_ledger_complete": ledger_complete, "claim_states": deepcopy(claims),
        "required_claim_count": n, "assessed_claim_count": a,
        "question_completion": completion, "completion_reasons": reasons,
        "gap_groups": groups, "declared_blocking_gap_ids_unvalidated": declarations,
        "handoff_status": handoff, "human_review_required": True,
        "semantic_correctness_verified": False, "joint_handoff_effectiveness": None,
        "legacy_legal_verdict": None, "legal_source_verification": "trusted_upstream_metadata_only",
        "presentation_only": True,
    }

def _audit(r, ctx, error):
    task = ctx["task"]
    for key, expected in (("task_scope_sha256", ctx["task_scope_sha256"]), ("input_sha256", ctx["input_sha256"]),
                          ("review_question", task["question"]), ("review_target", task["review_target"])):
        if r[key] != expected:
            error("B01", "response_binding_mismatch", key)
    required = _indexed(task["required_claims"], "claim_id")
    indexed = {}
    for name, key in (("claim_assessments", "claim_id"), ("completed_checks", "check_id"), ("gaps", "gap_id")):
        try:
            indexed[name] = _indexed(r[name], key)
        except ValueError:
            error("S01", "duplicate_or_invalid_id", name)
            return
    claims, checks, gaps = (indexed[k] for k in ("claim_assessments", "completed_checks", "gaps"))
    if set(claims) != set(required):
        error("R03", "required_claim_set_mismatch", "claim_assessments")
    evidence = _indexed(ctx["evidence_registry"], "evidence_id")
    laws = _indexed(ctx["laws"], "chunk_id")
    for cid, check in checks.items():
        if not check["document_evidence_refs"] or not set(check["document_evidence_refs"]) <= set(evidence):
            error("E01", "check_document_ref_invalid", cid)
        if check["check_kind"] == "text_observation":
            if check["legal_chunk_ids"] or check["claim_ids"]:
                error("R03", "observation_cannot_claim_legal_coverage", cid)
        else:
            if len(check["claim_ids"]) != 1 or not set(check["claim_ids"]) <= set(required):
                error("R03", "legal_check_requires_one_locked_claim", cid)
            if not check["legal_chunk_ids"]:
                error("E01", "legal_check_missing_law", cid)
            for lid in check["legal_chunk_ids"]:
                law = laws.get(lid)
                if not law or law["admitted"] is not True or law["independent_legal_basis"] is not True:
                    error("E01", "law_not_independently_admitted", cid)
                elif law["applicability_status"] != "applicable" or law["temporal_status"] != "valid":
                    error("E01", "law_applicability_or_time_unresolved", cid)
    for gid, gap in gaps.items():
        dep, rel = gap["dependency_key"], gap["task_relation"]
        rule = RELATION_RULES[rel]
        affected = gap["affected_claim_ids"]
        if gap["kind"] not in DEPENDENCIES[dep]:
            error("R01", "dependency_kind_mismatch", gid)
        if dep == "other_undetermined" and rel != "undetermined":
            error("R01", "unknown_material_requires_scope_review", gid)
        if (rule["affected"] == "nonempty" and not affected) or (rule["affected"] == "empty" and affected):
            error("R01", "relation_affected_claims_mismatch", gid)
        if not set(affected) <= set(required):
            error("R01", "unknown_affected_claim", gid)
        if rule["declared_dependency"] and any(dep not in required[c]["required_dependencies"] for c in affected if c in required):
            error("R01", "dependency_not_locked_for_claim", gid)
        if gap["dependency_trigger"] not in rule["triggers"]:
            error("R01", "trigger_relation_mismatch", gid)
        hits = {d for d, pat in MATERIAL_PATTERNS.items() if re.search(pat, gap["detail"])}
        if len(hits) > 1 or (hits and re.search(CURRENT_MATERIAL_PATTERN, gap["detail"])):
            error("R02", "known_mixed_material_requires_split", gid)
        elif hits and dep not in hits:
            error("R02", "known_material_dependency_mismatch", gid)
        if rel == "outside_locked_scope":
            if (not TASK_MODES[task["review_mode"]]["text_exclusions"] or dep not in EXCLUDABLE
                    or dep not in task["excluded_dependencies"]
                    or any(dep in c["required_dependencies"] for c in required.values())):
                error("R02", "outside_relation_not_authorized", gid)
            if dep not in hits:
                error("R02", "outside_material_not_identifiable", gid)
        referenced = set()
        typed_refs = set()
        for ref in gap["trigger_refs"]:
            token = (ref["type"], ref["id"])
            if token in typed_refs:
                error("R01", "duplicate_trigger_ref", gid)
            typed_refs.add(token)
            if ref["type"] == "document_evidence":
                if ref["id"] not in evidence:
                    error("E01", "unknown_trigger_evidence", gid)
                else:
                    referenced.add(ref["id"])
            else:
                check = checks.get(ref["id"])
                if not check:
                    error("E01", "unknown_trigger_check", gid)
                else:
                    referenced.update(check["document_evidence_refs"])
        # Two aliases to an identical source span do not constitute two sides.
        spans = {(evidence[e]["document_sha256"], evidence[e]["locator"], evidence[e]["quote"])
                 for e in referenced if e in evidence}
        if gap["dependency_trigger"] == "observed_context_conflict" and len(spans) < 2:
            error("R01", "observed_conflict_requires_two_explicit_spans", gid)
    for cid, claim in claims.items():
        linked_gaps = {g["gap_id"] for g in gaps.values() if cid in g["affected_claim_ids"]}
        if set(claim["gap_ids"]) != linked_gaps:
            error("R03", "claim_gap_reverse_link_mismatch", cid)
        linked_checks = {c["check_id"] for c in checks.values() if cid in c["claim_ids"]}
        if set(claim["check_ids"]) != linked_checks:
            error("R03", "claim_check_reverse_link_mismatch", cid)
        for check_id in claim["check_ids"]:
            if check_id not in checks or checks[check_id]["check_kind"] != "legal_comparison":
                error("R03", "claim_legal_check_invalid", cid)
        for obs_id in claim["observation_ids"]:
            if obs_id not in checks or checks[obs_id]["check_kind"] != "text_observation":
                error("R03", "claim_observation_invalid", cid)
        relations = {gaps[g]["task_relation"] for g in linked_gaps}
        policy = CLAIM_RULES[claim["assessment_state"]]
        if policy["finding"] == "required" and claim["finding"] is None:
            error("R03", "assessed_finding_required", cid)
        if policy["finding"] == "null" and claim["finding"] is not None:
            error("R03", "unresolved_claim_cannot_emit_finding", cid)
        if policy["requires_check"] and not claim["check_ids"]:
            error("R03", "assessed_requires_legal_check", cid)
        if policy["requires_relation"] and policy["requires_relation"] not in relations:
            error("R03", "state_requires_declared_gap", cid)
        if set(policy["forbids_relations"]) & relations:
            error("R03", "state_gap_relation_conflict", cid)
