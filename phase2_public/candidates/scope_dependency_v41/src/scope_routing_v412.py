"""Opt-in postprocessing only. Wire protocol and legal rules stay at v4.1.1.

Lexical recognition is conservative, finite and not a semantic truth oracle.
The two switches are separate to allow a same-response 2x2 offline comparison.
"""
from copy import deepcopy
import re

ENGINE_VERSION = "scope-routing-handoff-v4.1.2-candidate"
PERFORMANCE_ALIASES = ("合同履行阶段", "合同履行期间", "后续实际履行", "中标后实际履行")
CURRENT_TEXT_GUARDS = (
    r"(?:承诺|条款|文字|文本|约定).{0,12}(?:未包含|未涵盖|未说明|未明确|未约定|缺少|遗漏)",
    r"(?:未包含|未涵盖|未说明|未明确|未约定).{0,18}(?:承诺|条款|期限|时间|期间|阶段)",
    r"关键日期|起算点|否定词|适用条件|当前条款|承诺期限",
)


def recognize_material(gap, patterns):
    detail = str(gap.get("detail") or "")
    matches = [{"dependency_key": dep, "text": m.group(), "start": m.start(), "end": m.end(),
                "source_field": "detail", "match_type": "existing_pattern"}
               for dep, pattern in patterns.items() for m in re.finditer(pattern, detail)]
    for word in PERFORMANCE_ALIASES:
        matches += [{"dependency_key": "actual_performance", "text": m.group(),
                     "start": m.start(), "end": m.end(), "source_field": "detail",
                     "match_type": "reviewed_alias"} for m in re.finditer(re.escape(word), detail)]
    signalled = {m["dependency_key"] for m in matches}
    guards = [m.group() for pattern in CURRENT_TEXT_GUARDS for m in re.finditer(pattern, detail)]
    audit = {"engine_version": ENGINE_VERSION, "matches": matches,
             "current_text_guard_matches": guards, "detail_only_recognition": True,
             "semantic_correctness_verified": False}
    # A future-performance name cannot conceal missing present promise content.
    reason = None
    if gap.get("task_relation") == "outside_locked_scope" and gap.get("dependency_key") == "actual_performance" and guards:
        reason = "current_text_dependency_not_excludable_by_performance_alias"
    return signalled, audit, reason


def processing_presentation(finding):
    """Return display updates only; never create/change a legal verdict or gap."""
    audit = finding.get("nu_boundary_audit") or {}
    state = audit.get("processing_status")
    if state not in {"scope_review_required", "schema_blocked", "evidence_binding_blocked"}:
        return None
    blocking = deepcopy(audit.get("blocking_gaps", []))
    scope_items = deepcopy(audit.get("scope_review_items", []))
    if state == "scope_review_required":
        text = "该事项与锁定任务的关系尚未确认，原始模型判断暂不放行；范围待复核不是已经成立的法律信息不足结论。"
        action = "请先确认列出的事项属于当前文本比较还是范围外核验，并检查材料类型、子结论依赖和阻断标记是否一致。"
        category = "scope_relationship_unresolved"
        if blocking:
            text += "另有已列阻断缺口，必须与关系待确认事项分开复核，不能一并排除。"
            action += "已列阻断缺口：" + "；".join(str(x.get("detail", "")) for x in blocking) + "。"
            category = "scope_unresolved_with_reported_blocking_gaps"
        if scope_items:
            action += "关系待确认事项：" + "；".join(str(x.get("detail", "")) for x in scope_items) + "。"
    elif state == "schema_blocked":
        text = "输出协议或任务绑定未通过，当前没有可交付法律判断；不能把字段失败算成有效法律U。"
        action = "请核对协议字段、任务类型及输入绑定。保留原响应，不补写模型检查结论。"
        category = "protocol_or_task_binding_failure"
    else:
        text = "引文或证据定位未通过，当前没有可交付法律判断；尚未据此确认实质缺口或违规。"
        action = "请核对原文、定位与法条引用。保留原响应，不用猜测的引用替代。"
        category = "evidence_binding_failure"
    action += "全部结果仅供人工二次审核。"
    recommendation = deepcopy(finding.get("assistant_recommendation") or {})
    recommendation.update(substantive_conclusion=text, recommended_handling=action,
                          presentation_engine_version=ENGINE_VERSION, processing_status=state,
                          legal_verdict_available=False)
    comparison = recommendation.get("fact_law_comparison")
    if isinstance(comparison, dict):
        comparison.update(comparison_status="processing_hold_not_legal_comparison",
                          identified_difference="处理检查尚未完成，不生成新的合同—法规差异结论。")
    return {"reasoning_conclusion": text, "recommended_human_action": action,
            "assistant_recommendation": recommendation,
            "processing_presentation": {"engine_version": ENGINE_VERSION, "processing_status": state,
                "display_risk_category": category, "legal_verdict_available": False,
                "blocking_gaps": blocking, "scope_review_items": scope_items,
                "raw_and_compatibility_fields_preserved": True}}
