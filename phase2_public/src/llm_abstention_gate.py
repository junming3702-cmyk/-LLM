"""Deterministic post-LLM schema and abstention gate.

The gate is deliberately independent of the language model. It canonicalizes
evidence metadata from the runtime retrieval package, rejects citations that
were not supplied to the model, and forces an insufficient-information or
human-review outcome when decisive legal elements are missing. A legal hit
alone is not a fact-law relation: bounded documentary review requires actual
runtime comparisons and a supplied, scoped requirement. Under checkpoint03
policy, a concrete risk supported by usable Level 1-3 evidence remains a
human-legal-review outcome even when project scope metadata is incomplete;
Level 4 evidence is usable only after local applicability is matched.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from typing import Any
from external_fallback_v2 import is_usable_legal_basis as _is_usable_legal_basis

from conclusion_contract_v2 import (
    CANONICAL_CONCLUSION_STATES,
    CONCLUSION_CONTRACT_VERSION,
    INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM,
    LEGACY_THREE_CLASS_MAPPING,
    LEGACY_THREE_CLASS_CONCLUSION_MAPPING,
    NO_APPLICABLE_LEGAL_BASIS_NEEDS_HUMAN_CONFIRM,
    NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE,
    REQUIRES_HUMAN_LEGAL_CONFIRM,
    REQUIRES_HUMAN_LEGAL_REVIEW,
    canonicalize_conclusion_type,
    legacy_test_result,
)


DECISIVE_FIELDS = (
    "subject",
    "conduct_or_condition",
    "jurisdiction_and_scope",
    "legal_consequence",
)
MISSING_STATES = {"missing", "conflicting", "unknown", ""}
VALID_COVERAGE_STATES = {"supported", "missing", "conflicting", "not_applicable"}
RISK_CONCLUSION_TYPES = {
    REQUIRES_HUMAN_LEGAL_CONFIRM,
    REQUIRES_HUMAN_LEGAL_REVIEW,
}
RISK_CATEGORIES = {
    "potential_non_compliance",
    "internal_inconsistency",
    "ambiguity_or_unclear_obligation",
    "temporal_or_version_uncertainty",
    "cross_document_link_missing_or_inconsistent",
    "out_of_scope_or_unverifiable",
}
NO_ISSUE_CATEGORIES = {"no_issue_identified"}
SEVERITY_CAP_AT_MEDIUM = {
    "procedural_or_temporal_concern",
    "missing_document_only",
    "scope_or_version_uncertainty",
}
PROCESSING_LABEL_VALUES = {"accepted", "revised", "rejected"}
MANDATORY_MISSING_RELATION_TYPES = {
    "mandatory_material_missing",
    "mandatory_requirement_missing",
    "required_document_not_provided",
    "required_evidence_missing",
}
MANDATORY_REQUIREMENT_SOURCES = {
    "law",
    "legal_requirement",
    "law_and_tender_document",
    "tender_document",
    "tender_requirement",
}
EXPLICIT_MISSING_DOCUMENT_STATUSES = {
    "absent",
    "missing",
    "not_found_in_submitted_material",
    "not_provided",
    "not_submitted",
}
CONFIRMATION_PREDICATES = (
    "fact_present",
    "law_requirement_present",
    "scope_applicable",
    "relation_explicit",
    "evidence_independent",
    "no_unresolved_conflict",
)
EXTERNAL_COMPLETED_NO_HIT_STATUSES = {"completed_no_hit"}
EXTERNAL_SUCCESS_STATUSES = {
    "completed_no_hit",
    "completed_with_candidates",
}
EXTERNAL_FAILURE_STATUSES = {
    "failed",
    "network_failure",
    "schema_failure",
    "blocked",
    "running",
    "not_called",
    "pending_provider",
    "pending_human_scope_attestation",
}
TABLE_HEADERS = (
    "测试结果",
    "合同原文",
    "结论",
    "风险类别",
    "法规依据",
    "证据边界",
    "Assistant recommendation",
)


def _set_field(target: dict, key: str, value: Any, actions: list[str], path: str) -> None:
    if target.get(key) != value:
        target[key] = value
        actions.append(f"corrected {path}.{key}")


def _is_external_source(item: dict) -> bool:
    return bool(
        item.get("external_source")
        or item.get("external_candidate") is True
        or item.get("external_candidate_status")
        or item.get("source_role") == "external_source"
        or item.get("source_role") == "external_candidate"
        or item.get("provenance_origin") == "external"
        or item.get("acquisition_channel") == "external_retrieval"
    )


def _external_evidence_is_pending(item: dict) -> bool:
    verification_status = item.get("verification_status")
    confirmation_status = item.get("human_confirmation_status")
    eligibility = item.get("legal_evidence_eligibility")
    return (
        verification_status
        in {
            "pending_human_verification",
            "pending",
            "unverified",
            "not_admitted",
        }
        or confirmation_status
        not in {"confirmed", "approved", "verified", "human_confirmed"}
        or eligibility in {"verification_only", "not_admitted"}
    )


def _confirmation_candidate_from_finding(finding: dict) -> bool:
    """Mark a review candidate without making a confirmation decision.

    This flag may use the model's requested relation as a queueing signal, but
    it never treats severity or confidence as legal validation.  Only the
    runtime record checked by ``_runtime_claim_confirmation`` can promote a
    finding to ``requires_human_legal_confirm``.
    """

    state = canonicalize_conclusion_type(finding.get("conclusion_type"))
    relation = finding.get("compliance_relation")
    category = finding.get("risk_category")
    return bool(
        state in {REQUIRES_HUMAN_LEGAL_CONFIRM, REQUIRES_HUMAN_LEGAL_REVIEW}
        or relation in {"potential_non_compliance", "requirement_not_shown"}
        or category in {"potential_non_compliance", "internal_inconsistency"}
    )


def _select_runtime_claim_confirmation(runtime_input: dict, finding: dict) -> dict | None:
    """Select a finding-bound runtime validation record.

    This function deliberately reads only runtime-input locations.  A field
    placed inside the LLM finding is never accepted as validation.
    """

    containers: list[Any] = [
        runtime_input.get("claim_confirmation_validation"),
        (runtime_input.get("runtime_audit") or {}).get("claim_confirmation_validation"),
        (runtime_input.get("decision_audit") or {}).get("claim_confirmation_validation"),
    ]
    issue_id = finding.get("issue_id") or runtime_input.get("issue_id")
    finding_id = finding.get("finding_id")
    for container in containers:
        if isinstance(container, dict):
            if isinstance(container.get("findings"), list):
                candidates = container["findings"]
            elif isinstance(container.get("records"), list):
                candidates = container["records"]
            elif any(key in container for key in ("predicates", "validation_predicates", "validated")):
                candidates = [container]
            else:
                candidates = []
        elif isinstance(container, list):
            candidates = container
        else:
            candidates = []
        for record in candidates:
            if not isinstance(record, dict):
                continue
            if record.get("issue_id") and issue_id and record["issue_id"] != issue_id:
                continue
            if record.get("finding_id") and finding_id and record["finding_id"] != finding_id:
                continue
            return record
    return None


def _explicit_runtime_failure(runtime_input: dict, record: dict | None) -> str:
    """Return an explicit runtime failure marker, without inferring one."""

    if isinstance(record, dict):
        for key in ("unresolved_failures", "validation_errors", "errors"):
            value = record.get(key)
            if isinstance(value, list) and value:
                return f"runtime validation reported {key}"
            if isinstance(value, str) and value.strip():
                return f"runtime validation reported {key}"
        for key in ("schema_status", "network_status"):
            if record.get(key) in {"failed", "error", "unresolved"}:
                return f"runtime validation {key}={record[key]}"
    for container_key in ("runtime_health", "schema_audit", "network_audit"):
        container = runtime_input.get(container_key)
        if isinstance(container, dict) and container.get("status") in {"failed", "error", "unresolved"}:
            return f"{container_key} status={container['status']}"
    return ""


def _canonical_json(value: Any) -> str:
    """Serialize a runtime value deterministically for binding hashes."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _sha256_text(value: Any) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_text(_canonical_json(value))


def _first_nested(mapping: dict, *paths: tuple[str, ...]) -> Any:
    """Return the first existing value from a small set of nested paths."""

    for path in paths:
        value: Any = mapping
        found = True
        for key in path:
            if not isinstance(value, dict) or key not in value:
                found = False
                break
            value = value[key]
        if found:
            return value
    return None


def _runtime_validator_source_is_allowed(record: dict) -> bool:
    """Reject model/LLM-originated records at the confirmation boundary."""

    for key in (
        "llm_provided",
        "model_provided",
        "assistant_provided",
        "is_model_output",
    ):
        if record.get(key) is True:
            return False
    source_values = [
        record.get("record_origin"),
        record.get("validation_record_origin"),
        record.get("origin"),
        record.get("producer_type"),
        record.get("validation_source"),
        record.get("producer"),
        record.get("validated_by"),
    ]
    joined = " ".join(str(value).lower() for value in source_values if value)
    if any(marker in joined for marker in ("llm", "model", "assistant", "response")):
        return False
    return any(
        marker in joined
        for marker in ("runtime", "validator", "gate", "retrieval", "audit")
    )


def _confirmation_fact_conflict_failure(record: dict) -> str:
    """Reject invalid decisive-fact rows and unresolved relation conflicts."""

    for key in ("decisive_facts", "fact_validations", "validated_facts"):
        value = record.get(key)
        if value is None:
            continue
        rows = value if isinstance(value, list) else [value]
        for row in rows:
            if row is False:
                return f"runtime validation {key} contains false fact"
            if not isinstance(row, dict):
                continue
            if row.get("valid") is False or row.get("validated") is False:
                return f"runtime validation {key} contains invalid fact"
            if row.get("status") in {"invalid", "missing", "conflicting", "unresolved", "rejected"}:
                return f"runtime validation {key} contains status={row['status']}"
    for key in ("unresolved_conflicts", "claim_conflicts", "conflicts"):
        value = record.get(key)
        if value:
            return f"runtime validation reported unresolved {key}"
    return ""


def _runtime_validator_policy(runtime_input: dict) -> Any:
    """Locate the authoritative policy object used by the runtime validator."""

    for container in (
        runtime_input,
        runtime_input.get("runtime_audit"),
        runtime_input.get("decision_audit"),
        runtime_input.get("runtime_constraints"),
    ):
        if not isinstance(container, dict):
            continue
        for key in ("validator_policy", "claim_validator_policy", "validation_policy"):
            if key in container:
                return container[key]
    return None


def _runtime_context(runtime_input: dict) -> Any:
    return runtime_input.get("project_context") or runtime_input.get("runtime_project_context")


def _runtime_contract(runtime_input: dict) -> dict:
    value = runtime_input.get("contract_evidence")
    return value if isinstance(value, dict) else {}


def _runtime_evidence_by_id(runtime_input: dict) -> dict[str, dict]:
    result: dict[str, dict] = {}
    values = runtime_input.get("retrieved_legal_evidence")
    if not isinstance(values, list):
        return result
    for item in values:
        if isinstance(item, dict) and item.get("chunk_id"):
            result[str(item["chunk_id"])] = item
    return result


def _binding_hash(record: dict, names: tuple[str, ...], nested_names: tuple[tuple[str, ...], ...]) -> Any:
    return _first_nested(
        record,
        *[(name,) for name in names],
        *nested_names,
        ("hashes", names[0]) if names else ("hash",),
    )


