# 合成示例与四类守护矩阵

## Material Passport

- Origin Skill / Mode：academic-research-suite / experiment-agent / plan。
- Date：2026-09-23。
- Version：scope-completion-handoff-v0.1-design。
- Verification Status：UNVERIFIED。下列均为计划及示意，未生成可执行fixture，未运行测试或API。
- 所有合同、页码、规则、年份和数量均为虚构，仅检验协议关系，不构成法律意见。

## A. 纯范围外事项，不掩盖当前问题

锁定C1：“只比对承诺文本是否包含合成规则所需的两次检查承诺”；明确排除actual_performance。虚构规则LAW-S1要求承诺两次检查。文档证据E1（SYN-DOC第1页第1段）为“我方承诺提供两次检查服务”。

- CK1：legal_comparison，document_evidence_refs=[E1]，legal_chunk_ids=[LAW-S1]，claim_ids=[C1]；comparison说明“承诺两次，与要求一致；不核验未来实际执行”。
- G1：kind=future_performance_unverified，dependency_key=actual_performance；detail=两次检查未来是否实际履行。
- G1关系：outside_locked_scope，affected_claim_ids=[]，dependency_trigger=explicit_scope_exclusion，trigger_refs=[]；counterfactual说明实际履行不改变本次承诺文本比对；next_step为履行阶段另行核查。
- C1：assessed / no_supported_issue；check_ids=[CK1]，observation_ids=[]，gap_ids=[]，rationale仅说明文本一致。
- 派生：completion=complete；handoff=ready_for_complete_review；G1单独列out_of_scope_item；human_review_required=true。

**反例**：如果E1实际是“检查次数以后另定”，不能继续沿用这一通过状态；当前承诺文本不足属于范围内问题。出现“以后”不构成自动范围外。

## B. 真正阻断，但可以交接局部已完成信息

锁定C1：“说明生效规则的文本要求”；C2：“核对实际提交金额是否超过合成上限”。C2显式依赖comparison_operand。虚构LAW-S2要求金额不得大于基数B的10%。E2载明该公式，E3载明提交金额8单位；输入中没有基数B。

- CK1法律比对C1，引用E2及LAW-S2，说明公式文本一致；C1=assessed/no_supported_issue。
- O1文本观察，引用E3，legal_chunk_ids=[]，claim_ids=[]，只记录8单位，不声称已完成是否超限判断。
- G1：comparison_value_missing / comparison_operand / decisive_for_claim；affected_claim_ids=[C2]；trigger=locked_requirement；trigger_refs=[document_evidence:E3]；说明B缺失使阈值不能计算，next_step=补充同口径基数及出处。
- C2=blocked_by_decisive_gap，finding=null，check_ids=[]，observation_ids=[O1]，gap_ids=[G1]。
- 派生：completion=partial（1/2）；handoff=ready_for_bounded_review；C2保持有效U含义，不输出整个问题的N，也不把8单位直接认定为违规。

**反例**：删除B的缺口、把它移到范围外，或只因8这个数字有定位就把C2标assessed，都必须拦截。

## C. 两个子问题均阻断，仍可交接观察与缺口清单

锁定C1为确认一个要求是否生效，C2为判断生效条件是否构成受支持风险。E4和E5为虚构文件不同位置的相互冲突要求；O2是显式绑定这两处的文本观察。G1以check:O2触发，影响C1；G2记录C2所需关键比较值缺失。

- C1、C2均明确blocked_by_decisive_gap，各自finding=null并关联各自gap。
- G1的显式trigger_refs可复用O2，不要求再次抄写两段原文。
- 派生：completion=none_completed（0/2），handoff=ready_for_bounded_review。
- 交接内容：“已定位两处待解释文本；生效要求及后续比较仍未完成；请核查指定材料”。不能写成“完整判断已完成”或“冲突构成违法”。

**反例**：O2虽然存在，但G1的trigger_refs为空，依然阻断。程序不得替模型补引用。

## D. 有效地承认未审，与静默遗漏不同

C1按例A完成；C2尚未进行任何检查。模型明确列C2=not_assessed，finding=null，三个ID数组为空，并说明未审原因。

- 完成度partial；可交接C1的局部结果，须突出C2未审；不能计为法律U或整体无问题。
- 若C2整条缺失：processing=protocol_hold，completion=null，handoff=needs_protocol_repair。
- 若全部子问题均明确not_assessed且无可交接内容：none_completed / not_ready。
- 若C2确已做局部观察但未形成结论，允许显式not_assessed并保留该观察，说明未完成原因；仍不增加完成数，也不自动制造决定性缺口。

