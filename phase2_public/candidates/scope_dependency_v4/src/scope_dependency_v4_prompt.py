"""Candidate-only scope protocol; production prompt is unchanged."""
from scope_citation_v3_prompt import build_prompt as v3_prompt

ADDENDUM = '''

## 范围依赖 v4 候选：当前问题 → 子结论依赖 → 证据 → 输出
本节替代前文 decision_basis 的宽泛缺口归类及“每项 completed_check 均需法条”规则，
仅限该结构协议；不得覆盖法源准入、地域/时效、引用定位、检索及人工复审要求。

1. 先读取运行端提供的 review_task_contract_v4.scope_spec；它是本轮固定任务配置。
不得重写问题、增加实际履行或递交包完整性核验，也不得把范围内任务删成范围外。
把 input_scope_sha256 原样填入 decision_basis.task_scope_sha256。
原有 review_question、review_target、answerability、bounded_conclusion 必须保留。
先确认某项要求在本项目/当前子问题是否实际适用，再讨论它的数量、金额或期限缺口。
表格模板出现某栏，不自动证明项目强制要求该材料；不得把明确不适用的门槛转成缺数值。
仅因无法保证全包不存在其他补遗，不自动制造当前条款缺口；应说明具体条款解释为何
离不开特定上下文，或已有哪条信息表明存在影响当前要求的更正。潜在冲突不可直接写成已证实冲突。

2. completed_checks 每项新增唯一 check_id、check_kind、claim_ids。
check_kind=text_observation：只记录所给原文事实，必须有精确原文及定位；
legal_chunk_ids=[]、claim_ids=[]，不能独立支撑法律N/R或证明实际提交、真实性。
check_kind=legal_comparison：列出所支持的 required_claims.claim_id，引用准入法条，
说明原文与法规要求的具体相同/差异，列明必要适用前提；不能仅因引用了法条就判定成立。
每个要求作答的子结论都需其自身的合法、适用、可定位依据。片段引用继续遵循v3精确规则。

3. gaps 每项保留 kind/detail/blocks_current_question/reason，新增 dependency_key 和
affected_claim_ids。dependency_key 只可用：submission_package_completeness、
authenticity、actual_performance、current_clause_context、applicable_rule、
regulatory_applicability、comparison_operand、readability、other_undetermined。
明确解释：缺什么 → 影响哪个锁定子结论 → 为什么该结论离不开它。
affected_claim_ids 对应子结论的 required_dependencies 必须包含该 dependency_key；
若认为锁定配置漏列了必要依赖，应交回范围复核，不得擅自扩张或隐瞒缺口。
适用规则、决定性前提、比较数值、当前条款上下文和不可读证据，不得通过false或改名绕过。
不明依赖先保留，不猜测为范围外。一个缺口涉及多种依赖时拆开列示。

4. 仅当 scope_spec 明确排除了对应依赖，且它不影响任何当前子结论时，
才使用 blocks_current_question=false、affected_claim_ids=[]。
例如“仅核对承诺是否回应招标文字”不核验递交包完整性/真实履行；
但若当前任务就是核验实际提交、完整期限、签署效力、专项合规，则缺口仍阻断。
澄清、补遗、条款冲突的解释顺序、法条例外等，不因未核验整包而自动成为范围外。

5. 输出三类交接内容：已完成且可定位的观察；阻断当前子结论的缺口；
范围外、后续人工可选核验事项。范围外不等于已满足、不等于已实际提交。
存在决定性缺口仍输出U；保留可用观察，不把整项工作写成“完全无证据”。
仅剩范围外事项且所有当前子结论有充分依据时，才可依证据输出范围内N或风险判断。
不因想提高一致率而输出N，不把参考答案/历史专家标签作为输入，不作最终法律判断。
无论结论为何，整体 workflow_status 均为 requires_human_second_review。
'''


def build_prompt(base):
    return v3_prompt(base) + ADDENDUM