def _binding_object(record: dict, *keys: str) -> dict:
    for key in keys:
        value = record.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _runtime_claim_confirmation(
    runtime_input: dict,
    finding: dict,
    evidence: list[dict],
) -> dict:
    """Validate the runtime-only fact-to-law relation required for confirm.

    Every predicate is required as a literal boolean.  The model's own
    ``severity_basis``, ``risk_severity`` and confidence values are not used
    to establish trust.
    """

    candidate = _confirmation_candidate_from_finding(finding)
    record = _select_runtime_claim_confirmation(runtime_input, finding)
    base = {
        "available": isinstance(record, dict),
        "trusted": False,
        "candidate": candidate,
        "validated_evidence_chunk_ids": [],
        "predicates": {},
        "validation_source": "",
        "validation_basis": "",
        "binding_checks": {},
        "runtime_record_origin_verified": False,
        "not_upgraded_reason": "",
    }
    if record is None:
        base["not_upgraded_reason"] = (
            "没有运行时提供且与 finding 绑定的 claim_confirmation_validation；"
            "模型 severity/confidence 不能单独升级为明确违规确认。"
        )
        return base

    predicates = record.get("predicates") or record.get("validation_predicates")
    if not isinstance(predicates, dict):
        base["not_upgraded_reason"] = "运行时确认记录缺少结构化 predicates。"
        return base
    base["predicates"] = {
        key: predicates.get(key) for key in CONFIRMATION_PREDICATES if key in predicates
    }

    source = (
        record.get("validation_source")
        or record.get("producer")
        or record.get("validated_by")
        or record.get("source")
        or ""
    )
    basis = record.get("validation_basis") or record.get("basis") or ""
    base["validation_source"] = str(source)
    base["validation_basis"] = str(basis)
    evidence_ids = record.get("validated_evidence_chunk_ids") or record.get("evidence_chunk_ids") or []
    if isinstance(evidence_ids, str):
        evidence_ids = [evidence_ids]
    if not isinstance(evidence_ids, list):
        evidence_ids = []
    evidence_ids = [str(value) for value in evidence_ids if str(value).strip()]
    base["validated_evidence_chunk_ids"] = evidence_ids

    missing = [
        key for key in CONFIRMATION_PREDICATES if predicates.get(key) is not True
    ]
    runtime_evidence = _runtime_evidence_by_id(runtime_input)
    runtime_ids = set(runtime_evidence)
    finding_ids = {
        str(item.get("chunk_id")) for item in evidence if item.get("chunk_id")
    }
    selected_items = [
        item for item in evidence if item.get("chunk_id") in set(evidence_ids)
    ]
    failure = _explicit_runtime_failure(runtime_input, record)
    status_ok = record.get("validated") is True or record.get("status") == "validated"
    evidence_binding_ok = (
        bool(evidence_ids)
        and set(evidence_ids).issubset(runtime_ids)
        and set(evidence_ids).issubset(finding_ids)
        and bool(selected_items)
        and all(_is_usable_legal_basis(item) for item in selected_items)
    )
    identity_ok = bool(source) and bool(basis)

    # A confirmation record is trusted only when it binds the current issue,
    # project and finding to the *actual* runtime objects.  Hashes are
    # recomputed here from runtime content; a model-provided copy of the text
    # or a pair of matching strings is never sufficient.
    record_issue_id = _first_nested(
        record,
        ("issue_id",),
        ("claim_binding", "issue_id"),
        ("binding", "issue_id"),
    )
    record_project_id = _first_nested(
        record,
        ("project_id",),
        ("claim_binding", "project_id"),
        ("binding", "project_id"),
    )
    record_finding_id = _first_nested(
        record,
        ("finding_id",),
        ("claim_binding", "finding_id"),
        ("binding", "finding_id"),
    )
    issue_binding_ok = bool(runtime_input.get("issue_id")) and record_issue_id == runtime_input.get("issue_id") and record_issue_id == finding.get("issue_id")
    project_binding_ok = bool(runtime_input.get("project_id")) and record_project_id == runtime_input.get("project_id")
    finding_binding_ok = bool(finding.get("finding_id")) and record_finding_id == finding.get("finding_id")

    contract = _runtime_contract(runtime_input)
    contract_binding = _binding_object(
        record,
        "contract_binding",
        "contract_evidence_binding",
        "document_binding",
    )
    contract_id = contract.get("document_id")
    if contract_id is None:
        contract_id = _first_nested(record, ("document_id",), ("contract_document_id",))
    excerpt_hash = _first_nested(
        record,
        ("contract_excerpt_sha256",),
        ("document_excerpt_sha256",),
        ("contract_content_sha256",),
        ("contract_binding", "contract_excerpt_sha256"),
        ("contract_binding", "document_excerpt_sha256"),
        ("contract_binding", "contract_content_sha256"),
        ("contract_evidence_binding", "contract_excerpt_sha256"),
        ("hashes", "contract_excerpt_sha256"),
        ("hashes", "document_excerpt_sha256"),
    )
    locator_hash = _first_nested(
        record,
        ("contract_locator_sha256",),
        ("document_location_sha256",),
        ("document_locator_sha256",),
        ("contract_binding", "contract_locator_sha256"),
        ("contract_binding", "document_location_sha256"),
        ("contract_binding", "document_locator_sha256"),
        ("contract_evidence_binding", "contract_locator_sha256"),
        ("hashes", "contract_locator_sha256"),
        ("hashes", "document_location_sha256"),
    )
    actual_excerpt = contract.get("document_excerpt", "")
    actual_location = contract.get("document_location", "")
    contract_binding_ok = (
        bool(contract.get("document_id"))
        and contract_id == contract.get("document_id")
        and bool(actual_excerpt)
        and bool(actual_location)
        and isinstance(excerpt_hash, str)
        and excerpt_hash == _sha256_text(actual_excerpt)
        and isinstance(locator_hash, str)
        and locator_hash == _sha256_text(actual_location)
    )

    context = _runtime_context(runtime_input)
    actual_context_version = _first_nested(
        context if isinstance(context, dict) else {},
        ("context_version",),
        ("version",),
    )
    if actual_context_version is None:
        actual_context_version = runtime_input.get("context_version")
    record_context_version = _first_nested(
        record,
        ("project_context_version",),
        ("context_version",),
        ("context_binding", "project_context_version"),
        ("context_binding", "context_version"),
    )
    context_hash = _first_nested(
        record,
        ("project_context_sha256",),
        ("context_sha256",),
        ("context_binding", "project_context_sha256"),
        ("context_binding", "context_sha256"),
        ("hashes", "project_context_sha256"),
        ("hashes", "context_sha256"),
    )
    context_binding_ok = (
        context is not None
        and isinstance(context_hash, str)
        and context_hash == _sha256_json(context)
    )
    context_version_ok = bool(actual_context_version) and record_context_version == actual_context_version

    policy = _runtime_validator_policy(runtime_input)
    policy_hash = _first_nested(
        record,
        ("validator_policy_sha256",),
        ("validation_policy_sha256",),
        ("policy_sha256",),
        ("validator_policy_binding", "validator_policy_sha256"),
        ("validator_policy_binding", "policy_sha256"),
        ("policy_binding", "validator_policy_sha256"),
        ("policy_binding", "policy_sha256"),
        ("hashes", "validator_policy_sha256"),
        ("hashes", "policy_sha256"),
    )
    policy_id = _first_nested(
        record,
        ("validator_policy_id",),
        ("validation_policy_id",),
        ("policy_id",),
        ("validator_policy_binding", "validator_policy_id"),
        ("policy_binding", "validator_policy_id"),
    )
    actual_policy_id = policy.get("policy_id") if isinstance(policy, dict) else None
    if actual_policy_id is None and isinstance(policy, dict):
        actual_policy_id = policy.get("id")
    policy_hash_value = _sha256_json(policy) if isinstance(policy, (dict, list)) else _sha256_text(policy)
    policy_binding_ok = (
        policy is not None
        and bool(actual_policy_id)
        and policy_id == actual_policy_id
        and isinstance(policy_hash, str)
        and policy_hash == policy_hash_value
    )

    legal_bindings_value = (
        record.get("legal_evidence_bindings")
        or record.get("legal_bindings")
        or record.get("evidence_bindings")
        or record.get("legal_binding")
    )
    if isinstance(legal_bindings_value, dict):
        legal_bindings = {
            str(key): value for key, value in legal_bindings_value.items()
            if isinstance(value, dict)
        }
    elif isinstance(legal_bindings_value, list):
        legal_bindings = {
            str(value.get("chunk_id")): value
            for value in legal_bindings_value
            if isinstance(value, dict) and value.get("chunk_id")
        }
    else:
        legal_bindings = {}
    legal_hash_failures: list[str] = []
    for chunk_id in evidence_ids:
        actual = runtime_evidence.get(chunk_id)
        binding = legal_bindings.get(chunk_id)
        if actual is None or not isinstance(binding, dict):
            legal_hash_failures.append(f"{chunk_id}:missing_runtime_binding")
            continue
        quote_hash = _first_nested(
            binding,
            ("legal_quote_sha256",),
            ("quote_sha256",),
            ("hashes", "legal_quote_sha256"),
            ("hashes", "quote_sha256"),
        )
        article_hash = _first_nested(
            binding,
            ("article_sha256",),
            ("hashes", "article_sha256"),
        )
        version_hash = _first_nested(
            binding,
            ("source_version_sha256",),
            ("version_sha256",),
            ("hashes", "source_version_sha256"),
            ("hashes", "version_sha256"),
        )
        actual_version = actual.get("source_version")
        if not actual.get("legal_quote") or not actual.get("article") or not actual_version:
            legal_hash_failures.append(f"{chunk_id}:runtime_quote_article_or_version_missing")
            continue
        if not isinstance(quote_hash, str) or quote_hash != _sha256_text(actual.get("legal_quote")):
            legal_hash_failures.append(f"{chunk_id}:legal_quote_hash_mismatch")
        if not isinstance(article_hash, str) or article_hash != _sha256_text(actual.get("article")):
            legal_hash_failures.append(f"{chunk_id}:article_hash_mismatch")
        if not isinstance(version_hash, str) or version_hash != _sha256_text(actual_version):
            legal_hash_failures.append(f"{chunk_id}:source_version_hash_mismatch")
    legal_binding_ok = bool(evidence_ids) and not legal_hash_failures

    runtime_source_ok = _runtime_validator_source_is_allowed(record)
    fact_conflict_failure = _confirmation_fact_conflict_failure(record)
    if fact_conflict_failure:
        failure = "; ".join(value for value in (failure, fact_conflict_failure) if value)
    base["runtime_record_origin_verified"] = runtime_source_ok
    base["binding_checks"] = {
        "issue_id_bound": issue_binding_ok,
        "project_id_bound": project_binding_ok,
        "finding_id_bound": finding_binding_ok,
        "contract_content_and_locator_hashed": contract_binding_ok,
        "project_context_hashed": context_binding_ok,
        "project_context_version_bound": context_version_ok,
        "validator_policy_hashed": policy_binding_ok,
        "legal_quote_article_version_hashed": legal_binding_ok,
        "legal_hash_failures": legal_hash_failures,
        "runtime_record_origin_verified": runtime_source_ok,
    }
    binding_ok = (
        evidence_binding_ok
        and issue_binding_ok
        and project_binding_ok
        and finding_binding_ok
        and contract_binding_ok
        and context_binding_ok
        and context_version_ok
        and policy_binding_ok
        and legal_binding_ok
        and runtime_source_ok
    )
    trusted = not missing and status_ok and binding_ok and identity_ok and not failure
    base["trusted"] = trusted
    if not trusted:
        reasons = []
        if missing:
            reasons.append("缺少或未通过确认 predicates：" + ", ".join(missing))
        if not status_ok:
            reasons.append("运行时记录没有 validated=true 或 status=validated")
        if not evidence_binding_ok:
            reasons.append("验证证据未与当前 finding 和运行时 chunk 双向绑定，或证据不可独立使用")
        if not issue_binding_ok or not project_binding_ok or not finding_binding_ok:
            reasons.append("claim_confirmation_validation 未绑定当前 issue/project/finding")
        if not contract_binding_ok:
            reasons.append("合同实际内容或定位的运行时哈希未通过校验")
        if not context_binding_ok:
            reasons.append("project_context 的运行时哈希未通过校验")
        if not context_version_ok:
            reasons.append("project_context_version 未绑定或与运行时版本不一致")
        if not policy_binding_ok:
            reasons.append("validator policy 的运行时哈希或 policy_id 未通过校验")
        if not legal_binding_ok:
            reasons.append("法规原文、条款和版本的运行时哈希未全部通过校验")
        if not runtime_source_ok:
            reasons.append("确认记录来源不是允许的 runtime validator，或含有 model/LLM 来源标记")
        if not identity_ok:
            reasons.append("缺少 validation_source 或 validation_basis")
        if failure:
            reasons.append(failure)
        base["not_upgraded_reason"] = "；".join(reasons)
    return base


def _legacy_level_audit(runtime_input: dict) -> dict | None:
    """Return a legacy hierarchy audit only as a conservative fallback.

    Absence of a candidate in a finite manifest is never interpreted as a
    completed no-hit search.  This fallback therefore cannot make the pure
    no-law state eligible without the new explicit completion audit.
    """

    audit = runtime_input.get("hierarchy_retrieval_audit")
    return audit if isinstance(audit, dict) else None


