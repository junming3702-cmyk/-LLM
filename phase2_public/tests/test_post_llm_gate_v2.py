"""Offline regression tests for the Stage 3 v2 post-LLM gate.

The fixtures are deliberately local and synthetic.  They exercise the gate's
schema/provenance/issue-binding contract without calling DeepSeek, MinerU, or
any external retrieval service.  No gold labels are changed by this module.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from conclusion_contract_v2 import (  # noqa: E402
    INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM,
    NO_APPLICABLE_LEGAL_BASIS_NEEDS_HUMAN_CONFIRM,
    NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE,
    REQUIRES_HUMAN_LEGAL_CONFIRM,
    REQUIRES_HUMAN_LEGAL_REVIEW,
    legacy_three_class_conclusion,
    legacy_three_class_label,
    legacy_test_result,
)
from llm_abstention_gate import apply_gate  # noqa: E402


def _sha256_text(value: Any) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _sha256_json(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return _sha256_text(payload)


def _runtime(
    *,
    chunk: dict[str, Any] | None = None,
    issue_id: str = "ISSUE-001",
    project_id: str = "PROJECT-001",
    document_excerpt: str = "合同原文：未提交规定的证明文件。",
    document_location: str = "第3.2条",
) -> dict[str, Any]:
    chunk = chunk or {
        "chunk_id": "law-1",
        "law": "示例全国性法律",
        "article": "第十二条",
        "source_locator": "第十二条",
        "legal_quote": "应当提交真实、有效的证明文件。",
        "source_version": "2024-01-01",
        "normative_level": "Level 1",
        "normative_type": "law",
        "source_role": "primary_source",
        "legal_evidence_eligibility": "independent_candidate",
        "independent_legal_evidence": True,
        "applicability_status": "matched",
        "retrieval_admission": "high_trust",
    }
    return {
        "run_id": f"stage3-test-{issue_id}",
        "issue_id": issue_id,
        "project_id": project_id,
        "review_scope": {
            "jurisdiction_status": "uncertain",
            "retrieval_mode": "strict_level_cascade_hybrid_bm25_dense",
        },
        "project_context": {
            "project_id": project_id,
            "context_version": "context-v1",
            "project_location": {
                "raw_text": "",
                "confidence": "insufficient_information",
            },
            "project_type": "construction_project",
            "procurement_type": "",
        },
        "contract_evidence": {
            "document_id": "DOC-001",
            "document_location": document_location,
            "document_excerpt": document_excerpt,
        },
        "hierarchy_retrieval_audit": {
            "hierarchy_search_order": ["Level 1", "Level 2", "Level 3", "Level 4"],
            "levels": [],
        },
        "retrieved_legal_evidence": [chunk],
        "retrieval_queries": ["证明文件"] ,
        "runtime_constraints": {
            "external_retrieval_called": False,
        },
    }


def _finding(
    *,
    conclusion: str = "potential_risk",
    category: str = "potential_non_compliance",
    finding_id: str = "F001",
    issue_id: str = "ISSUE-001",
    evidence_ids: list[str] | None = None,
    coverage: dict[str, str] | None = None,
    relation: str = "potential_non_compliance",
) -> dict[str, Any]:
    return {
        "finding_id": finding_id,
        "issue_id": issue_id,
        "risk_category": category,
        "risk_severity": "high",
        "legal_element_coverage": coverage or {
            "subject": "supported",
            "conduct_or_condition": "supported",
            "jurisdiction_and_scope": "supported",
            "legal_consequence": "supported",
        },
        "compliance_relation": relation,
        "obligation_phase": "bid_submission",
        "requirement_lifecycle": "ongoing",
        "severity_basis": "direct_mandatory_conflict",
        "scope_assessment": "within_review_scope",
        "legal_evidence": [
            {
                "chunk_id": chunk_id,
                "source_locator": "MODEL-SUPPLIED-LOCATOR",
                "official_source_url": "https://model.invalid/not-runtime",
                "independent_legal_evidence": False,
            }
            for chunk_id in (evidence_ids if evidence_ids is not None else ["law-1"])
        ],
        "contract_evidence": [
            {
                "document_id": "MODEL-DOCUMENT",
                "document_location": "MODEL-LOCATION",
                "document_excerpt": "MODEL-EXCERPT",
                "nested": {"document_excerpt": "MODEL-NESTED-EXCERPT"},
            }
        ],
        "document_id": "MODEL-DOCUMENT",
        "document_location": "MODEL-LOCATION",
        "document_excerpt": "MODEL-EXCERPT",
        "reasoning_conclusion": "合同事实与法规要求可能存在不一致，需人工复核。",
        "conclusion_type": conclusion,
        "evidence_boundary": "supported_by_primary_local_source",
        "confidence_assessment": "high",
        "recommended_human_action": "请人工核对事实和法规适用条件。",
        "human_review_status": "review_required",
    }


def _with_trusted_confirmation(runtime: dict[str, Any], finding: dict[str, Any]) -> dict[str, Any]:
    contract = runtime["contract_evidence"]
    context = runtime["project_context"]
    policy = {
        "policy_id": "validator-policy-v2",
        "version": "2",
        "rules": ["explicit_fact_law_relation", "runtime_hash_binding"],
    }
    runtime["validator_policy"] = policy
    record = {
        "issue_id": runtime["issue_id"],
        "project_id": runtime["project_id"],
        "finding_id": finding["finding_id"],
        "status": "validated",
        "validated": True,
        "record_origin": "runtime_validator",
        "validation_source": "runtime_claim_validator_v2",
        "validation_basis": "independent runtime fact-law comparator",
        "predicates": {
            "fact_present": True,
            "law_requirement_present": True,
            "scope_applicable": True,
            "relation_explicit": True,
            "evidence_independent": True,
            "no_unresolved_conflict": True,
        },
        "validated_evidence_chunk_ids": ["law-1"],
        "contract_binding": {
            "document_id": contract["document_id"],
            "contract_excerpt_sha256": _sha256_text(contract["document_excerpt"]),
            "document_location_sha256": _sha256_text(contract["document_location"]),
        },
        "context_binding": {
            "context_version": context["context_version"],
            "project_context_sha256": _sha256_json(context),
        },
        "validator_policy_binding": {
            "validator_policy_id": policy["policy_id"],
            "validator_policy_sha256": _sha256_json(policy),
        },
        "legal_evidence_bindings": [
            {
                "chunk_id": "law-1",
                "legal_quote_sha256": _sha256_text(runtime["retrieved_legal_evidence"][0]["legal_quote"]),
                "article_sha256": _sha256_text(runtime["retrieved_legal_evidence"][0]["article"]),
                "source_version_sha256": _sha256_text(runtime["retrieved_legal_evidence"][0]["source_version"]),
            }
        ],
    }
    runtime["claim_confirmation_validation"] = {"records": [record]}
    return runtime


def _complete_no_law_runtime(*, manifest_only: bool = False) -> dict[str, Any]:
    runtime = _runtime()
    runtime["retrieved_legal_evidence"] = []
    runtime["external_retrieval_audit"] = {
        "local_search_completion": {
            "status": "completed_no_hit",
            "no_usable_applicable_basis": True,
            "executed_levels": ["Level 1", "Level 2", "Level 3", "Level 4"],
            "completion_basis": "runtime_execution",
        },
        "discovery": {
            "requested": True,
            "executed": True,
            "status": "completed_no_hit",
            "scope_completion_basis": "manifest_only" if manifest_only else "provider_execution",
            "human_attested": False,
            "external_search_completed": not manifest_only,
            "candidate_count": 0,
            "no_applicable_independent_source": not manifest_only,
        },
    }
    return runtime


def _run(name: str, fn) -> None:
    fn()
    print(f"PASS {name}")


def test_conclusion_aliases_and_mapping() -> None:
    runtime = _runtime()
    result = apply_gate({"findings": [_finding(conclusion="potential_risk")]}, runtime)
    finding = result["response"]["findings"][0]
    assert finding["conclusion_type"] == REQUIRES_HUMAN_LEGAL_REVIEW
    assert finding["legacy_input_conclusion_type"] == "potential_risk"
    assert legacy_three_class_label(REQUIRES_HUMAN_LEGAL_CONFIRM) == "risk_supported"
    assert legacy_three_class_conclusion(REQUIRES_HUMAN_LEGAL_CONFIRM) == REQUIRES_HUMAN_LEGAL_REVIEW
    assert legacy_test_result(NO_APPLICABLE_LEGAL_BASIS_NEEDS_HUMAN_CONFIRM) == "insufficient_information"


def test_confirm_requires_runtime_record_and_trusted_record_can_confirm() -> None:
    runtime = _runtime()
    raw_finding = _finding(conclusion=REQUIRES_HUMAN_LEGAL_CONFIRM)
    result = apply_gate({"findings": [raw_finding]}, runtime)
    finding = result["response"]["findings"][0]
    assert finding["conclusion_type"] == REQUIRES_HUMAN_LEGAL_REVIEW
    assert finding["confirmation_candidate"] is True
    assert finding["confirmation_validation_available"] is False
    assert result["response"]["stage3_decision_audit"]["confirmed_count"] == 0

    trusted_runtime = _with_trusted_confirmation(_runtime(), raw_finding)
    trusted_result = apply_gate({"findings": [raw_finding]}, trusted_runtime)
    trusted_finding = trusted_result["response"]["findings"][0]
    assert trusted_finding["conclusion_type"] == REQUIRES_HUMAN_LEGAL_CONFIRM
    assert trusted_finding["confirmation_validation"]["trusted"] is True
    assert trusted_result["response"]["stage3_decision_audit"]["confirmed_count"] == 1


def test_stale_hash_and_model_validation_cannot_confirm() -> None:
    runtime = _with_trusted_confirmation(_runtime(), _finding())
    runtime["claim_confirmation_validation"]["records"][0]["contract_binding"]["contract_excerpt_sha256"] = "stale"
    result = apply_gate({"findings": [_finding(conclusion=REQUIRES_HUMAN_LEGAL_CONFIRM)]}, runtime)
    finding = result["response"]["findings"][0]
    assert finding["conclusion_type"] == REQUIRES_HUMAN_LEGAL_REVIEW
    assert finding["confirmation_validation"]["trusted"] is False
    assert "合同实际内容或定位" in finding["confirmation_not_upgraded_reason"]

    model_finding = _finding(conclusion=REQUIRES_HUMAN_LEGAL_CONFIRM)
    model_finding["claim_confirmation_validation"] = {
        "validated": True,
        "status": "validated",
        "validation_source": "LLM",
        "predicates": {key: True for key in (
            "fact_present", "law_requirement_present", "scope_applicable",
            "relation_explicit", "evidence_independent", "no_unresolved_conflict",
        )},
    }
    model_result = apply_gate({"findings": [model_finding]}, _runtime())
    model_out = model_result["response"]["findings"][0]
    assert model_out["conclusion_type"] == REQUIRES_HUMAN_LEGAL_REVIEW
    assert model_out["confirmation_validation_available"] is False

    missing_binding_runtime = _with_trusted_confirmation(_runtime(), _finding())
    missing_record = missing_binding_runtime["claim_confirmation_validation"]["records"][0]
    missing_record["context_binding"].pop("context_version")
    missing_binding_result = apply_gate({"findings": [_finding(conclusion=REQUIRES_HUMAN_LEGAL_CONFIRM)]}, missing_binding_runtime)
    assert missing_binding_result["response"]["findings"][0]["conclusion_type"] == REQUIRES_HUMAN_LEGAL_REVIEW

    invalid_fact_runtime = _with_trusted_confirmation(_runtime(), _finding())
    invalid_fact_runtime["claim_confirmation_validation"]["records"][0]["decisive_facts"] = [{"status": "invalid"}]
    invalid_fact_result = apply_gate({"findings": [_finding(conclusion=REQUIRES_HUMAN_LEGAL_CONFIRM)]}, invalid_fact_runtime)
    invalid_fact_finding = invalid_fact_result["response"]["findings"][0]
    assert invalid_fact_finding["conclusion_type"] == REQUIRES_HUMAN_LEGAL_REVIEW
    assert "status=invalid" in invalid_fact_finding["confirmation_not_upgraded_reason"]


def test_runtime_provenance_and_document_fields_override_model() -> None:
    runtime = _runtime()
    raw = _finding()
    result = apply_gate({"findings": [raw]}, runtime)
    finding = result["response"]["findings"][0]
    evidence = finding["legal_evidence"][0]
    assert evidence["source_locator"] == "第十二条"
    assert "official_source_url" not in evidence
    assert finding["document_id"] == "DOC-001"
    assert finding["document_location"] == "第3.2条"
    assert finding["document_excerpt"] == "合同原文：未提交规定的证明文件。"
    nested = finding["contract_evidence"][0]
    assert nested["document_id"] == "DOC-001"
    assert nested["document_location"] == "第3.2条"
    assert nested["document_excerpt"] == "合同原文：未提交规定的证明文件。"


def test_external_pending_is_not_independent() -> None:
    external = deepcopy(_runtime()["retrieved_legal_evidence"][0])
    external.update({
        "external_source": True,
        "provenance_origin": "external",
        "acquisition_channel": "external_retrieval",
        "source_url": "https://example.gov/law/12",
        "issuer": "示例法制机构",
        "source_title": "示例全国性法律",
        "effective_date": "2024-01-01",
        "retrieved_at": "2026-09-05T00:00:00Z",
        "source_hash": "runtime-content-hash",
        "verification_status": "pending_human_verification",
        "human_confirmation_status": "pending",
        "legal_evidence_eligibility": "verification_only",
    })
    runtime = _runtime(chunk=external)
    result = apply_gate({"findings": [_finding()]}, runtime)
    finding = result["response"]["findings"][0]
    evidence = finding["legal_evidence"][0]
    assert evidence["independent_legal_evidence"] is False
    assert evidence["legal_evidence_eligibility"] == "verification_only"
    assert finding["conclusion_type"] == INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM

    incomplete = deepcopy(external)
    incomplete["source_locator"] = ""
    incomplete.pop("source_hash", None)
    incomplete_runtime = _runtime(chunk=incomplete)
    incomplete_result = apply_gate({"findings": [_finding()]}, incomplete_runtime)
    incomplete_finding = incomplete_result["response"]["findings"][0]
    assert incomplete_finding["legal_evidence"] == []
    assert incomplete_finding["conclusion_type"] == INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM

    cecn = deepcopy(external)
    cecn["provider_id"] = "CECN"
    cecn["external_candidate_status"] = "candidate"
    cecn_runtime = _runtime(chunk=cecn)
    cecn_result = apply_gate({"findings": [_finding()]}, cecn_runtime)
    cecn_evidence = cecn_result["response"]["findings"][0]["legal_evidence"][0]
    assert cecn_evidence["legal_evidence_eligibility"] == "supplement_only"
    assert cecn_evidence["citation_mode"] == "contextual_only"


def test_no_law_requires_completed_external_audit() -> None:
    no_law_runtime = _complete_no_law_runtime()
    raw = _finding(evidence_ids=[], conclusion="potential_risk")
    result = apply_gate({"findings": [raw]}, no_law_runtime)
    finding = result["response"]["findings"][0]
    assert finding["conclusion_type"] == NO_APPLICABLE_LEGAL_BASIS_NEEDS_HUMAN_CONFIRM
    assert finding["confidence_assessment"] == "insufficient_information"

    manifest_runtime = _complete_no_law_runtime(manifest_only=True)
    manifest_result = apply_gate({"findings": [_finding(evidence_ids=[])]}, manifest_runtime)
    manifest_finding = manifest_result["response"]["findings"][0]
    assert manifest_finding["conclusion_type"] == INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM

    root_runtime = _complete_no_law_runtime()
    local_completion = root_runtime["external_retrieval_audit"].pop("local_search_completion")
    root_runtime["local_search_completion"] = local_completion
    root_result = apply_gate({"findings": [_finding(evidence_ids=[])]}, root_runtime)
    assert root_result["response"]["findings"][0]["conclusion_type"] == NO_APPLICABLE_LEGAL_BASIS_NEEDS_HUMAN_CONFIRM

    mismatch_runtime = _complete_no_law_runtime()
    mismatch_runtime["local_search_completion"] = {"status": "pending"}
    mismatch_result = apply_gate({"findings": [_finding(evidence_ids=[])]}, mismatch_runtime)
    assert mismatch_result["response"]["findings"][0]["conclusion_type"] == INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM


def test_model_no_law_cannot_survive_when_usable_evidence_supports_no_issue() -> None:
    runtime = _runtime()
    runtime["external_retrieval_audit"] = _complete_no_law_runtime()["external_retrieval_audit"]
    # This deliberately contradictory fixture is a regression for model
    # supplied no-law output: a usable local chunk plus an explicitly satisfied
    # relation must not fall through and retain the no-law state.
    raw = _finding(
        conclusion=NO_APPLICABLE_LEGAL_BASIS_NEEDS_HUMAN_CONFIRM,
        category="no_issue_identified",
        relation="explicitly_satisfied",
    )
    result = apply_gate({"findings": [raw]}, runtime)
    finding = result["response"]["findings"][0]
    assert finding["conclusion_type"] == NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE
    assert finding["conclusion_type"] != NO_APPLICABLE_LEGAL_BASIS_NEEDS_HUMAN_CONFIRM


def test_national_risk_with_missing_scope_remains_review() -> None:
    runtime = _runtime()
    coverage = {
        "subject": "supported",
        "conduct_or_condition": "supported",
        "jurisdiction_and_scope": "missing",
        "legal_consequence": "supported",
    }
    result = apply_gate({"findings": [_finding(coverage=coverage)]}, runtime)
    finding = result["response"]["findings"][0]
    assert finding["conclusion_type"] == REQUIRES_HUMAN_LEGAL_REVIEW
    assert finding["risk_category"] == "potential_non_compliance"


def test_missing_material_requires_runtime_relation_and_blocks_level4_support() -> None:
    coverage = {
        "subject": "missing",
        "conduct_or_condition": "missing",
        "jurisdiction_and_scope": "missing",
        "legal_consequence": "missing",
    }
    raw = _finding(
        conclusion="insufficient_information",
        category="missing_or_insufficient_evidence",
        coverage=coverage,
        relation="requirement_not_shown",
    )
    raw["risk_severity"] = "informational"
    raw["severity_basis"] = "missing_document_only"
    raw["reasoning_conclusion"] = "当前证据不足，无法判断所需材料是否实际缺失。"

    without_runtime_relation = apply_gate({"findings": [raw]}, _runtime())
    without_finding = without_runtime_relation["response"]["findings"][0]
    assert without_finding["conclusion_type"] == INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM
    assert without_finding["runtime_fact_law_relation_validation"]["eligible"] is False

    runtime = _runtime()
    runtime["fact_law_relation_audit"] = {
        "records": [{
            "issue_id": runtime["issue_id"],
            "finding_id": raw["finding_id"],
            "evidence_chunk_ids": ["law-1"],
            "record_origin": "runtime_rule_checker",
            "validation_source": "deterministic_runtime_fact_law_comparator",
            "status": "validated",
            "validated": True,
            "relation_type": "mandatory_material_missing",
            "mandatory_requirement": True,
            "requirement_source": "law",
            "required_at_stage": "bid_submission",
            "actual_document_status": "not_provided",
        }]
    }
    runtime_result = apply_gate({"findings": [raw]}, runtime)
    runtime_finding = runtime_result["response"]["findings"][0]
    assert runtime_finding["conclusion_type"] == REQUIRES_HUMAN_LEGAL_REVIEW
    assert runtime_finding["runtime_fact_law_relation_validation"]["eligible"] is True
    assert runtime_finding["runtime_fact_law_relation_validation"]["matched_evidence_chunk_ids"] == ["law-1"]
    assert runtime_finding["assistant_recommendation"]["supporting_legal_evidence"][0]["chunk_id"] == "law-1"

    blocked_level4 = deepcopy(_runtime()["retrieved_legal_evidence"][0])
    blocked_level4.update({
        "normative_level": "Level 4",
        "scope_classification": "local_regional",
        "applicability_status": "blocked_missing_jurisdiction_context",
        "geographic_scope": "unverified_local_scope",
    })
    blocked_runtime = _runtime(chunk=blocked_level4)
    blocked_result = apply_gate({"findings": [raw]}, blocked_runtime)
    blocked_finding = blocked_result["response"]["findings"][0]
    assert blocked_finding["conclusion_type"] == INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM
    assert blocked_finding["assistant_recommendation"]["supporting_legal_evidence"] == []
    assert all(
        item.get("chunk_id") != "law-1"
        for item in blocked_finding["assistant_recommendation"]["supporting_legal_evidence"]
    )

    unknown_scope = _runtime()
    unknown_scope_result = apply_gate(
        {"findings": [_finding(coverage=coverage, relation="potential_non_compliance")]},
        unknown_scope,
    )
    assert (
        unknown_scope_result["response"]["findings"][0]["conclusion_type"]
        == INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM
    )


def test_null_negative_admission_and_duplicate_runtime_chunks_fail_closed() -> None:
    runtime = _runtime()
    source = runtime["retrieved_legal_evidence"][0]
    source["source_locator"] = None
    source["independent_evidence"] = None
    source["retrieval_admission"] = None
    result = apply_gate({"findings": [_finding()]}, runtime)
    finding = result["response"]["findings"][0]
    assert finding["conclusion_type"] == INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM
    assert finding["legal_evidence"] == []
    assert finding["document_excerpt"] == "合同原文：未提交规定的证明文件。"
    assert "MODEL-SUPPLIED-LOCATOR" not in json.dumps(finding, ensure_ascii=False)

    blocked_runtime = _runtime()
    blocked_runtime["retrieved_legal_evidence"][0]["retrieval_admission"] = "excluded_pending_review"
    blocked_result = apply_gate({"findings": [_finding()]}, blocked_runtime)
    assert blocked_result["response"]["findings"][0]["conclusion_type"] == INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM

    duplicate_runtime = _runtime()
    duplicate_runtime["retrieved_legal_evidence"].append(
        deepcopy(duplicate_runtime["retrieved_legal_evidence"][0])
    )
    duplicate_result = apply_gate({"findings": [_finding()]}, duplicate_runtime)
    duplicate_finding = duplicate_result["response"]["findings"][0]
    assert duplicate_finding["legal_evidence"] == []
    assert duplicate_finding["conclusion_type"] == INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM


def test_invalid_coverage_and_non_level4_mismatch_are_not_supported() -> None:
    runtime = _runtime()
    invalid_coverage = {
        "subject": None,
        "conduct_or_condition": "supported",
        "jurisdiction_and_scope": "supported",
        "legal_consequence": "supported",
    }
    raw = _finding(
        conclusion=NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE,
        category="no_issue_identified",
        relation="explicitly_satisfied",
        coverage=invalid_coverage,
    )
    result = apply_gate({"findings": [raw]}, runtime)
    assert result["response"]["findings"][0]["conclusion_type"] == INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM

    unrecognized = deepcopy(invalid_coverage)
    unrecognized["subject"] = "not-a-coverage-state"
    result = apply_gate({"findings": [_finding(conclusion=NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE, category="no_issue_identified", relation="explicitly_satisfied", coverage=unrecognized)]}, runtime)
    assert result["response"]["findings"][0]["conclusion_type"] == INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM

    mismatch_runtime = _runtime()
    mismatch_runtime["retrieved_legal_evidence"][0]["applicability_status"] = "mismatch"
    mismatch_result = apply_gate({"findings": [_finding()]}, mismatch_runtime)
    mismatch_finding = mismatch_result["response"]["findings"][0]
    assert mismatch_finding["conclusion_type"] == INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM


def test_issue_specific_over_alert_does_not_spread_to_unrelated_finding() -> None:
    runtime = _runtime()
    runtime["hierarchy_retrieval_audit"]["levels"] = [{
        "level": "Level 1",
        "level_state": "violation_or_inconsistency_detected",
        "violation_chunk_ids": ["law-1"],
        "finding_id": "F001",
        "issue_id": "ISSUE-001",
    }]
    first = _finding(
        conclusion=NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE,
        category="no_issue_identified",
        finding_id="F001",
        relation="explicitly_satisfied",
    )
    first["severity_basis"] = "no_supported_issue"
    first["risk_severity"] = "informational"
    second = _finding(
        conclusion=NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE,
        category="no_issue_identified",
        finding_id="F002",
        relation="explicitly_satisfied",
    )
    result = apply_gate({"findings": [first, second]}, runtime)
    findings = result["response"]["findings"]
    assert findings[0]["possible_over_alert"] is True
    assert findings[0]["review_highlight"] == "red"
    assert findings[0]["compliance_relation"] == "unresolved"
    assert findings[0]["gate_original_compliance_relation"] == "explicitly_satisfied"
    assert findings[0]["severity_basis"] == "procedural_or_temporal_concern"
    assert findings[0]["risk_severity"] == "medium"
    assert findings[1]["conclusion_type"] == NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE
    assert findings[1].get("possible_over_alert") is not True


def test_shared_article_without_finding_binding_does_not_spread() -> None:
    runtime = _runtime()
    runtime["hierarchy_retrieval_audit"]["levels"] = [{
        "level": "Level 1",
        "level_state": "violation_or_inconsistency_detected",
        "violation_chunk_ids": ["law-1"],
        "issue_id": "ISSUE-001",
    }]
    rows = [
        _finding(conclusion=NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE, category="no_issue_identified", finding_id="F001", relation="explicitly_satisfied"),
        _finding(conclusion=NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE, category="no_issue_identified", finding_id="F002", relation="explicitly_satisfied"),
    ]
    result = apply_gate({"findings": rows}, runtime)
    assert all(row.get("possible_over_alert") is not True for row in result["response"]["findings"])


def test_empty_duplicate_and_unexpected_ids_block() -> None:
    runtime = _runtime()
    empty = apply_gate({"findings": []}, runtime)
    assert empty["blocked"] is True
    duplicate = apply_gate({"findings": [_finding(), _finding(finding_id="F001")]}, runtime)
    assert duplicate["blocked"] is True
    unexpected = apply_gate({"findings": [_finding(issue_id="OTHER-ISSUE")]}, runtime)
    assert unexpected["blocked"] is True


def test_final_consistency_removes_stale_positive_state_after_insufficiency() -> None:
    runtime = _runtime()
    raw = _finding(
        conclusion="insufficient_information",
        category="no_issue_identified",
        evidence_ids=[],
        relation="explicitly_satisfied",
    )
    raw["risk_severity"] = "high"
    raw["assistant_recommendation"] = {
        "substantive_conclusion": "已明确满足要求，无需处理。",
        "recommended_handling": "接受。",
    }
    result = apply_gate({"findings": [raw]}, runtime)
    finding = result["response"]["findings"][0]
    assert finding["conclusion_type"] == INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM
    assert finding["risk_severity"] == "medium"
    assert finding["confidence_assessment"] == "insufficient_information"
    assert finding["compliance_relation"] == "unresolved"
    assert "无需处理" not in finding["assistant_recommendation"]["substantive_conclusion"]
    assert "gate_original_assistant_recommendation" in finding


def test_changed_conclusion_rebuilds_summary_and_preserves_original_audit() -> None:
    runtime = _runtime()
    raw = _finding(conclusion="potential_risk")
    raw["assistant_recommendation"] = {
        "substantive_conclusion": "旧的模型风险建议。",
        "recommended_handling": "旧建议。",
    }
    raw_response = {
        "findings": [raw],
        "project_summary": {
            "findings_count": 999,
            "high_priority_review_items": ["STALE"],
            "evidence_gaps": [],
        },
        "retrieval_audit": {
            "external_retrieval_called": True,
            "high_trust_candidates_used": ["STALE"],
        },
    }
    result = apply_gate(raw_response, runtime)
    response = result["response"]
    finding = response["findings"][0]
    assert "gate_original_project_summary" in response
    assert "gate_original_retrieval_audit" in response
    assert response["project_summary"]["findings_count"] == 1
    assert response["project_summary"]["high_priority_review_items"] == ["F001"]
    assert finding["assistant_recommendation"]["substantive_conclusion"] != "旧的模型风险建议。"


def test_checkpoint03_bounded_comparisons_and_true_gaps() -> None:
    # Generic runtime-only fixtures: arbitrary values/letters/IDs, no gold file.
    examples = [
        ("正文写投标有效期120日，投标函写45日。",
         "招标人应当在招标文件中载明投标有效期。", "同一投标有效期", "不推定投标无效"),
        ("招标文件写开标地点为东会议室，开标记录写为西会议室。",
         "开标地点应当为招标文件中预先确定的地点。", "地点记载", "不认定实际违规"),
        ("共同投标协议被列为资格文件，但清单中没有该协议。",
         "联合体各方应当签订共同投标协议，并将共同投标协议连同投标文件一并提交招标人。",
         "协议列项差异", "不推定实际未提交"),
        ("招标文件修改通知引用补充文件Z，投标人签收记录中没有Z。",
         "招标人修改招标文件，应当以书面形式通知所有招标文件收受人。",
         "签收记录", "不推定未送达"),
        ("招标文件明确要求须提交执业资格证明；当前已审材料未提供执业资格证明。",
         "投标文件应当对招标文件提出的实质性要求和条件作出响应。",
         "证明缺口", "不等于人员或企业没有资格"),
        ("当前已审材料未提供执业资格证明。",
         "本阶段应当提交执业资格证明。", "证明缺口", "不等于人员或企业没有资格"),
    ]
    coverage = {key: "missing" for key in ("subject", "conduct_or_condition", "jurisdiction_and_scope", "legal_consequence")}
    coverage["conduct_or_condition"] = "conflicting"
    for fact, quote, claim, limit in examples:
        runtime = _runtime(issue_id="RUNTIME-COMPARE-73", document_excerpt=fact)
        runtime["retrieved_legal_evidence"][0]["legal_quote"] = quote
        raw = _finding(issue_id=runtime["issue_id"], conclusion="insufficient_information",
                       category="missing_or_insufficient_evidence", relation="requirement_not_shown", coverage=coverage)
        raw["assistant_recommendation"] = {"substantive_conclusion": "投标无效且未送达。", "recommended_handling": "直接否决。"}
        result = apply_gate({"findings": [raw]}, runtime)
        out = result["response"]["findings"][0]
        assert out["conclusion_type"] == REQUIRES_HUMAN_LEGAL_REVIEW, (fact, out["runtime_bounded_review"])
        assert out["runtime_fact_law_relation_validation"]["available"] is False
        assert out["confirmation_validation_available"] is False
        assert result["response"]["stage3_decision_audit"]["confirmed_count"] == 0
        assert result["response"]["overall_review_status"] == "requires_human_second_review"
        rec = out["assistant_recommendation"]
        assert claim in rec["substantive_conclusion"] and limit in rec["substantive_conclusion"]
        assert fact in rec["substantive_conclusion"] and "第3.2条" in rec["substantive_conclusion"]
        assert "直接否决" not in rec["recommended_handling"]
        # Same fact, unavailable requirement: no review on related law alone.
        runtime["retrieved_legal_evidence"][0]["legal_quote"] = "招标活动应当遵循公开原则。"
        negative = apply_gate({"findings": [raw]}, runtime)["response"]["findings"][0]
        assert negative["conclusion_type"] == INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM, fact

    gaps = [
        "合同未提供投标有效期，无法核验保证金有效期是否一致。",
        "合同未提供项目估算价，无法计算保证金比例。",
        "施工许可证没有签发日期，无法判断三个月期限。",
        "补充通知未记录发送日期，无法判断是否按时通知。",
        "文件包未提供施工许可证或限额以下例外证明。",
        "文件包未提供规划许可证，无法核验申请条件。",
        "开标时间和地点与招标文件预先确定的内容一致。",
        "未提供承包企业专业技术人员执业资格证明。",
    ]
    for fact in gaps:
        runtime = _runtime(document_excerpt=fact)
        raw = _finding()  # Even optimistic model coverage cannot fill these facts.
        out = apply_gate({"findings": [raw]}, runtime)["response"]["findings"][0]
        assert out["conclusion_type"] == INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM, fact
        assert out["runtime_bounded_review"]["missing_decisive_facts"], fact
        assert "不形成违规指控" in out["assistant_recommendation"]["substantive_conclusion"]
        assert "尚缺" in out["recommended_human_action"]

    for fact in ("投标有效期存在冲突。", "正文写投标有效期90日，投标函内容未提供。",
                 "正文写投标有效期90日，另一标段的投标函写60日。",
                 "正文写投标有效期90日，投标函写90日。",
                 "修改通知引用补充文件Z，投标人签收记录中没有Y。"):
        runtime = _runtime(document_excerpt=fact)
        runtime["retrieved_legal_evidence"][0]["legal_quote"] = "招标人应当在招标文件中载明投标有效期。"
        raw = _finding(coverage=coverage)
        out = apply_gate({"findings": [raw]}, runtime)["response"]["findings"][0]
        assert out["conclusion_type"] == INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM, fact

    runtime = _runtime(document_excerpt="当前已审材料未提供执业资格证明。")
    runtime["retrieved_legal_evidence"][0]["legal_quote"] = "本阶段可以提交执业资格证明。"
    out = apply_gate({"findings": [_finding()]}, runtime)["response"]["findings"][0]
    assert out["conclusion_type"] == INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM
    runtime["retrieved_legal_evidence"][0]["legal_quote"] = "本阶段应当提交执业资格证明。"
    runtime["contract_evidence"]["extraction_status"] = "incomplete"
    out = apply_gate({"findings": [_finding()]}, runtime)["response"]["findings"][0]
    assert out["conclusion_type"] == INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM


def test_shared_admission_is_identical_and_nulls_survive_gate() -> None:
    from external_fallback_v2 import is_usable_legal_basis
    from llm_abstention_gate import _is_usable_legal_basis
    assert _is_usable_legal_basis is is_usable_legal_basis
    for key in ("independent_legal_evidence", "independent_evidence", "legal_evidence_eligibility",
                "retrieval_admission", "verification_status"):
        runtime = _runtime()
        runtime["retrieved_legal_evidence"][0][key] = None
        out = apply_gate({"findings": [_finding()]}, runtime)["response"]["findings"][0]
        assert out["conclusion_type"] == INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM, key
        assert out["assistant_recommendation"]["supporting_legal_evidence"] == [], key


def test_tender_proof_quote_and_legal_quote_keep_separate_locators() -> None:
    tender_quote = "招标文件明确要求须提交执业资格证明"
    legal_quote = "投标文件应当对招标文件提出的实质性要求和条件作出响应"
    runtime = _runtime(document_excerpt=tender_quote + "；当前已审材料未提供执业资格证明。",
                       document_location="资格文件第8项")
    runtime["retrieved_legal_evidence"][0]["legal_quote"] = legal_quote + "。"
    raw = _finding(relation="requirement_not_shown")
    result = apply_gate({"findings": [raw]}, runtime)
    out = result["response"]["findings"][0]
    bounded = out["runtime_bounded_review"]
    assert out["conclusion_type"] == REQUIRES_HUMAN_LEGAL_REVIEW
    assert bounded["tender_requirement_quote"] == tender_quote
    assert bounded["tender_requirement_locator"] == "资格文件第8项"
    assert bounded["tender_requirement_document_id"] == "DOC-001"
    assert bounded["requirement_quote"] == legal_quote
    assert tender_quote not in bounded["requirement_quote"]
    assert bounded["requirement_locator"] == "示例全国性法律 第十二条"
    tender_attribution = f"招标要求：DOC-001 资格文件第8项“{tender_quote}”。"
    legal_attribution = f"法规原文：示例全国性法律 第十二条“{legal_quote}”。"
    for text in (out["reasoning_conclusion"], out["assistant_recommendation"]["substantive_conclusion"],
                 result["response"]["review_table"][0]["assistant_recommendation"]["substantive_conclusion"]):
        assert tender_attribution in text
        assert legal_attribution in text
        assert f"第十二条“{tender_quote}" not in text
    assert out["legal_evidence"][0]["legal_quote"] == legal_quote + "。"
    assert out["assistant_recommendation"]["supporting_legal_evidence"][0]["source_locator"] == "第十二条"


def test_bounded_discrepancy_overrides_model_noissue_without_triage() -> None:
    examples = (
        ("正文写投标有效期120日，投标函写45日。", "招标人应当在招标文件中载明投标有效期。"),
        ("共同投标协议被列为资格文件，但清单中没有该协议。",
         "联合体各方应当将共同投标协议连同投标文件一并提交招标人。"),
        ("招标文件修改通知引用补充文件Z，投标人签收记录中没有Z。",
         "招标人修改招标文件，应当以书面形式通知所有招标文件收受人。"),
        ("招标文件明确要求须提交执业资格证明；当前已审材料未提供执业资格证明。",
         "投标文件应当对招标文件提出的实质性要求和条件作出响应。"),
    )
    for fact, quote in examples:
        runtime = _runtime(document_excerpt=fact)
        runtime["retrieved_legal_evidence"][0]["legal_quote"] = quote
        assert runtime["hierarchy_retrieval_audit"]["levels"] == []
        for incomplete in (False, True):
            raw = _finding(conclusion=NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE,
                           category="no_issue_identified", relation="explicitly_satisfied")
            raw.update(severity_basis="no_supported_issue", risk_severity="informational",
                       reasoning_conclusion="当前条款全部满足要求。",
                       assistant_recommendation={"substantive_conclusion": "无需复核。", "recommended_handling": "直接放行。"})
            if incomplete:
                raw["legal_element_coverage"].update(conduct_or_condition="conflicting", legal_consequence="missing")
            result = apply_gate({"findings": [raw]}, runtime)
            out = result["response"]["findings"][0]
            assert out["runtime_bounded_review"]["eligible"] is True
            assert out["conclusion_type"] == REQUIRES_HUMAN_LEGAL_REVIEW, (fact, incomplete)
            assert out["compliance_relation"] == "unresolved"
            assert out["risk_category"] != "no_issue_identified"
            assert out["gate_original_compliance_relation"] == "explicitly_satisfied"
            assert out["gate_original_conclusion"] == "当前条款全部满足要求。"
            assert out["confirmation_validation_available"] is False
            assert result["response"]["stage3_decision_audit"]["confirmed_count"] == 0
            assert result["response"]["overall_review_status"] == "requires_human_second_review"
            assert fact in out["assistant_recommendation"]["substantive_conclusion"]
            assert "直接放行" not in result["response"]["table_markdown"]
            assert out.get("possible_over_alert") is not True  # No invented triage conflict.
    runtime = _runtime(document_excerpt="正文写投标有效期45日，投标函写45日。")
    runtime["retrieved_legal_evidence"][0]["legal_quote"] = examples[0][1]
    raw = _finding(conclusion=NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE,
                   category="no_issue_identified", relation="explicitly_satisfied")
    out = apply_gate({"findings": [raw]}, runtime)["response"]["findings"][0]
    assert out["runtime_bounded_review"]["eligible"] is False
    assert out["conclusion_type"] == NO_SUPPORTED_ISSUE_WITHIN_REVIEW_SCOPE


def main() -> int:
    tests = [
        ("conclusion aliases and mapping", test_conclusion_aliases_and_mapping),
        ("runtime confirmation", test_confirm_requires_runtime_record_and_trusted_record_can_confirm),
        ("stale/model confirmation", test_stale_hash_and_model_validation_cannot_confirm),
        ("runtime provenance/document fields", test_runtime_provenance_and_document_fields_override_model),
        ("external pending", test_external_pending_is_not_independent),
        ("no-law audit", test_no_law_requires_completed_external_audit),
        ("model no-law invariant", test_model_no_law_cannot_survive_when_usable_evidence_supports_no_issue),
        ("national risk scope", test_national_risk_with_missing_scope_remains_review),
        ("runtime missing-material relation", test_missing_material_requires_runtime_relation_and_blocks_level4_support),
        ("provenance fail-closed", test_null_negative_admission_and_duplicate_runtime_chunks_fail_closed),
        ("coverage/applicability fail-closed", test_invalid_coverage_and_non_level4_mismatch_are_not_supported),
        ("issue-specific over-alert", test_issue_specific_over_alert_does_not_spread_to_unrelated_finding),
        ("shared article binding", test_shared_article_without_finding_binding_does_not_spread),
        ("identity/empty blocking", test_empty_duplicate_and_unexpected_ids_block),
        ("final consistency", test_final_consistency_removes_stale_positive_state_after_insufficiency),
        ("summary/audit rebuild", test_changed_conclusion_rebuilds_summary_and_preserves_original_audit),
        ("checkpoint03 bounded comparisons and true gaps", test_checkpoint03_bounded_comparisons_and_true_gaps),
        ("single shared admission and runtime nulls", test_shared_admission_is_identical_and_nulls_survive_gate),
        ("separate tender and legal quote locators", test_tender_proof_quote_and_legal_quote_keep_separate_locators),
        ("bounded discrepancy overrides noissue without triage", test_bounded_discrepancy_overrides_model_noissue_without_triage),
    ]
    for name, test in tests:
        _run(name, test)
    print(f"PASS all {len(tests)} Stage 3 v2 offline regression groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
