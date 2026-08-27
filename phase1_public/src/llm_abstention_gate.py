"""Deterministic post-LLM schema and abstention gate.

The gate is deliberately independent of the language model. It canonicalizes
evidence metadata from the runtime retrieval package, rejects citations that
were not supplied to the model, and forces an insufficient-information or
human-review outcome when decisive legal elements are missing. Under the
approved v5 policy, a concrete risk supported by usable Level 1-3 evidence
remains a human-legal-review outcome even when project scope metadata is
incomplete; Level 4 evidence is usable only after local applicability is
matched.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


DECISIVE_FIELDS = (
    "subject",
    "conduct_or_condition",
    "jurisdiction_and_scope",
    "legal_consequence",
)
MISSING_STATES = {"missing", "conflicting", "unknown", ""}
RISK_CONCLUSION_TYPES = {"potential_risk", "requires_human_legal_review"}
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


def _minimal_response(runtime_input: dict, reason: str) -> dict:
    table = [{
        "test_result": "blocked",
        "contract_original_text": runtime_input.get("contract_evidence", {}).get("document_excerpt", ""),
        "conclusion": {
            "conclusion_type": "insufficient_information",
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
    }


def _canonicalize_evidence(finding: dict, runtime_input: dict, actions: list[str]) -> tuple[list[dict], bool, bool]:
    supplied = {
        row.get("chunk_id"): row
        for row in runtime_input.get("retrieved_legal_evidence", [])
        if row.get("chunk_id")
    }
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
        )
        for field in authoritative_fields:
            value = source.get(field)
            if value is None and field == "independent_legal_evidence":
                value = not (
                    source.get("legal_evidence_eligibility") == "supplement_only"
                    or source.get("source_role") == "practice_material_only"
                )
            elif value is None and field == "legal_evidence_eligibility":
                value = (
                    "supplement_only"
                    if source.get("source_role") == "practice_material_only"
                    else "independent_candidate"
                )
            elif value is None and field == "citation_mode":
                value = (
                    "contextual_only"
                    if source.get("source_role") == "practice_material_only"
                    else "verbatim_source_citation"
                )
            if value is not None:
                _set_field(item, field, value, actions, f"legal_evidence[{index}]")
        _set_field(item, "legal_quote", source.get("legal_quote", ""), actions, f"legal_evidence[{index}]")

        if not item.get("source_locator") or not item.get("legal_quote"):
            invalid = True
            actions.append(f"rejected legal_evidence[{index}] because locator or quote is empty")
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


def _is_level4(item: dict) -> bool:
    return item.get("normative_level") == "Level 4" or (
        item.get("scope_classification") == "local_regional"
        and item.get("normative_level") not in {"Level 1", "Level 2", "Level 3"}
    )


def _is_usable_legal_basis(item: dict) -> bool:
    if not item.get("source_locator") or not item.get("legal_quote"):
        return False
    if item.get("independent_legal_evidence") is False:
        return False
    if item.get("legal_evidence_eligibility") in {
        "supplement_only",
        "verification_only",
        "not_admitted",
    }:
        return False
    if item.get("source_role") == "practice_material_only":
        return False
    if _is_level4(item) and item.get("applicability_status") != "matched":
        return False
    return True


def _finding_claims_concrete_risk(finding: dict) -> bool:
    return (
        finding.get("conclusion_type") in RISK_CONCLUSION_TYPES
        or finding.get("risk_category") in RISK_CATEGORIES
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
    conclusion = finding.get("conclusion_type")
    if conclusion == "requires_human_legal_review":
        return "risk_supported"
    if conclusion == "no_supported_issue_found_within_review_scope":
        return "no_supported_issue_found"
    if conclusion == "insufficient_information":
        return "insufficient_information"
    return "blocked"


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
        if isinstance(evidence, dict)
    ]


def _default_processing_label(finding: dict) -> str:
    label = finding.get("review_processing_label")
    if label in PROCESSING_LABEL_VALUES:
        return label
    if finding.get("conclusion_type") == "no_supported_issue_found_within_review_scope":
        return "accepted"
    if finding.get("conclusion_type") == "insufficient_information":
        return "revised"
    if not any(_is_usable_legal_basis(item) for item in finding.get("legal_evidence", []) if isinstance(item, dict)):
        return "rejected"
    return "revised"


def _default_substantive_recommendation(finding: dict) -> dict:
    recommendation = finding.get("assistant_recommendation")
    if isinstance(recommendation, dict):
        if recommendation.get("substantive_conclusion") and recommendation.get("recommended_handling"):
            recommendation = dict(recommendation)
            recommendation["supporting_legal_evidence"] = _legal_basis_for_recommendation(finding)
            return recommendation

    basis = _legal_basis_for_recommendation(finding)
    basis_names = []
    for item in basis:
        label = " ".join(
            part
            for part in (item.get("law"), item.get("article"), item.get("source_locator"))
            if part
        )
        if label:
            basis_names.append(label)
    basis_text = "、".join(basis_names) or "当前已提供证据"
    conclusion = finding.get("conclusion_type")
    category = finding.get("risk_category")
    combined = " ".join(
        str(finding.get(key, ""))
        for key in ("reasoning_conclusion", "recommended_human_action")
    )
    if conclusion == "no_supported_issue_found_within_review_scope":
        substantive = "当前审查范围内未发现有充分证据支持的风险。"
        handling = "建议暂不将该条款列为风险项，但保留人工二次审核和审查范围限定。"
    elif conclusion == "insufficient_information":
        substantive = f"当前证据不足以判断该问题是否违反相关法规；现有参考依据为：{basis_text}。"
        handling = finding.get("recommended_human_action") or "建议补充缺失文件、工程地点、工程类型或适用标准后进行人工二次审核。"
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
                    "reference_purpose": evidence.get("reference_purpose", ""),
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
                "assistant_recommendation": _default_substantive_recommendation(finding),
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


def apply_gate(raw_response: Any, runtime_input: dict) -> dict:
    """Return raw-preserving gate result with a safe final response."""

    actions: list[str] = []
    if not isinstance(raw_response, dict):
        reason = "LLM response was not a JSON object"
        return {
            "status": "blocked",
            "blocked": True,
            "actions": [reason],
            "response": _minimal_response(runtime_input, reason),
        }

    response = deepcopy(raw_response)
    _set_field(response, "run_id", runtime_input.get("run_id", ""), actions, "root")
    _set_field(response, "project_id", runtime_input.get("project_id", ""), actions, "root")
    _set_field(response, "output_format", "review_table", actions, "root")
    _set_field(response, "overall_review_status", "requires_human_second_review", actions, "root")
    if not isinstance(response.get("findings"), list):
        reason = "LLM response findings is not a list; review_table/table_markdown are gate-generated and cannot replace findings"
        return {
            "status": "blocked",
            "blocked": True,
            "actions": actions + [reason],
            "response": _minimal_response(runtime_input, reason),
        }

    runtime_scope = runtime_input.get("review_scope", {})
    if not isinstance(response.get("review_scope"), dict):
        response["review_scope"] = deepcopy(runtime_scope)
        actions.append("corrected root.review_scope")
    if runtime_scope.get("jurisdiction_status") != "confirmed":
        _set_field(response["review_scope"], "jurisdiction_status", runtime_scope.get("jurisdiction_status", "uncertain"), actions, "review_scope")

    for index, finding in enumerate(response["findings"]):
        path = f"findings[{index}]"
        if not isinstance(finding, dict):
            response["findings"][index] = {
                "finding_id": f"GATE-{index + 1:03d}",
                "conclusion_type": "insufficient_information",
                "confidence_assessment": "insufficient_information",
                "human_review_status": "review_required",
                "assistant_recommendation": "revised",
                "reasoning_conclusion": "依据当前材料无法得出确切结论：finding 不是 JSON object。",
            }
            actions.append(f"replaced {path} with safe insufficient-information finding")
            continue

        contract = runtime_input.get("contract_evidence", {})
        for field in ("document_id", "document_location", "document_excerpt"):
            if contract.get(field):
                _set_field(finding, field, contract[field], actions, path)

        _normalize_risk_severity(finding, actions, path)

        coverage = finding.get("legal_element_coverage")
        if not isinstance(coverage, dict):
            coverage = {}
            finding["legal_element_coverage"] = coverage
            actions.append(f"created {path}.legal_element_coverage")
        missing_fields = [field for field in DECISIVE_FIELDS if coverage.get(field) in MISSING_STATES or field not in coverage]
        if runtime_scope.get("jurisdiction_status") != "confirmed" and "jurisdiction_and_scope" not in missing_fields:
            missing_fields.append("jurisdiction_and_scope")
            _set_field(coverage, "jurisdiction_and_scope", "missing", actions, f"{path}.legal_element_coverage")

        evidence, invalid_evidence, only_supplementary = _canonicalize_evidence(finding, runtime_input, actions)
        usable_evidence = [item for item in evidence if _is_usable_legal_basis(item)]
        blocked_level4 = [
            item for item in evidence
            if _is_level4(item) and not _is_usable_legal_basis(item)
        ]
        explicit_no_issue = _finding_is_explicitly_compliant(finding)
        usable_non_level4 = [item for item in usable_evidence if not _is_level4(item)]
        no_issue_eligible = bool(usable_evidence) and explicit_no_issue and (
            not blocked_level4 or bool(usable_non_level4)
        )
        evidence_backed_risk = (
            bool(usable_evidence)
            and _finding_claims_concrete_risk(finding)
            and not no_issue_eligible
        )
        force_insufficient = (
            not usable_evidence
            or (bool(missing_fields) and not evidence_backed_risk and not no_issue_eligible)
            or (invalid_evidence and not usable_evidence)
        )
        old_conclusion = finding.get("reasoning_conclusion", "")
        if force_insufficient:
            if old_conclusion and "gate_original_conclusion" not in finding:
                finding["gate_original_conclusion"] = old_conclusion
            reason_parts = []
            if missing_fields:
                reason_parts.append("缺少决定性法律要件：" + "、".join(missing_fields))
            if not evidence:
                reason_parts.append("没有可用且可定位的运行时法规证据")
            if invalid_evidence:
                reason_parts.append("部分法规引用未通过运行时证据回配")
            reason = "；".join(reason_parts)
            _set_field(finding, "conclusion_type", "insufficient_information", actions, path)
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
            _set_field(finding, "reasoning_conclusion", f"依据当前材料无法得出确切结论。{reason}。", actions, path)
            if not finding.get("recommended_human_action"):
                action = (
                    "补充工程所在地、工程类型和必要的地方适用范围，确认 Level 4 法规适用性后重新审查。"
                    if blocked_level4
                    else "补充项目所在地、项目类型和适用法规版本，并提交专业人员复核。"
                )
                _set_field(finding, "recommended_human_action", action, actions, path)
        elif no_issue_eligible:
            if finding.get("conclusion_type") != "no_supported_issue_found_within_review_scope":
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
                "no_supported_issue_found_within_review_scope",
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
            _set_field(finding, "conclusion_type", "requires_human_legal_review", actions, path)
            _set_field(
                finding,
                "confidence_assessment",
                "low" if missing_fields or invalid_evidence else "medium",
                actions,
                path,
            )
            _set_field(finding, "evidence_support_confidence", "medium", actions, path)
            _set_field(finding, "applicability_confidence", "medium", actions, path)
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
        elif only_supplementary:
            _set_field(finding, "conclusion_type", "requires_human_legal_review", actions, path)
            _set_field(finding, "confidence_assessment", "low", actions, path)
            _set_field(finding, "evidence_support_confidence", "low", actions, path)
            _set_field(finding, "applicability_confidence", "low", actions, path)
            _set_field(finding, "human_review_status", "review_required", actions, path)
            _set_field(finding, "evidence_boundary", "supported_by_supplementary_source_only", actions, path)

        recommendation = _default_substantive_recommendation(finding)
        _set_field(finding, "assistant_recommendation", recommendation, actions, path)
        processing_label = _default_processing_label(finding)
        _set_field(finding, "review_processing_label", processing_label, actions, path)

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
    if runtime_input.get("runtime_constraints", {}).get("external_retrieval_called") is False:
        _set_field(audit, "external_sources_used", [], actions, "retrieval_audit")
        _set_field(audit, "external_retrieval_called", False, actions, "retrieval_audit")

    review_table = _build_review_table(response)
    _set_field(response, "review_table", review_table, actions, "root")
    _set_field(response, "table_markdown", _build_table_markdown(review_table), actions, "root")

    return {
        "status": "corrected" if actions else "passed",
        "blocked": False,
        "actions": actions,
        "response": response,
    }