def _no_applicable_legal_basis_audit(runtime_input: dict) -> tuple[bool, str]:
    """Check the completed-local-plus-external conditions for the no-law state."""

    audit = runtime_input.get("external_retrieval_audit")
    if not isinstance(audit, dict):
        return False, "缺少独立的 external_retrieval_audit，不能把有限 manifest 当作完成搜索。"

    nested_local = audit.get("local_search_completion")
    root_local = runtime_input.get("local_search_completion")
    if isinstance(nested_local, dict) and isinstance(root_local, dict):
        for key in (
            "status",
            "no_applicable_status_eligible",
            "no_usable_applicable_basis",
            "all_levels_executed",
            "completion_basis",
            "executed_levels",
            "not_applicable_levels",
            "decisive_missing_facts",
            "has_relevant_inconclusive",
            "blocked_scope_levels",
        ):
            if key in nested_local and key in root_local and nested_local[key] != root_local[key]:
                return False, f"root/nested local_search_completion mismatch on {key}."
    local = nested_local
    if not isinstance(local, dict):
        # The hierarchy worker also exports this completion record at the
        # runtime-input root.  Accept that authoritative location, but never
        # infer completion from a finite manifest or from model output.
        local = runtime_input.get("local_search_completion")
    if not isinstance(local, dict):
        return False, "缺少 local_search_completion。"
    local_status = local.get("status")
    local_eligible = local.get("no_applicable_status_eligible") is True or local.get(
        "no_usable_applicable_basis"
    ) is True
    if local_status not in EXTERNAL_SUCCESS_STATUSES and not (
        local_status in {"completed", "complete"} and local_eligible
    ):
        return False, f"本地四层检索未完成：status={local_status!r}。"
    if not local_eligible:
        return False, "本地检索没有运行时确认‘无可用适用独立法源’。"
    executed_levels = set(local.get("executed_levels") or [])
    not_applicable_levels = set(local.get("not_applicable_levels") or [])
    if not {"Level 1", "Level 2", "Level 3", "Level 4"}.issubset(
        executed_levels | not_applicable_levels
    ):
        return False, "Level 1–4 的完成或明确不适用记录不完整。"
    if local.get("all_levels_executed") is False:
        return False, "运行时记录表明四层级检索并未全部完成。"
    if local.get("completion_basis") not in {"provider_execution", "runtime_execution", "human_attested_manual_discovery"}:
        return False, "本地检索缺少可验证的 completion_basis。"
    if local.get("decisive_missing_facts") or local.get("has_relevant_inconclusive") is True:
        return False, "本地检索仍有决定性缺失事实或相关但未决结果。"
    if local.get("blocked_scope_levels"):
        return False, "本地检索仍有未解决的适用范围阻断。"
    if local.get("failure_reason"):
        return False, "本地检索存在未解决失败。"

    discovery = audit.get("discovery")
    if not isinstance(discovery, dict):
        return False, "缺少外部 discovery audit。"
    if discovery.get("requested") is not True:
        return False, "外部法规发现没有被明确请求。"
    discovery_status = discovery.get("status")
    external_search_completed = discovery.get("external_search_completed") is True or audit.get(
        "external_search_completed"
    ) is True
    if discovery_status not in EXTERNAL_COMPLETED_NO_HIT_STATUSES:
        return False, f"外部发现不是已完成无命中：status={discovery_status!r}。"
    if not external_search_completed:
        return False, "外部发现没有运行时 external_search_completed=true。"
    executed = discovery.get("executed") is True or discovery.get("provider_call_attempted") is True or discovery.get("http_called") is True
    human_attested = discovery.get("human_attested") is True or discovery.get("scope_completion_attested") is True
    if not executed and not human_attested:
        return False, "外部发现没有实际 provider 执行或人工范围确认。"
    if discovery.get("scope_completion_basis") not in {
        "provider_execution",
        "human_attested_manual_discovery",
    }:
        return False, "外部发现只有 manifest 或有限 URL 记录，不能视为完成搜索。"
    if discovery.get("scope_completion_basis") == "human_attested_manual_discovery" and not human_attested:
        return False, "人工手动外部发现缺少 human_attested=true。"
    candidates = discovery.get("candidates")
    candidate_count = discovery.get("candidate_count")
    if candidate_count is None and isinstance(candidates, list):
        candidate_count = len(candidates)
    no_independent_source = discovery.get("no_applicable_independent_source") is True or audit.get(
        "external_no_applicable_independent_source"
    ) is True
    if candidate_count not in {0, None} or (isinstance(candidates, list) and candidates):
        if not no_independent_source:
            return False, "外部发现仍有候选，缺少‘无适用独立来源’确认。"
    elif no_independent_source is not True:
        # A zero candidate count alone is not an independent no-law attestation.
        return False, "外部发现无候选但缺少 no_applicable_independent_source 运行时确认。"

    verification = audit.get("verification")
    if isinstance(verification, dict) and verification.get("requested") is True:
        if verification.get("executed") is not True or verification.get("status") not in EXTERNAL_SUCCESS_STATUSES:
            return False, "已请求的外部核验尚未完成。"
    if audit.get("unresolved_failures") or audit.get("unresolved_conflicts"):
        return False, "外部或事实审计仍有未解决失败/冲突。"
    if audit.get("external_failure_reason"):
        return False, "外部法规发现存在未解决失败。"
    if _explicit_runtime_failure(runtime_input, None):
        return False, "运行时仍存在 schema/network failure。"
    return True, "本地适用层级检索与外部无适用独立法源检索均有完成记录。"


def _minimal_response(runtime_input: dict, reason: str) -> dict:
    table = [{
        "test_result": "blocked",
        "contract_original_text": runtime_input.get("contract_evidence", {}).get("document_excerpt", ""),
        "conclusion": {
            "conclusion_type": INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM,
            "text": reason,
        },
        "risk_category": "missing_or_insufficient_evidence",
        "legal_basis": [],
        "evidence_boundary": "not_supported_by_current_corpus",
        "assistant_recommendation": {
            "substantive_conclusion": "当前模型结果未形成可交付的结构化结论。",
            "recommended_handling": "建议人工二次审核并修正该 finding。",
            "supporting_legal_evidence": [],
        },
        "review_processing_label": "revised",
    }]
    return {
        "run_id": runtime_input.get("run_id", ""),
        "project_id": runtime_input.get("project_id", ""),
        "conclusion_contract_version": CONCLUSION_CONTRACT_VERSION,
        "review_scope": runtime_input.get("review_scope", {}),
        "output_format": "review_table",
        "overall_review_status": "requires_human_second_review",
        "review_table": table,
        "table_markdown": _build_table_markdown(table),
        "findings": [],
        "project_summary": {
            "findings_count": 0,
            "high_priority_review_items": [],
            "evidence_gaps": [reason],
            "not_assessed": [],
            "supplement_candidate_pool_dependencies": [],
            "statement_boundary": "本结果仅辅助人工审查，不是最终法律结论",
        },
        "retrieval_audit": {
            "local_sources_used": [],
            "external_sources_used": [],
            "queries": [],
            "model_and_parameters": {},
            "high_trust_candidates_used": [],
            "supplement_candidate_pool_searched": False,
            "supplement_candidate_pool_used": False,
            "supplement_candidate_pool_use_reason": "",
            "supplement_candidate_pool_dependency": False,
            "unresolved_conflicts": [],
            "external_retrieval_called": False,
        },
        "stage3_decision_audit": {
            "conclusion_contract_version": CONCLUSION_CONTRACT_VERSION,
            "confirmation_validation_available": False,
            "confirmation_candidate_count": 0,
            "confirmed_count": 0,
            "no_applicable_legal_basis_eligible": False,
            "no_applicable_legal_basis_reason": reason,
        },
    }


def _canonicalize_evidence(finding: dict, runtime_input: dict, actions: list[str]) -> tuple[list[dict], bool, bool]:
    supplied: dict[str, dict] = {}
    duplicate_chunk_ids: set[str] = set()
    runtime_rows = runtime_input.get("retrieved_legal_evidence", [])
    if not isinstance(runtime_rows, list):
        runtime_rows = []
    for row in runtime_rows:
        if not isinstance(row, dict) or not row.get("chunk_id"):
            continue
        chunk_id = str(row["chunk_id"])
        if chunk_id in supplied:
            duplicate_chunk_ids.add(chunk_id)
            continue
        supplied[chunk_id] = row
    raw_evidence = finding.get("legal_evidence")
    if not isinstance(raw_evidence, list):
        raw_evidence = []

    canonical: list[dict] = []
    invalid = False
    for index, evidence in enumerate(raw_evidence):
        if not isinstance(evidence, dict):
            invalid = True
            actions.append(f"rejected legal_evidence[{index}] because it is not an object")
            continue
        chunk_id = evidence.get("chunk_id")
        if chunk_id is not None:
            chunk_id = str(chunk_id)
        if chunk_id in duplicate_chunk_ids:
            invalid = True
            actions.append(
                f"rejected legal_evidence[{index}] because runtime retrieval contains duplicate chunk_id={chunk_id!r}"
            )
            continue
        source = supplied.get(chunk_id)
        if source is None:
            invalid = True
            actions.append(f"rejected legal_evidence[{index}] because chunk_id was not in runtime retrieval")
            continue

        item = deepcopy(evidence)
        authoritative_fields = (
            "law",
            "article",
            "source_locator",
            "normative_level",
            "normative_type",
            "source_role",
            "parent_source_title",
            "corpus_partition",
            "evidence_weight",
            "requires_human_review",
            "citation_ready",
            "independent_legal_evidence",
            "legal_evidence_eligibility",
            "citation_mode",
            "jurisdiction_note",
            "scope_classification",
            "geographic_scope",
            "project_type_scope",
            "applicability_status",
            "applicability_basis",
            "evidence_support_confidence",
            "applicability_confidence",
            "retrieval_admission",
            "independent_evidence",
            "verification_status",
            "candidate_pool_warning",
            "reference_purpose",
            "retrieval_scores",
            "query_hits",
            "rank",
            # External provenance is runtime-owned and must survive
            # canonicalisation unchanged.  It is never inferred from the
            # model's source label or URL text.
            "external_source",
            "provenance_origin",
            "acquisition_channel",
            "official_source_url",
            "source_url",
            "issuer",
            "source_title",
            "source_version",
            "effective_date",
            "retrieved_at",
            "source_hash",
            "content_sha256",
            "human_confirmation_status",
            "external_candidate_status",
            "provider_id",
        )
        external_source = _is_external_source(source)
        external_pending = external_source and _external_evidence_is_pending(source)
        explicit_none_fields = {
            field for field in authoritative_fields
            if field in source and source.get(field) is None
        }
        for field in authoritative_fields:
            if (field not in source or field in explicit_none_fields) and field in item:
                del item[field]
                actions.append(
                    f"discarded model-supplied legal_evidence[{index}].{field} absent or null in runtime metadata"
                )
        for field in authoritative_fields:
            if field in explicit_none_fields:
                # Keep runtime denials visible to the shared admission predicate.
                item[field] = None
                continue
            value = source.get(field)
            if value is None and field == "independent_legal_evidence":
                if external_source:
                    # Legacy local metadata may infer independence for old
                    # local chunks.  External evidence must opt in through
                    # an explicit, runtime-approved record.
                    value = False
                else:
                    value = not (
                        source.get("legal_evidence_eligibility") == "supplement_only"
                        or source.get("source_role") == "practice_material_only"
                    )
            elif value is None and field == "legal_evidence_eligibility":
                value = (
                    "verification_only"
                    if external_source
                    else (
                        "supplement_only"
                        if source.get("source_role") == "practice_material_only"
                        else "independent_candidate"
                    )
                )
            elif value is None and field == "citation_mode":
                value = (
                    "verification_only"
                    if external_source
                    else (
                        "contextual_only"
                        if source.get("source_role") == "practice_material_only"
                        else "verbatim_source_citation"
                    )
                )
            if value is not None:
                _set_field(item, field, value, actions, f"legal_evidence[{index}]")
        # Explicit runtime negatives override every legacy alias or model
        # value.  A null admission is fail-closed, while a missing admission
        # remains compatible with the frozen local corpus.
        if source.get("independent_legal_evidence") is not True or (
            "independent_evidence" in source and source.get("independent_evidence") is not True
        ):
            _set_field(
                item,
                "independent_legal_evidence",
                False,
                actions,
                f"legal_evidence[{index}]",
            )
            _set_field(item, "independent_evidence", False, actions, f"legal_evidence[{index}]")
        if "retrieval_admission" in source and source.get("retrieval_admission") is None:
            _set_field(
                item,
                "retrieval_admission",
                "excluded_pending_review",
                actions,
                f"legal_evidence[{index}]",
            )
        if external_pending:
            cecn_candidate = bool(
                source.get("cecn_policy") is True
                or source.get("provider_id") in {"cecn", "CECN"}
                or "cecn.gov.cn" in str(source.get("source_url") or source.get("official_source_url") or "")
            )
            _set_field(
                item,
                "independent_legal_evidence",
                False,
                actions,
                f"legal_evidence[{index}]",
            )
            _set_field(
                item,
                "legal_evidence_eligibility",
                "supplement_only" if cecn_candidate else "verification_only",
                actions,
                f"legal_evidence[{index}]",
            )
            _set_field(
                item,
                "citation_mode",
                "contextual_only" if cecn_candidate else "verification_only",
                actions,
                f"legal_evidence[{index}]",
            )
            actions.append(
                f"external legal_evidence[{index}] remains pending human verification and is not independent"
            )
        _set_field(item, "legal_quote", source.get("legal_quote", ""), actions, f"legal_evidence[{index}]")
        if "independent_evidence" not in item and "independent_legal_evidence" in item:
            _set_field(
                item,
                "independent_evidence",
                item.get("independent_legal_evidence"),
                actions,
                f"legal_evidence[{index}]",
            )

        if not item.get("source_locator") or not item.get("legal_quote"):
            invalid = True
            actions.append(f"rejected legal_evidence[{index}] because locator or quote is empty")
            continue
        if external_source:
            external_url = source.get("source_url") or source.get("official_source_url")
            external_hash = source.get("content_sha256") or source.get("source_hash")
            required_external_fields = (
                external_url,
                source.get("issuer"),
                source.get("source_title"),
                source.get("source_version"),
                source.get("effective_date"),
                source.get("retrieved_at"),
                external_hash,
                source.get("article"),
                source.get("legal_quote"),
                source.get("source_locator"),
            )
            if any(value is None or value == "" for value in required_external_fields):
                invalid = True
                actions.append(
                    f"rejected external legal_evidence[{index}] because source URL/identity/version/hash/locator is incomplete"
                )
                continue
        canonical.append(item)

    finding["legal_evidence"] = canonical
    only_supplementary = bool(canonical) and all(
        item.get("independent_legal_evidence") is False
        or item.get("legal_evidence_eligibility") == "supplement_only"
        or item.get("source_role") == "practice_material_only"
        for item in canonical
    )
    return canonical, invalid, only_supplementary