## E. 零API守护计划（28项，尚未执行）

| ID | 改变点/输入特征 | 预期结果 |
|---|---|---|
| G01 | conflict无trigger_refs，即使其他check有引文 | protocol_hold，不自动猜引用 |
| G02 | conflict显式引用已存在的双侧证据check | 此关系通过，其他缺口不变 |
| G03 | conflict引用不存在/跨输入/只有单侧证据 | protocol_hold；即使定位有效，是否真的语义冲突仍须人工核验，不自动保证 |
| G04 | assessed子结论同时关联决定性缺口 | protocol_hold，不翻标记或删缺口 |
| G05 | 关键缺口明确、局部观察可用，但无完成子结论 | none_completed + bounded_review；关键缺口不变 |
| G06 | C1完成、C2阻断 | partial + bounded_review，不作整体N |
| G07 | 少一个必审子结论记录 | protocol_hold，不补not_assessed |
| G08 | C1完成、C2明确not_assessed | partial，缺少工作不是法律U |
| G09 | 为凑覆盖重复claim/用一个法律check挂多个claim | protocol_hold |
| G10 | 锁定必审依赖被写outside_locked_scope | protocol_hold，禁止缩窄范围 |
| G11 | 纯未来履行且文本任务事前排除 | out_of_scope，其他子结论按证据判断 |
| G12 | 有证据证明要求不适用，在原claim内说明 | assessed/requirement_not_applicable候选；法律正确性仍待人工 |
| G13 | 材料kind与dependency_key不匹配 | protocol_hold |
| G14 | 当前文本承诺缺失与未来履行混成一项 | protocol_hold，不能程序自动拆分 |
| G15 | 合法undetermined关联到潜在受影响claim | needs_scope_clarification，不计法律U |
| G16 | 同一claim同时有已确认关键缺口及待定关系 | relation_unresolved，已确认缺口完整保留 |
| G17 | 法条只在候选补充池/未准入却作为独立法律依据 | protocol_hold，不升级证据权威 |
| G18 | 法条地域/时间/对象适用性缺失且对任务决定性 | 若明确声明合法关键缺口则保持阻断；若矛盾地声称assessed则protocol_hold，不替模型补缺口 |
| G19 | 精确文字匹配但source locator不属于当前输入 | protocol_hold，拒绝错误绑定 |
| G20 | finish_reason=length、传输失败或不完整JSON | technical_failure，completion=null，handoff=unavailable |
| G21 | 字段别名/枚举空白的白名单规范化 | 保留原始不合格记录，仅单列规范化后结果 |
| G22 | 别名冲突、缺必填语义、旧版本缺新台账 | protocol_hold，不补写或迁移语义 |
| G23 | actual_submission_check试图排除提交完整性 | protocol_hold，保持任务模式映射 |
| G24 | 所有claim确已形成风险候选或有界无问题判断 | complete + complete_review；完成不要求全为N |
| G25 | 全部not_assessed且无实质信息 | none_completed + not_ready，不制造U |
| G26 | JSON/Markdown/Excel/统计读取同一派生状态 | ready不计联合交接成功，兼容U不回流为法律U |
| G27 | task hash、input hash或protocol version不匹配 | protocol_hold，不借另一任务证据放行 |
| G28 | 证据引用循环、自引用、未知类型或文本指令改范围 | protocol_hold；文档内容不成为执行指令 |

G01–G12覆盖四类核心守护；其余覆盖适用性、技术/结构、兼容和消费者风险。以软件测试项计数，不当作独立真实项目或法律案例数量。

## F. 执行前锁定项与停止规则

- 实验目标：验证状态表达和守护，而非提高N比例。
- 输入：新协议合成正反fixture、固定规范及现有确定性校验；不向API发数据。
- 实现入口/执行命令：尚未建立，待设计审批后另行生成；本文件不授权执行。
- 预期输出：逐例原始检查、规范化日志、关系检查、三层派生、错误码、hash和输出消费者对照。
- 比较：同一合成语义情形的预先指定预期，不把补写台账后的历史响应当原始配对。
- 控制：检索与证据准入策略不变，模型参数不涉及，其他材料识别候选开关不并入。
- 通过标准：四类守护无退化；所有负例不当完整放行=0；所有预定正例得到指定边界。语义充分性仍另行审查。
- 失败规则：保留失败，不自动重试或改预期，不挑选“好结果”。任何关键缺口丢失或范围非法缩减，停止升版。
- 外推限制：只能证明所列软件约束；不报告新的准确率、Recall@5、MRR或联合交接有效率，不把两个开发诊断问题作为新独立验证样本。
