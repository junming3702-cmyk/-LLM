"""Generated field/enum instructions; no second handwritten allowed-value list."""
import json
from scope_citation_v3_prompt import build_prompt as legacy_prompt
from scope_dependency_v41_schema import SCHEMA, render_schema

POLICY = """

## 范围依赖 v4.1 候选：完整替换 decision_basis 协议
以下 schema 是本次 decision_basis 的唯一字段/类型/枚举规范，替代前文该对象的
旧版结构；其他外层输出字段、法源准入、地域/时效、引用及人工复核要求保持有效。
不得输出 schema 外字段。所有 required=true 字段必须填写，无法完成检查时不编造
completed_check；check 名称与 comparison 均必填，不能用一个字段替代另一个。
只读取运行端 review_task_contract_v41.scope_spec，不自行扩大或缩小任务。
把 input_scope_sha256 原样复制到 task_scope_sha256。

先判定要求是否在当前项目/子问题实际生效，再判断其数值、年份、数量是否缺失。
模板有某栏不等于强制提交；有两个措辞不等于已证实冲突。缺少实际真实性验证、
最终递交包或后续履行证据，不自动阻断已锁定的文本核对。
但实际提交核查、完整期限、专项合规等当前任务的决定性材料仍须保留为阻断。

严格区分三层：
1. kind/dependency_key 说明缺什么材料。不得把“范围外”写成材料种类。
2. task_relation/reason/counterfactual_impact 解释为什么影响当前子结论。
3. 输出分组由 gate 生成。不得在模型 gap 中填 output_group 或自行宣称已放行。
真正阻断须绑定 required_claims 中已声明的依赖及子结论，解释哪一步不能完成。
有具体条款解释冲突时提供 trigger_evidence 原文定位；泛泛无法确保不存在任何
补遗只是待澄清关系，不自动成为关键法源或当前条款缺口。
范围外须是锁定配置明确排除、不影响任何子结论、false和空claim数组同时满足。
若锁定配置漏列潜在必要依赖，或材料类别/关系尚不清楚，提交范围复核，不改任务。
一个记录混合整包、真实性、具体更正、数值等事项时必须分别列项。
关系无法确定用 scope_unresolved；不能静默当作法律 U，也不得把未知变成 N。

text_observation 只记录有定位的输入事实，无独立法规支持能力；
legal_comparison 绑定准入法条与所支持的当前子结论，说明适用前提和实际比较。
单有一条引文、一般性法条、supplement或“未发现冲突”不足以证明范围内N。
输出理由、结论、差异和建议供人复核，不输出内部思维链。
范围外事项仍可见，不表示已经满足。整体仍需要人工二次审核。

以下是机器可读字段说明（自同一 schema 自动生成）：
"""


def examples():
    """Both synthetic examples obey the exact same validator as model output."""
    check = {"check_id": "CK1", "check_kind": "legal_comparison",
             "check": "合成承诺文字与合成规则比对",
             "document_quote": "合成示例：申请人承诺提供有效证明。",
             "document_locator": "SYN-p001-b001", "legal_chunk_ids": ["SYN-law-1"],
             "claim_ids": ["C1"], "comparison": "合成情景中已给文字回应已给要求；不证明真实递交或法律正确。"}
    common = {"review_question": "合成问题：承诺是否回应文字要求？",
              "review_target": "document_response", "answerability": "sufficient",
              "task_scope_sha256": "COPY_RUNTIME_HASH_NOT_THIS_PLACEHOLDER",
              "completed_checks": [check], "bounded_conclusion": "仅限合成已给文字比对，不认证实际提交。",
              "gaps": [{"gap_id": "G1", "kind": "input_evidence_missing",
                        "dependency_key": "submission_package_completeness",
                        "detail": "最终递交包完整性尚未核验。",
                        "task_relation": "outside_locked_scope", "affected_claim_ids": [],
                        "blocks_current_question": False,
                        "reason": "合成锁定配置明确排除整包核查，C1只比较已给文字。",
                        "counterfactual_impact": "完整包状态不改变已给承诺与要求的文本关系。",
                        "dependency_trigger": "explicit_scope_exclusion", "trigger_evidence": []}]}
    from copy import deepcopy
    blocking = deepcopy(common)
    blocking.update(answerability="decisive_gap", completed_checks=[],
                    bounded_conclusion="合成锁定C1需要项目金额完成上限核算，现无法核算；保留U。")
    blocking["gaps"] = [{"gap_id": "G1", "kind": "comparison_value_missing",
                        "dependency_key": "comparison_operand", "detail": "计算上限需要的项目金额未提供。",
                        "task_relation": "decisive_for_claim", "affected_claim_ids": ["C1"],
                        "blocks_current_question": True,
                        "reason": "合成C1明确要求比较数额上限，其required_dependencies含comparison_operand。",
                        "counterfactual_impact": "没有金额分母无法计算并比较上限，补全后才可作答。",
                        "dependency_trigger": "locked_requirement", "trigger_evidence": []}]
    return {"pure_outside_item": common, "genuine_blocking_gap": blocking}


def build_addendum():
    return (POLICY + "\n" + render_schema() +
            "\n以下仅为协议合成示例，法条/定位/哈希占位符不可复制到真实输出；非法律结论：\n" +
            json.dumps(examples(), ensure_ascii=False, indent=2))


def build_prompt(base):
    return legacy_prompt(base) + build_addendum()
