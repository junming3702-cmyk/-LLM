"""Opt-in structural risk-binding audit; not a legal-entailment classifier.

This policy reads no reference labels and never declares a clause compliant.
It checks that a positive model claim names a usable, cited evidence item and
an explicit difference. Those necessary conditions are NOT sufficient proof
that the interpretation is legally correct. Human review remains mandatory.
"""
from conclusion_contract_v2 import (
    REQUIRES_HUMAN_LEGAL_CONFIRM, REQUIRES_HUMAN_LEGAL_REVIEW,
)

VERSION = 'risk-binding-v2'
RISK_STATES = {REQUIRES_HUMAN_LEGAL_CONFIRM, REQUIRES_HUMAN_LEGAL_REVIEW}


def audit_risk_binding(finding, *, canonical_input, usable_evidence,
                       risk_candidate, runtime_relation_supported=False,
                       trusted_confirmation=False):
    """Only caller-validated runtime relations may override model abstention.

    Do not pass model self-reported eligibility as either trusted argument.
    Usable evidence must already have passed provenance/applicability gates.
    """
    comparison = finding.get('fact_law_comparison')
    comparison = comparison if isinstance(comparison, dict) else {}
    chunk = comparison.get('supporting_chunk_id')
    chunk = chunk.strip() if isinstance(chunk, str) else ''
    difference = comparison.get('difference_summary')
    difference = difference.strip() if isinstance(difference, str) else ''
    usable_ids = {str(row['chunk_id']) for row in usable_evidence if row.get('chunk_id')}
    declared = finding.get('legal_evidence')
    declared = declared if isinstance(declared, list) else []
    cited_ids = {str(row['chunk_id']) for row in declared
                 if isinstance(row, dict) and row.get('chunk_id')}
    runtime_override = bool(usable_ids) and bool(runtime_relation_supported or trusted_confirmation)
    reasons = []
    if risk_candidate and not runtime_override:
        if canonical_input not in RISK_STATES:
            reasons.append('nonrisk_model_output_cannot_be_promoted_by_category_or_triage')
        if not chunk or chunk not in usable_ids or chunk not in cited_ids:
            reasons.append('missing_direct_usable_cited_supporting_chunk_id')
        if not difference:
            reasons.append('missing_explicit_fact_law_difference')
        if finding.get('compliance_relation') == 'out_of_scope_reference':
            reasons.append('model_relation_explicitly_outside_applicable_scope')
    return {'version': VERSION, 'evaluated_risk_candidate': bool(risk_candidate),
            'supporting_chunk_id': chunk, 'difference_present': bool(difference),
            'runtime_override': runtime_override, 'force_insufficient': bool(reasons),
            'reasons': reasons, 'legal_entailment_verified': False,
            'human_review_required': True}


PROMPT = '''

实验候选规则 risk-binding-v2（不改变证据池和审查任务）：
1. 先核对规则对象、适用制度、义务发生阶段及例外，再比较当前条款。未检索到允许某行为的规定不等于该行为被禁止；未检索到禁止规定也不等于已经合规。
2. 文字不同不等于违反：比较义务的实质、上下限方向、单位、起算事件、适用条件及例外。约定更短期限是否满足法定最长期限等问题须按同一对象和起算条件判断，不能单纯用数字或措辞不相等报警。
3. 区分条款本身预审与实际履约/授标行为核验。非决定性的未知事实不应单独迫使弃答；真正影响规则适用或事实比较的缺口必须保留。未提供附件不等于附件不存在。
4. 主张风险时必须给出 fact_law_comparison.supporting_chunk_id（来自本次已准入且已引用的法条）以及 difference_summary，明确“当前合同内容—该法条具体要求—差异—建议人工处理”。找不到直接绑定或只有主题相关时输出 insufficient_information_needs_human_confirm，不用风险类别或检索阶段的风险标记替代事实与法条之间的支持关系。
5. 对未发现风险的判断保留限定审查范围；对支持不足不输出确定合法或违法。所有结论仍需人工复核。只输出约定 JSON，简明填写一个 finding；不要重复整份原文或完整法条。
'''