def _canonicalize_contract_evidence(
    finding: dict,
    runtime_input: dict,
    actions: list[str],
    path: str,
) -> None:
    """Replace model document facts and nested locators with runtime facts."""

    contract = runtime_input.get("contract_evidence")
    contract = contract if isinstance(contract, dict) else {}
    runtime_values = {
        "document_id": contract.get("document_id", ""),
        "document_location": contract.get("document_location", ""),
        "document_excerpt": contract.get("document_excerpt", ""),
    }
    for field, value in runtime_values.items():
        _set_field(finding, field, value, actions, path)

    nested = finding.get("contract_evidence")
    if isinstance(nested, dict):
        nested_rows: list[Any] = [nested]
    elif isinstance(nested, list):
        nested_rows = nested
    else:
        nested_rows = []
    for index, row in enumerate(nested_rows):
        if not isinstance(row, dict):
            continue
        nested_path = f"{path}.contract_evidence[{index}]"
        aliases = {
            "document_id": runtime_values["document_id"],
            "document_location": runtime_values["document_location"],
            "document_excerpt": runtime_values["document_excerpt"],
            "location": runtime_values["document_location"],
            "excerpt": runtime_values["document_excerpt"],
            "document_locator": runtime_values["document_location"],
        }
        for field, value in aliases.items():
            _set_field(row, field, value, actions, nested_path)


def _runtime_violation_records(runtime_input: dict) -> list[dict]:
    """Collect issue/evidence-scoped violation records from runtime audit."""

    audit = runtime_input.get("hierarchy_retrieval_audit")
    if not isinstance(audit, dict):
        return []
    records: list[dict] = []
    for level in audit.get("levels", []) or []:
        if not isinstance(level, dict):
            continue
        level_state = level.get("level_state")
        level_flag = level.get("violation_or_inconsistency_detected") is True
        if level_state != "violation_or_inconsistency_detected" and not level_flag:
            continue
        chunk_ids = set(level.get("violation_chunk_ids") or level.get("selected_chunk_ids") or [])
        finding_id = level.get("finding_id") or level.get("affected_finding_id")
        issue_id = level.get("issue_id")
        phase_rows = level.get("phases")
        if not isinstance(phase_rows, list):
            phase_rows = level.get("phase_results")
        if not isinstance(phase_rows, list):
            phase_rows = []
        for phase in phase_rows:
            if not isinstance(phase, dict):
                continue
            phase_state = phase.get("level_state")
            if phase_state == "violation_or_inconsistency_detected" or level_flag:
                chunk_ids.update(phase.get("violation_chunk_ids") or [])
                chunk_ids.update(phase.get("selected_chunk_ids") or [])
            finding_id = finding_id or phase.get("finding_id") or phase.get("affected_finding_id")
            issue_id = issue_id or phase.get("issue_id")
        chunk_ids = {str(value) for value in chunk_ids if str(value).strip()}
        # A level flag without an exact evidence binding is not distributed to
        # every finding.  It remains visible in the raw cascade audit.
        if not chunk_ids:
            continue
        records.append(
            {
                "level": level.get("level", ""),
                "chunk_ids": sorted(chunk_ids),
                "finding_id": finding_id,
                "issue_id": issue_id or runtime_input.get("issue_id"),
            }
        )
    return records


def _runtime_violation_for_finding(
    runtime_input: dict,
    finding: dict,
    all_findings: list[Any],
) -> list[dict]:
    """Return only violation records bound to this finding's evidence."""

    finding_issue_id = finding.get("issue_id") or runtime_input.get("issue_id")
    finding_id = finding.get("finding_id")
    finding_chunk_ids = {
        str(item.get("chunk_id"))
        for item in finding.get("legal_evidence", []) or []
        if isinstance(item, dict) and item.get("chunk_id")
    }
    matches: list[dict] = []
    records = _runtime_violation_records(runtime_input)
    for record in records:
        if record.get("issue_id") and record["issue_id"] != finding_issue_id:
            continue
        if record.get("finding_id") and record["finding_id"] != finding_id:
            continue
        overlap = finding_chunk_ids.intersection(record.get("chunk_ids", []))
        if not overlap:
            continue
        if not record.get("finding_id"):
            other_findings = []
            for other in all_findings:
                if not isinstance(other, dict):
                    continue
                if (other.get("issue_id") or runtime_input.get("issue_id")) != finding_issue_id:
                    continue
                other_ids = {
                    str(item.get("chunk_id"))
                    for item in other.get("legal_evidence", []) or []
                    if isinstance(item, dict) and item.get("chunk_id")
                }
                if other_ids.intersection(record.get("chunk_ids", [])):
                    other_findings.append(other)
            # A shared article/chunk is not enough to assign a violation to
            # multiple findings.  The runtime producer must bind a finding id
            # in that case.
            if len(other_findings) != 1:
                continue
        matches.append({**record, "overlap_chunk_ids": sorted(overlap)})
    return matches


def _runtime_fact_law_relation_records(runtime_input: dict) -> list[dict]:
    """Collect only explicit runtime fact-to-law relation records.

    A model finding is not a fact validator.  This separate runtime channel is
    intentionally narrow: a producer must state that a requirement is
    mandatory at the finding's obligation phase and that the required material
    was actually absent.  The ordinary hierarchy audit is not treated as this
    relation because a law hit alone does not prove a missing document.
    """

    records: list[dict] = []
    seen: set[int] = set()
    for parent in (
        runtime_input,
        runtime_input.get("runtime_audit"),
        runtime_input.get("decision_audit"),
    ):
        if not isinstance(parent, dict):
            continue
        for key in (
            "fact_law_relation_audit",
            "runtime_fact_law_relation_audit",
            "fact_law_relations",
        ):
            container = parent.get(key)
            if isinstance(container, list):
                candidates = container
            elif isinstance(container, dict):
                candidates = []
                for rows_key in ("records", "relations", "findings", "claims"):
                    if isinstance(container.get(rows_key), list):
                        candidates = container[rows_key]
                        break
                if not candidates and any(
                    field in container
                    for field in (
                        "mandatory_requirement",
                        "relation_type",
                        "actual_document_status",
                        "document_status",
                    )
                ):
                    candidates = [container]
            else:
                candidates = []
            for record in candidates:
                if not isinstance(record, dict) or id(record) in seen:
                    continue
                seen.add(id(record))
                records.append(record)
    return records


def _string_set(value: Any) -> set[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = []
    return {str(item).strip() for item in values if str(item).strip()}


def _runtime_mandatory_missing_relation(
    runtime_input: dict,
    finding: dict,
    usable_evidence: list[dict],
) -> dict:
    """Validate a finding-bound runtime assertion of mandatory material absence.

    This is deliberately not the confirmation gate.  It only permits a
    ``requirement_not_shown``/missing-material claim to remain a potential risk
    when an independent runtime producer has supplied all of the required
    bindings.  No model field is read here.
    """

    records = _runtime_fact_law_relation_records(runtime_input)
    result = {
        "available": bool(records),
        "eligible": False,
        "matched_record_count": 0,
        "matched_evidence_chunk_ids": [],
        "required_at_stage": "",
        "not_eligible_reason": "no runtime fact-law relation record provided",
    }
    runtime_issue_id = runtime_input.get("issue_id")
    finding_issue_id = finding.get("issue_id") or runtime_issue_id
    finding_id = finding.get("finding_id")
    finding_phase = finding.get("obligation_phase")
    usable_ids = {
        str(item.get("chunk_id"))
        for item in usable_evidence
        if isinstance(item, dict) and item.get("chunk_id")
    }
    failure_reasons: list[str] = []

    for record in records:
        record_issue_id = _first_nested(
            record,
            ("issue_id",),
            ("claim_binding", "issue_id"),
            ("binding", "issue_id"),
        )
        record_finding_id = _first_nested(
            record,
            ("finding_id",),
            ("claim_binding", "finding_id"),
            ("binding", "finding_id"),
        )
        evidence_ids = _string_set(
            _first_nested(
                record,
                ("evidence_chunk_ids",),
                ("legal_evidence_chunk_ids",),
                ("chunk_ids",),
                ("relation_binding", "evidence_chunk_ids"),
                ("claim_binding", "evidence_chunk_ids"),
                ("binding", "evidence_chunk_ids"),
            )
        )
        relation_type = str(
            _first_nested(
                record,
                ("relation_type",),
                ("relation",),
                ("claim_type",),
            )
            or ""
        ).strip()
        requirement_source = str(
            _first_nested(
                record,
                ("requirement_source",),
                ("requirement_origin",),
                ("source_type",),
                ("basis_type",),
            )
            or ""
        ).strip().lower()
        required_at_stage = _first_nested(
            record,
            ("required_at_stage",),
            ("obligation_phase",),
            ("stage",),
            ("requirement_binding", "obligation_phase"),
        )
        actual_status = str(
            _first_nested(
                record,
                ("actual_document_status",),
                ("document_status",),
                ("fact_status",),
                ("actual_status",),
                ("provided_status",),
            )
            or ""
        ).strip().lower()
        actual_missing = actual_status in EXPLICIT_MISSING_DOCUMENT_STATUSES
        if record.get("actual_document_present") is False and str(
            record.get("missing_reason") or ""
        ).strip():
            actual_missing = True
        validated = record.get("validated") is True or record.get("status") in {
            "validated",
            "confirmed",
            "matched",
        }
        stage_matches = (
            bool(finding_phase)
            and (
                required_at_stage == finding_phase
                or isinstance(required_at_stage, (list, tuple, set))
                and finding_phase in required_at_stage
            )
        )
        checks = {
            "issue_binding": bool(runtime_issue_id)
            and record_issue_id == runtime_issue_id
            and record_issue_id == finding_issue_id,
            "finding_binding": bool(finding_id) and record_finding_id == finding_id,
            "evidence_binding": bool(evidence_ids.intersection(usable_ids)),
            "record_origin": _runtime_validator_source_is_allowed(record),
            "validated": validated,
            "relation_type": relation_type in MANDATORY_MISSING_RELATION_TYPES,
            "mandatory_requirement": record.get("mandatory_requirement") is True,
            "requirement_source": requirement_source in MANDATORY_REQUIREMENT_SOURCES,
            "obligation_phase": stage_matches,
            "actual_missing": actual_missing,
            "runtime_failure_free": not bool(_explicit_runtime_failure(runtime_input, record)),
            "conflict_free": not bool(_confirmation_fact_conflict_failure(record)),
        }
        if all(checks.values()):
            result.update(
                {
                    "eligible": True,
                    "matched_record_count": 1,
                    "matched_evidence_chunk_ids": sorted(evidence_ids.intersection(usable_ids)),
                    "required_at_stage": finding_phase,
                    "not_eligible_reason": "",
                }
            )
            return result
        failed = [name for name, passed in checks.items() if not passed]
        failure_reasons.append(", ".join(failed))

    result["not_eligible_reason"] = (
        "runtime fact-law relation records did not satisfy: "
        + "; ".join(failure_reasons)
        if failure_reasons
        else result["not_eligible_reason"]
    )
    return result


def _is_level4(item: dict) -> bool:
    return item.get("normative_level") == "Level 4" or (
        item.get("scope_classification") == "local_regional"
        and item.get("normative_level") not in {"Level 1", "Level 2", "Level 3"}
    )


def _runtime_bounded_review(runtime_input: dict, usable_evidence: list[dict]) -> dict:
    """Recognize the approved, narrow documentary comparisons in supplied text.

    This is a review-scope check, NOT an independent fact validator or a legal
    finding. Values, document roles and requirements come from runtime text;
    no model coverage tag, issue ID or expected label establishes a discrepancy.
    Unrecognized relations retain the existing abstention/confirmation paths.
    """
    contract = _runtime_contract(runtime_input)
    fact = str(contract.get("document_excerpt") or "").strip()
    locator = str(contract.get("document_location") or "").strip()
    result = {"eligible": False, "claim": "", "missing_decisive_facts": [],
              "document_excerpt": fact, "document_location": locator,
              "supporting_chunk_ids": [], "requirement_quote": "",
              "requirement_locator": "", "limitation": "", "human_action": ""}
    if not fact or not locator:
        result["missing_decisive_facts"] = ["可定位的当前合同事实原文"]
        return result
    if contract.get("extraction_status") in {"failed", "unread", "incomplete"} or re.search(
        r"无法读取|未识别|OCR失败|提取失败|解析失败", fact
    ):
        result["missing_decisive_facts"] = ["读取成功的原文及完整记录；提取失败不能证明材料不存在"]
        return result

    def requirement(*terms: str) -> tuple[dict, str] | None:
        for item in usable_evidence:
            for sentence in re.split(r"[。；\n]", str(item.get("legal_quote") or "")):
                if all(term in sentence for term in terms):
                    return item, sentence.strip()
        return None

    def admit(claim: str, source: tuple[dict, str], limitation: str, action: str) -> dict:
        item, quote = source
        result.update(eligible=True, claim=claim,
                      supporting_chunk_ids=[item["chunk_id"]], requirement_quote=quote,
                      requirement_locator=" ".join(dict.fromkeys(str(item.get(k) or "")
                                                   for k in ("law", "article", "source_locator"))).strip(),
                      limitation=limitation, human_action=action)
        return result

    # Two stated values about the same validity period, not a conflicting tag
    # or two unrelated durations elsewhere in the excerpt.
    periods = re.search(
        r"(?:正文|招标文件)[^。；]{0,24}?投标有效期\s*(\d+)\s*(日|天)[，,；;]\s*"
        r"投标函(?:格式)?(?:写|载明|为|规定|[:：]){0,3}\s*(\d+)\s*(日|天)", fact)
    if periods and periods[1] != periods[3]:
        source = requirement("应当", "载明", "投标有效期")
        if source:
            return admit("同一投标有效期的两处记载不一致", source,
                         "仅复核记载差异，不推定投标无效。",
                         "人工核对正文与投标函的对应标段、起算点及有效版本，确认应采用的期限并统一记载。")

    places = re.search(r"招标文件[^。；]*开标地点(?:为|写为|是)([^，。；]+)[，,；;]"
                       r"\s*开标记录(?:写为|为|载明为|写)([^，。；]+)", fact)
    if places and places[1].strip() != places[2].strip():
        source = requirement("开标地点", "招标文件", "预先确定")
        if source:
            return admit("招标文件与开标记录的地点记载不一致", source,
                         "仅复核地点记载，不认定实际违规开标。",
                         "人工核对同一项目的招标文件、开标记录及地点变更通知，确认实际地点和有效版本。")

    agreement = re.search(r"(联合体协议|共同投标协议)(?:被)?列为资格文件[，,；;]"
                          r"\s*(?:但)?清单中(?:没有|未列出|未包含)该协议", fact)
    if agreement:
        source = requirement("共同投标协议", "提交")
        if source:
            return admit("已列资格文件要求与当前清单存在协议列项差异", source,
                         "只说明当前清单没有该项，不推定实际未提交协议或投标无效。",
                         "人工核对资格文件要求、完整清单及实际提交包，确认协议是否已收取并补正清单关联。")

    receipt = re.search(r"(?:招标文件)?修改通知引用(?:补充)?文件\s*([A-Za-z0-9一二三四五六七八九十]+)"
                        r"[，,；;]\s*投标人签收记录中(?:没有|未见|未记录)\s*\1(?:[。；]|$)", fact)
    if receipt:
        source = requirement("修改", "书面", "通知", "收受人")
        if source:
            return admit("修改通知所引用文件与当前签收记录存在关联缺口", source,
                         "仅说明当前签收记录未见该文件，不推定未送达或通知无效。",
                         "人工核对修改通知附件、发送记录与完整签收凭证，确认该文件是否随通知发送并收取。")

    # A qualification rule alone does not create a duty to supply its proof at
    # this stage. Require the same proof object in an explicit supplied duty.
    proof = re.search(r"(?:未提供|未提交|缺少|未见)([^，。；]{0,20}(?:执业资格证明|资质证明|资格证书))", fact)
    if proof:
        proof_name = proof[1]
        tender = re.search(r"招标文件(?:明确)?(?:要求|规定)[^。；]*?(?:应当|须|必须)提交"
                           + re.escape(proof_name), fact)
        source = requirement("提交", proof_name)
        if source and not re.search(r"(?:应当|必须|须)提交" + re.escape(proof_name), source[1]):
            source = None
        if source and source[0].get("applicability_status") != "matched":
            source = None
        if tender:
            # Tender requirement is locatable runtime text, with an admitted
            # selected legal rule requiring response to tender conditions.
            legal = requirement("投标文件", "招标文件", "响应")
            if legal:
                source = legal
                result["tender_requirement_quote"] = tender[0]
                result["tender_requirement_locator"] = locator
                result["tender_requirement_document_id"] = contract.get("document_id", "")
        if source:
            return admit("适用的证明提交要求与当前已审材料存在证明缺口", source,
                         "缺少当前材料中的证明不等于人员或企业没有资格。",
                         "人工核对该阶段的证明提交要求、人员身份、完整材料及证书，确认是否已提供有效证明。")
        result["missing_decisive_facts"] = ["当前阶段要求提交该项资格证明的适用条文或招标要求"]

    # These are gaps in the proposed comparison itself, irrespective of an
    # optimistic model coverage tag. Keep them scoped to the stated claim.
    decisive = (
        (r"(?:未提供|缺少|没有).{0,8}项目估算价", "项目估算价及实际保证金金额或比例"),
        (r"(?:未提供|缺少|没有).{0,8}投标有效期", "投标有效期、保证金有效期的实际数值与起算点"),
        (r"(?:未记录|没有|缺少|未提供).{0,5}(?:签发|领取|发送)日期", "签发/领取或发送日期及对应起算、截止或开工记录"),
        (r"未提供施工许可证或限额以下例外", "项目施工阶段、许可适用条件及实际许可/例外情况"),
        (r"未提供规划许可证", "本项目是否依法须办理规划许可及申请阶段、实际办理情况"),
        (r"(?:未提供|缺少).{0,10}(?:技术标准|检测标准|标准文本)", "适用标准的具体要求及实际检测或性能比较事实"),
    )
    for pattern, gap in decisive:
        if re.search(pattern, fact):
            result["missing_decisive_facts"].append(gap)
    if "开标时间和地点" in fact and "一致" in fact and not re.search(r"\d{1,2}[:：]\d{2}", fact):
        result["missing_decisive_facts"].append("实际开标时间与投标截止时间，以及对应预定地点")
    return result


def _bounded_requirement_text(bounded: dict) -> str:
    """Keep tender text with its document locator, separate from legal text."""
    tender_text = ""
    if bounded.get("tender_requirement_quote"):
        tender_text = (
            f"招标要求：{bounded.get('tender_requirement_document_id', '')} "
            f"{bounded['tender_requirement_locator']}“{bounded['tender_requirement_quote']}”。"
        )
    return tender_text + f"法规原文：{bounded['requirement_locator']}“{bounded['requirement_quote']}”。"


def _finding_claims_concrete_risk(finding: dict) -> bool:
    return (
        finding.get("conclusion_type") in RISK_CONCLUSION_TYPES
        or finding.get("risk_category") in RISK_CATEGORIES
        or finding.get("compliance_relation") in {
            "potential_non_compliance",
            "requirement_not_shown",
        }
    )


def _finding_requires_runtime_fact_relation(
    finding: dict,
    missing_fields: list[str],
) -> bool:
    """Require runtime fact support before treating a gap as a risk.

    A legal hit is not, by itself, evidence that a required document was
    absent.  The same rule applies when the finding lacks the subject or the
    conduct/condition needed to connect the contract fact to the provision.
    Missing jurisdiction is intentionally not included here: a national
    requirement with otherwise supported facts may remain a human-review risk.
    """

    if not _finding_claims_concrete_risk(finding):
        return False
    return bool(
        finding.get("compliance_relation") == "requirement_not_shown"
        or finding.get("risk_category") == "missing_or_insufficient_evidence"
        or finding.get("severity_basis") == "missing_document_only"
        or any(field in missing_fields for field in ("subject", "conduct_or_condition"))
    )


def _finding_is_explicitly_compliant(finding: dict) -> bool:
    return (
        finding.get("conclusion_type") == "no_supported_issue_found_within_review_scope"
        or finding.get("risk_category") in NO_ISSUE_CATEGORIES
        or finding.get("compliance_relation") == "explicitly_satisfied"
    )


def _finding_is_out_of_scope_reference(finding: dict) -> bool:
    if finding.get("scope_assessment") == "outside_current_corpus":
        return True
    if finding.get("compliance_relation") == "out_of_scope_reference":
        return True
    if finding.get("risk_category") == "out_of_scope_or_unverifiable":
        evidence = finding.get("legal_evidence", [])
        return bool(evidence) and all(
            isinstance(item, dict)
            and item.get("legal_evidence_eligibility")
            in {"supplement_only", "verification_only", "not_admitted"}
            or isinstance(item, dict)
            and item.get("source_role") == "practice_material_only"
            for item in evidence
        )
    return any(
        isinstance(item, dict)
        and item.get("reference_purpose") == "out_of_scope_context_only"
        for item in finding.get("legal_evidence", [])
    )


def _normalize_risk_severity(finding: dict, actions: list[str], path: str) -> None:
    severity = finding.get("risk_severity")
    basis = finding.get("severity_basis")
    category = finding.get("risk_category")
    if basis == "no_supported_issue":
        _set_field(finding, "risk_severity", "informational", actions, path)
    elif severity in {"high", "critical"} and (
        basis != "direct_mandatory_conflict"
        or basis in SEVERITY_CAP_AT_MEDIUM
        or category in {"temporal_or_version_uncertainty", "ambiguity_or_unclear_obligation"}
    ):
        _set_field(finding, "risk_severity", "medium", actions, path)


def _table_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def _test_result(finding: dict) -> str:
    return legacy_test_result(finding.get("conclusion_type"))


def _legal_basis_for_recommendation(finding: dict) -> list[dict]:
    return [
        {
            "chunk_id": evidence.get("chunk_id", ""),
            "law": evidence.get("law", ""),
            "article": evidence.get("article", ""),
            "normative_level": evidence.get("normative_level", ""),
            "source_locator": evidence.get("source_locator", ""),
            "legal_evidence_eligibility": evidence.get("legal_evidence_eligibility", ""),
            "reference_purpose": evidence.get("reference_purpose", ""),
        }
        for evidence in finding.get("legal_evidence", [])
        if isinstance(evidence, dict) and _is_usable_legal_basis(evidence)
    ]


def _unsupported_article_refs(text: Any, evidence: list[dict]) -> set[str]:
    cited = set(re.findall(r"第[一二三四五六七八九十百千万零〇0-9]+条", str(text or "")))
    allowed = {
        match
        for item in evidence
        if isinstance(item, dict) and _is_usable_legal_basis(item)
        for match in re.findall(
            r"第[一二三四五六七八九十百千万零〇0-9]+条",
            " ".join(str(item.get(key, "")) for key in ("article", "legal_quote")),
        )
    }
    return cited - allowed


def _default_processing_label(finding: dict) -> str:
    label = finding.get("review_processing_label")
    if label in PROCESSING_LABEL_VALUES:
        return label
    conclusion = canonicalize_conclusion_type(finding.get("conclusion_type"))
    if conclusion == NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE:
        return "accepted"
    if conclusion in {
        INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM,
        NO_APPLICABLE_LEGAL_BASIS_NEEDS_HUMAN_CONFIRM,
    }:
        return "revised"
    if not any(_is_usable_legal_basis(item) for item in finding.get("legal_evidence", []) if isinstance(item, dict)):
        return "rejected"
    return "revised"


def _default_substantive_recommendation(
    finding: dict,
    *,
    force_rebuild: bool = False,
) -> dict:
    recommendation = finding.get("assistant_recommendation")
    conclusion_state = canonicalize_conclusion_type(finding.get("conclusion_type"))
    # A stale model recommendation may still say "no issue" after the gate
    # has abstained.  Rebuild the recommendation for both information-limited
    # states so a positive conclusion cannot survive the final consistency
    # pass.
    allow_model_recommendation = conclusion_state == NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE
    if isinstance(recommendation, dict) and allow_model_recommendation and not force_rebuild:
        recommendation_text = " ".join(
            str(recommendation.get(key, ""))
            for key in ("substantive_conclusion", "recommended_handling")
        )
        unsupported_articles = _unsupported_article_refs(
            recommendation_text,
            [item for item in finding.get("legal_evidence", []) if isinstance(item, dict)],
        )
        if (
            recommendation.get("substantive_conclusion")
            and recommendation.get("recommended_handling")
            and not unsupported_articles
        ):
            recommendation = dict(recommendation)
            recommendation["supporting_legal_evidence"] = _legal_basis_for_recommendation(finding)
            return recommendation

    basis = _legal_basis_for_recommendation(finding)
    basis_names = []
    for item in basis:
        # ``source_locator`` is commonly identical to ``article``.  Do not
        # render labels such as "第二十六条 第二十六条" in the human-review
        # recommendation.
        label_parts = []
        for part in (item.get("law"), item.get("article"), item.get("source_locator")):
            if part and part not in label_parts:
                label_parts.append(part)
        label = " ".join(label_parts)
        if label:
            basis_names.append(label)
    basis_text = "、".join(basis_names) or "当前没有可作为独立依据的法规证据"
    conclusion = canonicalize_conclusion_type(finding.get("conclusion_type"))
    category = finding.get("risk_category")
    # Classify the substantive issue from the reasoning itself.  Human-action
    # boilerplate routinely says "不得直接作出废标/否决投标决定" and must not
    # create a false rejection-risk label.
    combined = str(finding.get("reasoning_conclusion", ""))
    if conclusion == NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE:
        substantive = "当前审查范围内未发现有充分证据支持的风险。"
        handling = "建议暂不将该条款列为风险项，但保留人工二次审核和审查范围限定。"
    elif conclusion == INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM:
        substantive = finding.get("reasoning_conclusion") or "当前缺少可定位的比较事实或适用要求，证据不足以判断该问题，不形成违规指控。"
        handling = finding.get("recommended_human_action") or "建议补充缺失文件、工程地点、工程类型或适用标准后进行人工二次审核。"
    elif conclusion == NO_APPLICABLE_LEGAL_BASIS_NEEDS_HUMAN_CONFIRM:
        substantive = "本地适用层级和已记录的外部法规发现均未找到可用的独立法规依据，当前不形成违规或合规判断。"
        handling = finding.get("recommended_human_action") or "建议人工确认检索范围、法规覆盖范围和是否存在未纳入当前语料库的适用法源。"
    elif conclusion == REQUIRES_HUMAN_LEGAL_CONFIRM:
        substantive = f"运行时已验证合同事实与 {basis_text} 的直接法规关系，建议人工确认该明确冲突及其适用的后续处理。"
        handling = finding.get("recommended_human_action") or "建议专业人员核对事实、法规适用条件和程序后确认；本结果不直接作出废标、中标或最终法律决定。"
    elif conclusion == REQUIRES_HUMAN_LEGAL_REVIEW:
        bounded = finding.get("runtime_bounded_review", {})
        if bounded.get("eligible"):
            basis = [item for item in basis if item["chunk_id"] in bounded["supporting_chunk_ids"]]
            substantive = (
                f"{bounded['claim']}：{bounded['document_location']}“{bounded['document_excerpt']}”。"
                + _bounded_requirement_text(bounded)
                + bounded["limitation"]
            )
            handling = bounded["human_action"] + "所有处理均须人工二次审核。"
        else:
            fact = finding.get("document_excerpt") or "当前调用未提供可定位的合同原文"
            location = finding.get("document_location") or "定位待补充"
            substantive = (
                f"待人工复核的事实为：{location}“{fact}”。"
                f"本次已准入的对照条文：{basis_text}。"
                "复核限于上述事实与具体适用要求的关系，不据此认定违反全部所列条文或作出最终法律处理。"
            )
            handling = "请人工逐项核对上述原文、所列条文的具体要求与适用条件，确认差异及完整材料后进行二次审核。"
    elif "围标" in combined or "串标" in combined or "串通投标" in combined:
        substantive = f"疑似存在围标/串标相关风险，涉及 {basis_text}。"
        handling = finding.get("recommended_human_action") or "建议人工核对不同投标人的文件编制来源、项目管理成员、报价关系及其他串通投标事实。"
    elif any(term in combined for term in ("否决投标", "废标", "无效投标", "拒收投标")):
        substantive = f"疑似涉及依法否决投标、拒收投标或其他不利处理的法定情形，涉及 {basis_text}。"
        handling = "建议人工依据所列法规核验事实是否达到依法否决、拒收或其他处理的法定条件；本结果不直接作出废标或中标决定。"
    elif category == "cross_document_link_missing_or_inconsistent":
        substantive = f"疑似存在跨文件证据不一致或关联缺失，涉及 {basis_text}。"
        handling = finding.get("recommended_human_action") or "建议人工对照相关合同、投标文件、附件和版本记录，确认事实链后再作处理。"
    elif category == "out_of_scope_or_unverifiable":
        substantive = "该问题超出当前法规库可独立核验的范围，当前不形成具体法律违规结论。"
        handling = finding.get("recommended_human_action") or "建议转交相应税务、技术标准或专业审批人员进行人工二次审核。"
    else:
        substantive = f"疑似存在与 {basis_text} 要求不一致的潜在合规风险。"
        handling = finding.get("recommended_human_action") or "建议依据所列法规证据进行人工二次法律复核，不直接作出最终法律处理决定。"
    return {
        "substantive_conclusion": substantive,
        "recommended_handling": handling,
        "supporting_legal_evidence": basis,
    }


def _build_review_table(response: dict) -> list[dict]:
    table = []
    for finding in response.get("findings", []):
        if not isinstance(finding, dict):
            continue
        legal_basis = []
        for evidence in finding.get("legal_evidence", []):
            if not isinstance(evidence, dict):
                continue
            legal_basis.append(
                {
                    "law": evidence.get("law", ""),
                    "article": evidence.get("article", ""),
                    "normative_level": evidence.get("normative_level", ""),
                    "source_locator": evidence.get("source_locator", ""),
                    "legal_evidence_eligibility": evidence.get("legal_evidence_eligibility", ""),
                    "reference_purpose": (
                        evidence.get("reference_purpose", "")
                        if _is_usable_legal_basis(evidence)
                        else "verification_lead_only：仅供人工核验，不作为指控依据"
                    ),
                }
            )
        table.append(
            {
                "test_result": _test_result(finding),
                "contract_original_text": finding.get("document_excerpt", ""),
                "conclusion": {
                    "conclusion_type": finding.get("conclusion_type", ""),
                    "text": finding.get("reasoning_conclusion", ""),
                },
                "risk_category": finding.get("risk_category", ""),
                "legal_basis": legal_basis,
                "evidence_boundary": finding.get("evidence_boundary", ""),
                "assistant_recommendation": deepcopy(finding.get("assistant_recommendation"))
                or _default_substantive_recommendation(finding),
                "review_processing_label": _default_processing_label(finding),
            }
        )
    return table


def _build_table_markdown(table: list[dict]) -> str:
    lines = [
        "整体状态：`requires_human_second_review`",
        "",
        "| " + " | ".join(TABLE_HEADERS) + " |",
        "|" + "|".join("---" for _ in TABLE_HEADERS) + "|",
    ]
    for row in table:
        conclusion = row.get("conclusion", {})
        conclusion_text = f"{conclusion.get('conclusion_type', '')}：{conclusion.get('text', '')}"
        basis_parts = []
        for item in row.get("legal_basis", []):
            label = " ".join(
                part
                for part in (
                    item.get("law"),
                    item.get("article"),
                    f"[{item.get('normative_level')}]" if item.get("normative_level") else "",
                    item.get("source_locator"),
                )
                if part
            )
            status = item.get("legal_evidence_eligibility")
            purpose = item.get("reference_purpose")
            if status:
                label += f" ({status}"
                if purpose:
                    label += f", {purpose}"
                label += ")"
            basis_parts.append(label)
        recommendation = row.get("assistant_recommendation", {})
        if isinstance(recommendation, dict):
            recommendation_text = (
                f"建议结论：{recommendation.get('substantive_conclusion', '')}"
                f"<br>建议处理：{recommendation.get('recommended_handling', '')}"
            )
        else:
            recommendation_text = str(recommendation)
        lines.append(
            "| "
            + " | ".join(
                _table_text(value)
                for value in (
                    row.get("test_result", ""),
                    row.get("contract_original_text", ""),
                    conclusion_text,
                    row.get("risk_category", ""),
                    "<br>".join(basis_parts),
                    row.get("evidence_boundary", ""),
                    recommendation_text,
                )
            )
            + " |"
        )
    return "\n".join(lines)


def _rebuild_project_summary(response: dict) -> dict:
    """Rebuild summary fields from canonical findings, never model prose."""

    findings = [
        finding for finding in response.get("findings", [])
        if isinstance(finding, dict)
    ]
    high_priority: list[str] = []
    evidence_gaps: list[str] = []
    supplement_dependencies: list[str] = []
    for finding in findings:
        finding_id = str(finding.get("finding_id", ""))
        state = canonicalize_conclusion_type(finding.get("conclusion_type"))
        if state in RISK_CONCLUSION_TYPES or finding.get("possible_over_alert") is True:
            if finding_id:
                high_priority.append(finding_id)
        coverage = finding.get("legal_element_coverage")
        if isinstance(coverage, dict):
            missing = [
                field for field in DECISIVE_FIELDS
                if coverage.get(field) not in VALID_COVERAGE_STATES
                or coverage.get(field) in MISSING_STATES
            ]
            if missing and finding_id:
                evidence_gaps.append(
                    f"{finding_id}: missing or unresolved legal elements: {', '.join(missing)}"
                )
        reason = finding.get("confirmation_not_upgraded_reason")
        if reason and finding_id:
            evidence_gaps.append(f"{finding_id}: {reason}")
        for evidence in finding.get("legal_evidence", []) or []:
            if not isinstance(evidence, dict):
                continue
            if evidence.get("legal_evidence_eligibility") in {
                "supplement_only",
                "verification_only",
                "not_admitted",
            } or evidence.get("retrieval_admission") in {
                "supplement_candidate_pool",
                "excluded_pending_review",
                "control_only",
            }:
                chunk_id = evidence.get("chunk_id", "")
                supplement_dependencies.append(f"{finding_id}:{chunk_id}")
    scope = response.get("review_scope")
    scope = scope if isinstance(scope, dict) else {}
    not_assessed = scope.get("documents_not_received_or_missing", [])
    if not isinstance(not_assessed, list):
        not_assessed = []
    return {
        "findings_count": len(findings),
        "high_priority_review_items": high_priority,
        "evidence_gaps": evidence_gaps,
        "not_assessed": deepcopy(not_assessed),
        "supplement_candidate_pool_dependencies": supplement_dependencies,
        "statement_boundary": "本结果仅辅助人工审查，不是最终法律结论",
    }


def _empty_findings_are_runtime_authorized(runtime_input: dict) -> bool:
    """Return True only for an explicit runtime statement that nothing is reviewable."""

    for container in (
        runtime_input,
        runtime_input.get("review_scope"),
        runtime_input.get("runtime_constraints"),
    ):
        if not isinstance(container, dict):
            continue
        for key in (
            "no_reviewable_issue",
            "no_reviewable_findings",
            "explicit_no_reviewable_issue",
            "allow_empty_findings",
        ):
            if container.get(key) is True:
                return True
    return False


def _validate_finding_ids(findings: list[Any], runtime_input: dict) -> list[str]:
    """Reject missing, duplicate, or cross-issue finding identifiers."""

    errors: list[str] = []
    expected_issue_id = runtime_input.get("issue_id")
    expected_finding_id = runtime_input.get("finding_id")
    seen_issue_ids: set[str] = set()
    seen_finding_ids: set[str] = set()
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            errors.append(f"findings[{index}] is not an object with an issue_id/finding_id")
            continue
        issue_id = finding.get("issue_id")
        finding_id = finding.get("finding_id")
        if not isinstance(issue_id, str) or not issue_id.strip():
            errors.append(f"findings[{index}] is missing issue_id")
        elif expected_issue_id and issue_id != expected_issue_id:
            errors.append(
                f"findings[{index}] issue_id={issue_id!r} does not match runtime issue_id={expected_issue_id!r}"
            )
        elif issue_id in seen_issue_ids:
            # Multiple findings may belong to one issue.  Repeating the issue
            # id is therefore valid; finding_id uniqueness is checked below.
            pass
        seen_issue_ids.add(issue_id)
        if not isinstance(finding_id, str) or not finding_id.strip():
            errors.append(f"findings[{index}] is missing finding_id")
        elif expected_finding_id and finding_id != expected_finding_id:
            errors.append(
                f"findings[{index}] finding_id={finding_id!r} does not match runtime finding_id={expected_finding_id!r}"
            )
        elif finding_id in seen_finding_ids:
            errors.append(f"duplicate finding_id={finding_id!r}")
        seen_finding_ids.add(finding_id)
    return errors


def _runtime_external_audit(runtime_input: dict) -> dict:
    """Build the output external audit from runtime fields only."""

    supplied = runtime_input.get("external_retrieval_audit")
    if isinstance(supplied, dict):
        audit = deepcopy(supplied)
        audit["audit_source"] = "runtime_only"
        return audit
    called = (runtime_input.get("runtime_constraints") or {}).get(
        "external_retrieval_called"
    )
    status = "not_called" if called is False else "pending_provider"
    return {
        "audit_source": "runtime_only",
        "discovery": {
            "requested": False,
            "executed": False,
            "status": status,
            "scope_completion_basis": "none",
            "human_attested": False,
            "candidate_count": 0,
            "failure_reason": "runtime external_retrieval_audit was not provided",
        },
        "verification": {
            "requested": False,
            "executed": False,
            "status": status,
            "candidate_count": 0,
            "failure_reason": "runtime external_retrieval_audit was not provided",
        },
        "local_search_completion": {},
    }


def _final_consistency_pass(
    finding: dict,
    actions: list[str],
    path: str,
    confirmation: dict,
    *,
    no_law_invariant: bool,
) -> None:
    """Remove stale state after the conclusion decision has been made."""

    state = canonicalize_conclusion_type(finding.get("conclusion_type"))
    if state is None:
        _set_field(
            finding,
            "conclusion_type",
            INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM,
            actions,
            path,
        )
        state = INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM
    if state == NO_APPLICABLE_LEGAL_BASIS_NEEDS_HUMAN_CONFIRM and not no_law_invariant:
        if "gate_original_conclusion_type" not in finding:
            finding["gate_original_conclusion_type"] = state
        _set_field(
            finding,
            "conclusion_type",
            INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM,
            actions,
            path,
        )
        _set_field(
            finding,
            "confirmation_not_upgraded_reason",
            "no-applicable-legal-basis 状态未通过运行时四层完成与外部 completed_no_hit 不变量校验。",
            actions,
            path,
        )
        state = INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM
    if state == REQUIRES_HUMAN_LEGAL_CONFIRM and not confirmation.get("trusted"):
        _set_field(
            finding,
            "conclusion_type",
            REQUIRES_HUMAN_LEGAL_REVIEW,
            actions,
            path,
        )
        state = REQUIRES_HUMAN_LEGAL_REVIEW
        _set_field(
            finding,
            "confirmation_not_upgraded_reason",
            confirmation.get("not_upgraded_reason") or "未通过运行时确认 gate。",
            actions,
            path,
        )
    if state in {
        INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM,
        NO_APPLICABLE_LEGAL_BASIS_NEEDS_HUMAN_CONFIRM,
    }:
        if finding.get("risk_severity") in {"high", "critical"}:
            _set_field(finding, "risk_severity", "medium", actions, path)
        _set_field(
            finding,
            "confidence_assessment",
            "insufficient_information",
            actions,
            path,
        )
        if finding.get("evidence_support_confidence") in {"high", "medium"}:
            _set_field(finding, "evidence_support_confidence", "low", actions, path)
        if finding.get("applicability_confidence") not in {
            "low",
            "insufficient_information",
        }:
            _set_field(
                finding,
                "applicability_confidence",
                "insufficient_information",
                actions,
                path,
            )
        if finding.get("risk_category") == "no_issue_identified":
            _set_field(
                finding,
                "risk_category",
                "missing_or_insufficient_evidence",
                actions,
                path,
            )
        if finding.get("compliance_relation") == "explicitly_satisfied":
            if "gate_original_compliance_relation" not in finding:
                finding["gate_original_compliance_relation"] = finding[
                    "compliance_relation"
                ]
            _set_field(finding, "compliance_relation", "unresolved", actions, path)
    if state in {
        REQUIRES_HUMAN_LEGAL_CONFIRM,
        REQUIRES_HUMAN_LEGAL_REVIEW,
    }:
        _set_field(finding, "human_review_status", "review_required", actions, path)


def apply_gate(raw_response: Any, runtime_input: dict) -> dict:
    """Return raw-preserving gate result with a safe final response."""

    actions: list[str] = []
    if not isinstance(raw_response, dict):
        reason = "LLM response was not a JSON object"
        return {
            "status": "blocked",
            "blocked": True,
            "actions": [reason],
            "raw_response": deepcopy(raw_response),
            "response": _minimal_response(runtime_input, reason),
        }

    response = deepcopy(raw_response)
    raw_response_preserved = deepcopy(raw_response)
    _set_field(response, "run_id", runtime_input.get("run_id", ""), actions, "root")
    _set_field(response, "project_id", runtime_input.get("project_id", ""), actions, "root")
    _set_field(response, "conclusion_contract_version", CONCLUSION_CONTRACT_VERSION, actions, "root")
    _set_field(response, "output_format", "review_table", actions, "root")
    _set_field(response, "overall_review_status", "requires_human_second_review", actions, "root")
    if not isinstance(response.get("findings"), list):
        reason = "LLM response findings is not a list; review_table/table_markdown are gate-generated and cannot replace findings"
        return {
            "status": "blocked",
            "blocked": True,
            "actions": actions + [reason],
            "raw_response": raw_response_preserved,
            "response": _minimal_response(runtime_input, reason),
        }

    if not response["findings"] and not _empty_findings_are_runtime_authorized(runtime_input):
        reason = (
            "LLM response findings is empty for a submitted issue; an explicit runtime no_reviewable_issue "
            "authorization is required"
        )
        return {
            "status": "blocked",
            "blocked": True,
            "actions": actions + [reason],
            "raw_response": raw_response_preserved,
            "response": _minimal_response(runtime_input, reason),
        }

    id_errors = _validate_finding_ids(response["findings"], runtime_input)
    if id_errors:
        reason = "invalid finding identity binding: " + "; ".join(id_errors)
        return {
            "status": "blocked",
            "blocked": True,
            "actions": actions + [reason],
            "raw_response": raw_response_preserved,
            "response": _minimal_response(runtime_input, reason),
        }

    runtime_scope = runtime_input.get("review_scope", {})
    runtime_scope = runtime_scope if isinstance(runtime_scope, dict) else {}
    no_law_eligible, no_law_reason = _no_applicable_legal_basis_audit(runtime_input)
    if not isinstance(response.get("review_scope"), dict):
        response["review_scope"] = deepcopy(runtime_scope)
        actions.append("corrected root.review_scope")
    if "jurisdiction_status" in runtime_scope and runtime_scope.get("jurisdiction_status") != "confirmed":
        _set_field(response["review_scope"], "jurisdiction_status", runtime_scope.get("jurisdiction_status", "uncertain"), actions, "review_scope")

    all_findings = response["findings"]
    confirmation_audits: list[dict] = []
    confirmed_count = 0
    confirmation_candidate_count = 0
    confirmation_validation_available_count = 0
    any_conclusion_changed = False

    for index, finding in enumerate(response["findings"]):
        path = f"findings[{index}]"
        # _validate_finding_ids has already rejected non-object findings.
        if not isinstance(finding, dict):
            continue

        raw_conclusion = finding.get("conclusion_type")
        original_conclusion_type = raw_conclusion
        canonical_input = canonicalize_conclusion_type(raw_conclusion)
        if canonical_input is not None:
            if raw_conclusion != canonical_input:
                _set_field(finding, "legacy_input_conclusion_type", raw_conclusion, actions, path)
                _set_field(finding, "conclusion_type", canonical_input, actions, path)
        elif raw_conclusion is not None:
            _set_field(finding, "legacy_input_conclusion_type", raw_conclusion, actions, path)

        _canonicalize_contract_evidence(finding, runtime_input, actions, path)

        _normalize_risk_severity(finding, actions, path)

        coverage = finding.get("legal_element_coverage")
        if not isinstance(coverage, dict):
            coverage = {}
            finding["legal_element_coverage"] = coverage
            actions.append(f"created {path}.legal_element_coverage")
        invalid_coverage_fields = [
            field
            for field in DECISIVE_FIELDS
            if field not in coverage or coverage.get(field) not in VALID_COVERAGE_STATES
        ]
        missing_fields = [
            field
            for field in DECISIVE_FIELDS
            if field not in coverage
            or coverage.get(field) in MISSING_STATES
            or coverage.get(field) not in VALID_COVERAGE_STATES
        ]

        evidence, invalid_evidence, only_supplementary = _canonicalize_evidence(finding, runtime_input, actions)
        for prose_field in ("reasoning_conclusion", "recommended_human_action"):
            unsupported = _unsupported_article_refs(finding.get(prose_field), evidence)
            if unsupported:
                replacement = (
                    "仅依据已列入 legal_evidence 的法规条文核对当前合同事实；"
                    "未检索、未回配的其他条款不得用于本次判断，并须提交人工二次复核。"
                )
                _set_field(finding, prose_field, replacement, actions, path)
                actions.append(f"removed unsupported article references from {path}.{prose_field}: {sorted(unsupported)}")
        usable_evidence = [item for item in evidence if _is_usable_legal_basis(item)]
        bounded_review = _runtime_bounded_review(runtime_input, usable_evidence)
        # Never accept a model-provided scope check with this field name.
        _set_field(finding, "runtime_bounded_review", bounded_review, actions, path)
        blocked_level4 = [
            item for item in evidence
            if _is_level4(item) and not _is_usable_legal_basis(item)
        ]
        explicit_no_issue_before_conflict = _finding_is_explicitly_compliant(finding)
        model_relation_conflict = (
            finding.get("compliance_relation") == "explicitly_satisfied"
            and _finding_claims_concrete_risk(finding)
        )
        if model_relation_conflict:
            if "gate_original_compliance_relation" not in finding:
                finding["gate_original_compliance_relation"] = finding["compliance_relation"]
            _set_field(finding, "compliance_relation", "unresolved", actions, path)
            actions.append(
                f"marked {path}.compliance_relation unresolved because an active risk claim conflicted with explicitly_satisfied"
            )

        runtime_violations = _runtime_violation_for_finding(
            runtime_input,
            finding,
            all_findings,
        )
        runtime_mandatory_missing = _runtime_mandatory_missing_relation(
            runtime_input,
            finding,
            usable_evidence,
        )
        _set_field(
            finding,
            "runtime_fact_law_relation_validation",
            runtime_mandatory_missing,
            actions,
            path,
        )
        requires_runtime_fact_relation = _finding_requires_runtime_fact_relation(
            finding,
            missing_fields,
        )
        runtime_fact_relation_supported = bool(
            runtime_mandatory_missing.get("eligible")
            or bounded_review.get("eligible")
        )
        if requires_runtime_fact_relation and not runtime_fact_relation_supported:
            actions.append(
                f"forced {path} to information insufficiency because no exact runtime fact-law relation supports the claimed missing material or factual gap"
            )
        possible_over_alert = bool(runtime_violations and explicit_no_issue_before_conflict)
        if possible_over_alert:
            if "gate_original_compliance_relation" not in finding and finding.get("compliance_relation"):
                finding["gate_original_compliance_relation"] = finding["compliance_relation"]
            _set_field(finding, "compliance_relation", "unresolved", actions, path)
            _set_field(finding, "possible_over_alert", True, actions, path)
            over_alert_reason = (
                "运行时严格级联审计在 "
                + ", ".join(
                    f"{row.get('level')}({','.join(row.get('overlap_chunk_ids', []))})"
                    for row in runtime_violations
                )
                + " 标记了与当前 finding 证据绑定的潜在不一致，但模型原始结论为满足要求；"
                "可能存在过度警报，必须人工复核。"
            )
            _set_field(finding, "possible_over_alert_reason", over_alert_reason, actions, path)
            _set_field(finding, "review_highlight", "red", actions, path)
            actions.append(f"flagged {path} possible_over_alert")

        explicit_no_issue = _finding_is_explicitly_compliant(finding)
        usable_non_level4 = [item for item in usable_evidence if not _is_level4(item)]
        no_issue_eligible = bool(usable_evidence) and not invalid_coverage_fields and explicit_no_issue and (
            not blocked_level4 or bool(usable_non_level4)
        ) and not runtime_violations and not model_relation_conflict and not bounded_review.get("eligible")
        confirmation = _runtime_claim_confirmation(runtime_input, finding, evidence)
        confirmation_audits.append(confirmation)
        confirmation_validation_available_count += int(confirmation.get("available", False))
        confirmation_candidate_count += int(confirmation.get("candidate", False))
        evidence_backed_risk = (
            bool(usable_evidence)
            and (_finding_claims_concrete_risk(finding) or bool(runtime_violations) or bounded_review.get("eligible"))
            and not bounded_review.get("missing_decisive_facts")
            and (
                not requires_runtime_fact_relation
                or runtime_fact_relation_supported
            )
            and not no_issue_eligible
        )
        no_law_invariant = bool(
            no_law_eligible
            and not usable_evidence
            and not missing_fields
            and not invalid_evidence
            and not runtime_violations
        )
        force_insufficient = (
            (not usable_evidence and not no_law_eligible)
            or (bool(missing_fields) and not evidence_backed_risk and not no_issue_eligible)
            or (invalid_evidence and not usable_evidence)
            or canonical_input is None
            or (requires_runtime_fact_relation and not runtime_fact_relation_supported)
            or bool(bounded_review.get("missing_decisive_facts"))
        )
        old_conclusion = finding.get("reasoning_conclusion", "")
        if no_law_eligible and not missing_fields and not invalid_evidence and not runtime_violations and not usable_evidence:
            if old_conclusion and "gate_original_conclusion" not in finding:
                finding["gate_original_conclusion"] = old_conclusion
            _set_field(
                finding,
                "conclusion_type",
                NO_APPLICABLE_LEGAL_BASIS_NEEDS_HUMAN_CONFIRM,
                actions,
                path,
            )
            _set_field(finding, "risk_category", "missing_or_insufficient_evidence", actions, path)
            _set_field(finding, "risk_severity", "low", actions, path)
            _set_field(finding, "confidence_assessment", "insufficient_information", actions, path)
            _set_field(finding, "evidence_support_confidence", "insufficient_information", actions, path)
            _set_field(finding, "applicability_confidence", "insufficient_information", actions, path)
            _set_field(finding, "human_review_status", "review_required", actions, path)
            boundary = (
                "supported_by_supplementary_source_only"
                if only_supplementary
                else "not_supported_by_current_corpus"
            )
            _set_field(finding, "evidence_boundary", boundary, actions, path)
            _set_field(
                finding,
                "reasoning_conclusion",
                "本地 Level 1–4 适用层级检索和已记录的外部法规发现均已完成，但没有找到可用的独立法规依据；当前不形成违规或合规判断。",
                actions,
                path,
            )
            _set_field(
                finding,
                "recommended_human_action",
                "请人工确认检索范围、法规覆盖范围及是否存在尚未纳入当前语料库的适用法源。",
                actions,
                path,
            )
        elif force_insufficient:
            if old_conclusion and "gate_original_conclusion" not in finding:
                finding["gate_original_conclusion"] = old_conclusion
            reason_parts = []
            if bounded_review.get("missing_decisive_facts"):
                reason_parts.append("尚缺：" + "、".join(bounded_review["missing_decisive_facts"]))
            elif requires_runtime_fact_relation and not runtime_fact_relation_supported:
                reason_parts.append("尚缺与当前事项对应的实际比较事实，或该阶段明确适用的材料提交要求及已审记录")
            if missing_fields:
                reason_parts.append("模型报告未闭合字段（不单独视为风险证据）：" + "、".join(missing_fields))
            if not evidence:
                reason_parts.append("没有可用且可定位的运行时法规证据")
            if invalid_evidence:
                reason_parts.append("部分法规引用未通过运行时证据回配")
            if canonical_input is None:
                reason_parts.append("conclusion_type 不是可识别的 v2 或 legacy 状态")
            reason = "；".join(reason_parts) or "当前材料或运行时审计未形成可用结论"
            _set_field(finding, "conclusion_type", INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM, actions, path)
            _set_field(finding, "confidence_assessment", "insufficient_information", actions, path)
            _set_field(
                finding,
                "evidence_support_confidence",
                "low" if evidence else "insufficient_information",
                actions,
                path,
            )
            _set_field(
                finding,
                "applicability_confidence",
                "insufficient_information" if blocked_level4 else "low",
                actions,
                path,
            )
            _set_field(finding, "human_review_status", "review_required", actions, path)
            if only_supplementary:
                boundary = "supported_by_supplementary_source_only"
            elif blocked_level4:
                boundary = "supported_by_verification_pending_source"
            elif not evidence:
                boundary = "not_supported_by_current_corpus"
            else:
                boundary = "partially_supported"
            if only_supplementary and _finding_is_out_of_scope_reference(finding):
                boundary = "not_supported_by_current_corpus"
            _set_field(finding, "evidence_boundary", boundary, actions, path)
            _set_field(finding, "reasoning_conclusion", f"依据当前材料无法建立所主张的具体差异或判断是否违反要求。{reason}。不形成违规指控。", actions, path)
            _set_field(finding, "compliance_relation", "unresolved", actions, path)
            _set_field(finding, "risk_category", "missing_or_insufficient_evidence", actions, path)
            _set_field(finding, "recommended_human_action", f"请补充并核验上述缺口：{reason}；取得完整原文及定位后进行人工二次审核。", actions, path)
        elif no_issue_eligible:
            if finding.get("conclusion_type") != NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE:
                _set_field(
                    finding,
                    "gate_original_conclusion",
                    finding.get("reasoning_conclusion", ""),
                    actions,
                    path,
                )
            _set_field(finding, "risk_category", "no_issue_identified", actions, path)
            _set_field(finding, "risk_severity", "informational", actions, path)
            _set_field(
                finding,
                "conclusion_type",
                NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE,
                actions,
                path,
            )
            _set_field(
                finding,
                "confidence_assessment",
                "low" if missing_fields else "medium",
                actions,
                path,
            )
            _set_field(finding, "evidence_support_confidence", "medium", actions, path)
            _set_field(
                finding,
                "applicability_confidence",
                "low" if missing_fields else "medium",
                actions,
                path,
            )
            _set_field(finding, "human_review_status", "review_required", actions, path)
            _set_field(
                finding,
                "evidence_boundary",
                "supported_by_multiple_local_levels"
                if len(usable_evidence) > 1
                else "supported_by_primary_local_source",
                actions,
                path,
            )
            _set_field(
                finding,
                "reasoning_conclusion",
                "在当前审查范围内，合同证据明确满足所引用法规要求，未发现有充分证据支持的风险；这不代表整个项目或合同全面合规。",
                actions,
                path,
            )
        elif evidence_backed_risk:
            if finding.get("severity_basis") == "no_supported_issue":
                _set_field(
                    finding,
                    "severity_basis",
                    "procedural_or_temporal_concern",
                    actions,
                    path,
                )
            if finding.get("risk_severity") == "informational":
                _set_field(finding, "risk_severity", "medium", actions, path)
            if runtime_violations and explicit_no_issue_before_conflict:
                _set_field(finding, "risk_category", "potential_non_compliance", actions, path)
                _set_field(
                    finding,
                    "reasoning_conclusion",
                    "运行时严格级联审计已在 "
                    + "、".join(row.get("level", "") for row in runtime_violations)
                    + " 针对当前 finding 的证据标记具体潜在不一致；模型原始无风险表述与检索审计冲突，"
                    "因此保守转入人工法律复核。",
                    actions,
                    path,
                )
            target_conclusion = (
                REQUIRES_HUMAN_LEGAL_CONFIRM
                if confirmation.get("trusted") and not possible_over_alert
                and not (bounded_review.get("eligible") and explicit_no_issue_before_conflict)
                else REQUIRES_HUMAN_LEGAL_REVIEW
            )
            if target_conclusion == REQUIRES_HUMAN_LEGAL_CONFIRM:
                confirmed_count += 1
            _set_field(finding, "conclusion_type", target_conclusion, actions, path)
            if bounded_review.get("eligible") and target_conclusion == REQUIRES_HUMAN_LEGAL_REVIEW:
                if old_conclusion and "gate_original_conclusion" not in finding:
                    finding["gate_original_conclusion"] = old_conclusion
                if finding.get("compliance_relation") == "explicitly_satisfied":
                    finding.setdefault("gate_original_compliance_relation", finding["compliance_relation"])
                    _set_field(finding, "compliance_relation", "unresolved", actions, path)
                if finding.get("risk_category") == "no_issue_identified":
                    _set_field(finding, "risk_category", "potential_non_compliance", actions, path)
                _set_field(finding, "risk_severity", "medium", actions, path)
                _set_field(finding, "reasoning_conclusion",
                           f"{bounded_review['claim']}：{bounded_review['document_location']}“{bounded_review['document_excerpt']}”。"
                           + _bounded_requirement_text(bounded_review)
                           + bounded_review['limitation'], actions, path)
                _set_field(finding, "recommended_human_action", bounded_review["human_action"], actions, path)
            _set_field(
                finding,
                "confidence_assessment",
                "low" if missing_fields or invalid_evidence else "medium",
                actions,
                path,
            )
            _set_field(finding, "evidence_support_confidence", "medium", actions, path)
            _set_field(
                finding,
                "applicability_confidence",
                "low" if missing_fields else "medium",
                actions,
                path,
            )
            _set_field(finding, "human_review_status", "review_required", actions, path)
            _set_field(
                finding,
                "evidence_boundary",
                (
                    "partially_supported"
                    if any(_is_external_source(item) for item in usable_evidence)
                    else (
                        "supported_by_multiple_local_levels"
                        if len(usable_evidence) > 1
                        else "supported_by_primary_local_source"
                    )
                ),
                actions,
                path,
            )
        elif only_supplementary:
            _set_field(finding, "conclusion_type", REQUIRES_HUMAN_LEGAL_REVIEW, actions, path)
            _set_field(finding, "confidence_assessment", "low", actions, path)
            _set_field(finding, "evidence_support_confidence", "low", actions, path)
            _set_field(finding, "applicability_confidence", "low", actions, path)
            _set_field(finding, "human_review_status", "review_required", actions, path)
            _set_field(finding, "evidence_boundary", "supported_by_supplementary_source_only", actions, path)

        _set_field(
            finding,
            "confirmation_validation_available",
            bool(confirmation.get("available")),
            actions,
            path,
        )
        _set_field(
            finding,
            "confirmation_candidate",
            bool(confirmation.get("candidate")),
            actions,
            path,
        )
        _set_field(
            finding,
            "confirmation_validation",
            {
                "available": bool(confirmation.get("available")),
                "trusted": bool(confirmation.get("trusted")),
                "validated_evidence_chunk_ids": confirmation.get("validated_evidence_chunk_ids", []),
                "predicates": confirmation.get("predicates", {}),
                "validation_source": confirmation.get("validation_source", ""),
                "validation_basis": confirmation.get("validation_basis", ""),
            },
            actions,
            path,
        )
        _set_field(
            finding,
            "confirmation_not_upgraded_reason",
            confirmation.get("not_upgraded_reason", "")
            if not confirmation.get("trusted")
            else "",
            actions,
            path,
        )

        _final_consistency_pass(
            finding,
            actions,
            path,
            confirmation,
            no_law_invariant=no_law_invariant,
        )
        _normalize_risk_severity(finding, actions, path)

        conclusion_changed = finding.get("conclusion_type") != original_conclusion_type
        any_conclusion_changed = any_conclusion_changed or conclusion_changed
        if conclusion_changed and isinstance(finding.get("assistant_recommendation"), dict):
            if "gate_original_assistant_recommendation" not in finding:
                finding["gate_original_assistant_recommendation"] = deepcopy(
                    finding["assistant_recommendation"]
                )
        recommendation = _default_substantive_recommendation(
            finding,
            force_rebuild=conclusion_changed,
        )
        if possible_over_alert:
            reason = finding.get("possible_over_alert_reason", "可能存在过度警报，必须人工复核。")
            if isinstance(recommendation, dict):
                handling = recommendation.get("recommended_handling", "")
                recommendation = dict(recommendation)
                recommendation["possible_over_alert"] = True
                recommendation["review_highlight"] = "red"
                recommendation["recommended_handling"] = f"⚠️ possible_over_alert：{reason} {handling}".strip()
        _set_field(finding, "assistant_recommendation", recommendation, actions, path)
        processing_label = _default_processing_label(finding)
        _set_field(finding, "review_processing_label", processing_label, actions, path)

    if any_conclusion_changed:
        if isinstance(response.get("project_summary"), dict) and "gate_original_project_summary" not in response:
            response["gate_original_project_summary"] = deepcopy(response["project_summary"])
            actions.append("preserved root.project_summary before deterministic rebuild")
        if isinstance(response.get("retrieval_audit"), dict) and "gate_original_retrieval_audit" not in response:
            response["gate_original_retrieval_audit"] = deepcopy(response["retrieval_audit"])
            actions.append("preserved root.retrieval_audit before deterministic canonicalization")
        if isinstance(response.get("stage3_decision_audit"), dict) and "gate_original_stage3_decision_audit" not in response:
            response["gate_original_stage3_decision_audit"] = deepcopy(response["stage3_decision_audit"])
            actions.append("preserved root.stage3_decision_audit before deterministic rebuild")
        response["project_summary"] = _rebuild_project_summary(response)
        actions.append("rebuilt root.project_summary from canonical findings")

    summary = response.get("project_summary")
    if not isinstance(summary, dict):
        summary = {}
        response["project_summary"] = summary
        actions.append("created root.project_summary")
    _set_field(summary, "findings_count", len(response["findings"]), actions, "project_summary")
    _set_field(summary, "statement_boundary", "本结果仅辅助人工审查，不是最终法律结论", actions, "project_summary")

    audit = response.get("retrieval_audit")
    if not isinstance(audit, dict):
        audit = {}
        response["retrieval_audit"] = audit
        actions.append("created root.retrieval_audit")
    runtime_external_audit = _runtime_external_audit(runtime_input)
    _set_field(
        audit,
        "external_retrieval_audit",
        runtime_external_audit,
        actions,
        "retrieval_audit",
    )
    runtime_external_sources = runtime_input.get("external_sources_used")
    if not isinstance(runtime_external_sources, list):
        runtime_external_sources = runtime_external_audit.get("external_sources_used", [])
    if not isinstance(runtime_external_sources, list):
        runtime_external_sources = []
    _set_field(audit, "external_sources_used", deepcopy(runtime_external_sources), actions, "retrieval_audit")
    runtime_constraints = runtime_input.get("runtime_constraints") or {}
    if runtime_constraints.get("external_retrieval_called") is False:
        _set_field(audit, "external_retrieval_called", False, actions, "retrieval_audit")
    elif "external_retrieval_called" in runtime_constraints:
        external_called = bool(runtime_constraints.get("external_retrieval_called"))
        for key in ("discovery", "verification"):
            record = runtime_external_audit.get(key)
            if isinstance(record, dict) and record.get("executed") is True:
                external_called = True
        _set_field(audit, "external_retrieval_called", external_called, actions, "retrieval_audit")

    decision_audit = {
        "conclusion_contract_version": CONCLUSION_CONTRACT_VERSION,
        "canonical_conclusion_states": list(CANONICAL_CONCLUSION_STATES),
        "confirmation_validation_available": confirmation_validation_available_count > 0,
        "confirmation_validation_available_count": confirmation_validation_available_count,
        "confirmation_candidate_count": confirmation_candidate_count,
        "confirmed_count": confirmed_count,
        "no_applicable_legal_basis_eligible": no_law_eligible,
        "no_applicable_legal_basis_reason": no_law_reason,
        "legacy_three_class_table_mapping": deepcopy(LEGACY_THREE_CLASS_MAPPING),
        "legacy_three_class_conclusion_mapping": deepcopy(LEGACY_THREE_CLASS_CONCLUSION_MAPPING),
    }
    _set_field(response, "stage3_decision_audit", decision_audit, actions, "root")

    review_table = _build_review_table(response)
    _set_field(response, "review_table", review_table, actions, "root")
    _set_field(response, "table_markdown", _build_table_markdown(review_table), actions, "root")

    return {
        "status": "corrected" if actions else "passed",
        "blocked": False,
        "actions": actions,
        "raw_response": raw_response_preserved,
        "response": response,
    }
