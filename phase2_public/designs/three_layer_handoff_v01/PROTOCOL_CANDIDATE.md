# 子结论状态—整体问题完成度—人工交接状态：候选协议

## Material Passport

- Origin Skill / Mode：academic-research-suite / experiment-agent / plan。
- Origin Date：2026-09-23。
- Version Label：`scope-completion-handoff-v0.1-design`。
- 此编号是设计稿编号，不是当前运行端支持的wire版本；不能直接替换线上schema。
- Verification Status：UNVERIFIED；本文件为待审批设计，不是已实现或已验证协议。
- 实现基线：v4.1.1字段协议；独立v4.1.2路由候选仍保持原开关与状态。
- 本轮范围：仅新增设计文档。无线上调用，无运行代码、Prompt、gate或历史结果变更。
- 内容：通用模型设计与完全合成示例；不含真实合同、专家评分、申请材料或API凭据。

## 1. 目标与非目标

目标是如实表达：哪些必审子问题已有有界判断、哪些被真正决定性的缺口阻断、哪些尚未完成，以及哪些信息可以交给人工。**发现有用信息、完成整个问题、获得正确法律结论，是不同事件。**

候选假设：显式子结论台账和单向派生关系，可以减少状态自相矛盾，并使未完成任务的交接边界可检查。该假设尚未验证；不预设N增多、专家一致率提高或法律准确率提高。

非目标：不改变锁定问题，不放松法律/引用/适用性要求，不调整参照，不修补旧响应的语义，不自动认定违规或合规，不新增检索或上下文，不启用v4.1.2材料识别候选。

## 2. 三层与前置处理检查

| 层次 | 回答的问题 | 状态来源 | 不能据此推导 |
|---|---|---|---|
| 前置处理检查 | 响应是否完整、结构/引用/关系是否符合协议？ | 程序检查并保留原因码 | 处理失败不等于法律信息不足 |
| 子结论状态 | 每个事前锁定子问题做到哪一步？ | 模型逐项声明，gate检查相容性 | 有一个观察，不等于该法律子问题已完成 |
| 整体问题完成度 | 所有必审子问题是否都已形成有界判断？ | gate从有效台账派生 | 完成不等于无风险，也不等于法律正确 |
| 人工交接状态 | 当前材料以什么边界交接？ | gate按优先级派生 | 可以交接不等于联合交接有效性已通过 |

本协议中的`assessed`仅指：模型已提交该子问题的判断，且满足预定结构、绑定及关系条件。它不是独立语义核验、专家认可或司法确认。

## 3. 数据与权限边界

### 3.1 调用端锁定，不由模型修改

保留任务模式、目标类型、问题、必审子结论、每项依赖、允许排除项、输入/任务hash、法规准入状态和外检快照。任务映射继续使用同一规范：

| review_mode | review_target | 可使用事前批准的文本范围排除 |
|---|---|---|
| clause_design | textual_pre_review | 是 |
| text_response_comparison | document_response | 是 |
| actual_submission_check | document_completeness | 否 |
| actual_conduct_check | actual_conduct | 否 |

候选新增由调用端生成的**证据注册表**：`evidence_id → 原文片段、source locator、文档hash、输入版本`。模型只能引用已提供ID。法规仍用已准入的`legal_chunk_ids`，不因建立注册表改变效力、时间、地域或补充证据的使用边界。

证据ID复用是为了避免重复抄写，不是降低定位要求。若现有输入不能生成可靠注册表，应保持该事实并停止对应放行，不能倒推或伪造物理页码。

### 3.2 模型提供

`protocol_version`、原样复制的任务绑定、`claim_assessments`、`completed_checks`和`gaps`。只要求最终可核验理由，不要求披露内部思维链。

模型不再提交具有决定权的`answerability`、`blocks_current_question`、整体完成度或交接状态。缺口对任务的影响通过“影响哪个子结论”表达，由gate派生。旧布尔值的取消不是删除关键缺口。

### 3.3 程序派生，人工最终确认

程序派生`processing_status`、有效子结论台账、`question_completion`、`completion_reasons`、`handoff_status`和缺口分组；`human_review_required=true`始终保留。

人工判断法律适用、缺口必要性和交接信息是否真正有用。程序不得将引文存在、法条ID存在或字段齐全升级为这些人工判断。

## 4. 第一层：子结论状态与必填账目

每个锁定`required_claim_id`必须恰好出现一次。不得多写、漏写、重复或自行改写问题。

| assessment_state | 含义 | 最低条件 | finding |
|---|---|---|---|
| assessed | 已形成该子问题的有界判断 | 至少一个对应法律比对；无影响本子问题的决定性或关系待定缺口 | supported_risk_candidate / no_supported_issue / requirement_not_applicable |
| blocked_by_decisive_gap | 已开展审查，但该子问题有真正决定性缺口 | 至少一个合法且显式关联的decisive gap；可同时保留局部检查和观察 | null |
| relation_unresolved | 无法确定某材料对该子问题的必要关系 | 至少一个显式关联的undetermined事项 | null |
| not_assessed | 尚未形成该子结论，且没有声称已确认决定性或关系待定原因 | 说明是尚未开展还是仅完成局部检查；不得用它隐藏已声明的决定性缺口 | null |

每条`claim_assessments`必填：

- `claim_id`：已锁定ID。
- `assessment_state`：上表四值之一。
- `finding`：上表规定的值或显式null。
- `check_ids`：对应法律比对ID；允许部分比对存在，但不自动构成完成。
- `observation_ids`：相关文本观察ID，不计入法律子结论完成数。
- `gap_ids`：影响本子结论的缺口/关系待定项；与gap反向关系完全一致。
- `rationale`：有界结论或未完成原因；不能只写“需人工确认”。

相容性规则：

1. `assessed`不能同时带决定性/关系待定缺口；`requirement_not_applicable`必须在原子问题内，以证据和规则说明要求为何不生效，不能删除该子问题。
2. 同一子问题同时存在已确认决定性缺口与关系待定事项时，状态取`relation_unresolved`，但所有已确认决定性缺口仍独立保留，不能被覆盖或消失。
3. `not_assessed`的gap_ids为空；可以保留确实已做的局部check/observation，但须说明尚未形成该子结论，不能计入完成数。没有开展检查时两个检查数组也为空。若已有决定性缺口或待定关系，必须改用相应状态显式记录，不得藏入“未审”。
4. 漏写一个子问题是**协议错误**。模型明确写`not_assessed`是**如实承认未完成**。程序不得把前者补成后者来制造完整台账。
5. `no_supported_issue`只表示该子问题在给定输入、范围和证据下未发现受支持问题，不表示材料真实、未来履行或整体工程合规。

## 5. 检查项、证据指针与缺口字段

### 5.1 completed_checks必填字段

| 字段 | 规则 |
|---|---|
| check_id | 本响应内唯一 |
| check_kind | text_observation / legal_comparison |
| check | 具体检查名称，不可用comparison代填 |
| document_evidence_refs | 至少一个注册表内的文档证据ID；精确回连原文及定位 |
| legal_chunk_ids | legal_comparison至少一个准入法条；text_observation必须为空 |
| claim_ids | legal_comparison恰好一个锁定子结论；text_observation为空 |
| comparison | 写明观察，或“文件内容—适用要求—相同/差异—判断边界”的具体比对 |

这里建议**一个法律check只对应一个子结论**。同一证据可被多个check复用，但每个check分别给出对应比较，防止把一串claim_ids当作完成证明。此规则属于待审批的新协议，不反向施加到旧结果。

精确绑定与比较文本存在是机器可检查的必要条件；比较是否逻辑充分仍属语义审查，不声称gate能够自动保证。

### 5.2 gaps必填字段

`gap_id`、`kind`、`dependency_key`、`detail`、`task_relation`、`affected_claim_ids`、`reason`、`counterfactual_impact`、`dependency_trigger`、`trigger_refs`、`next_step`。

- `detail`仅表达一种缺失材料。材料类型、任务关系与输出分组不得混用。
- `reason`说明为何需要该材料；`counterfactual_impact`指出具体哪步判断因此无法完成。
- `next_step`提出具体可执行补查，不输出自动废标、中标或最终法律决定。
- `trigger_refs`只能引用已存在`check_id`或文档`evidence_id`；采用带类型对象，不能模糊搜索全文自动猜引用。
- `observed_context_conflict`必须回连被声明为冲突两侧的具体文本。可复用一个含多个来源片段的检查，但必须能解析到两个不同片段；单个孤立引文不满足此表达要求。片段是否真的冲突、何种优先顺序能够消解它们，仍须语义复核；两个ID不构成冲突成立的证明。
- `locked_requirement`绑定可信任务内已有的该claim及该依赖；不能只因“通常需要”就自行生成决定性要求。缺法源时可以诚实记录缺法源，不要求伪造不存在的法律引文。

### 5.3 kind—dependency_key合法组合（延续既有规则）

| dependency_key | 合法kind |
|---|---|
| submission_package_completeness | input_evidence_missing / required_document_missing |
| authenticity | authenticity_unverified |
| actual_performance | future_performance_unverified |
| current_clause_context | input_evidence_missing / required_document_missing |
| applicable_rule | key_legal_source_missing |
| regulatory_applicability | decisive_applicability_missing |
| comparison_operand | comparison_value_missing |
| readability | unreadable_evidence |
| other_undetermined | material_type_undetermined |

`other_undetermined`只能走关系待定，不可作为自动阻断或自动排除的万能类型。

### 5.4 关系、子结论与gate分组

| task_relation | 关联要求 | dependency_trigger | gate分组 |
|---|---|---|---|
| decisive_for_claim | 至少一个需要该依赖的锁定子结论 | locked_requirement / observed_context_conflict | blocking_gap |
| outside_locked_scope | affected_claim_ids为空；任务允许且事前明确排除该依赖；不得有当前子结论仍依赖它 | explicit_scope_exclusion | out_of_scope_item |
| undetermined | 至少一个明确的、可能受影响的锁定子结论；说明待定之处 | locked_requirement / observed_context_conflict / generic_unverified_possibility / undetermined | scope_review_item |

若无法把待定事项关联到任何锁定子结论，不得自动关联全部子结论或改为范围外；返回协议/范围澄清诊断，不作法律U。

允许同一个已拆分的纯材料缺口影响多个子结论，但须逐项验证依赖。同一事项混有当前承诺文本和后续实际履行时，必须由模型明确拆开；程序不做语义拆分。

## 6. 第二层：整体问题完成度

令n为事前锁定必审子结论数，a为通过结构、引用、关系检查且声明`assessed`的个数。n必须大于零。

| question_completion | 派生条件 | 解释 |
|---|---|---|
| complete | 前置处理有效，且a=n | 所有必审子问题均提交有界判断，仍待人工复审 |
| partial | 前置处理有效，且0<a<n | 部分子问题有界完成，其余状态逐项列出 |
| none_completed | 前置处理有效，且a=0 | 没有已完成子结论；可能已有有用观察或真实缺口清单 |
| null | 技术失败，或结构、引用、范围绑定、关系自相矛盾 | 不能可靠计算完成度；显示原因，不把它当法律U |

同时给出`required_claim_count`、`assessed_claim_count`与`completion_reasons`：`decisive_gap`、`scope_relation_pending`、`not_assessed`可并存。`claim_ledger_complete`只表示账目齐全，不等于`question_completion=complete`。

已识别真实缺口可以形成**完整的缺口交接清单**，但不计作已回答该法律子问题。所有子问题都有台账，也不能写成法律任务100%完成。

## 7. 第三层：人工交接状态

按下表从上到下判定，顺序也是规范的一部分：

| 优先级 | handoff_status | 条件 | 人工可见内容与限制 |
|---|---|---|---|
| 1 | unavailable | 传输失败、截断、无法得到完整可解析响应 | 技术失败记录；碎片不作为法律判断 |
| 2 | needs_protocol_repair | 必填/引用/绑定错误、关系矛盾、漏子问题、擅改范围等 | 错误明细及单独标注的可追溯诊断线索；不称为可用法律交接包 |
| 3 | needs_scope_clarification | 结构有效，明确存在undetermined关系 | 已确认信息、已确认关键缺口、待澄清关系并列；不把待定关系计为法律U |
| 4 | ready_for_complete_review | 完成度complete，无上述问题 | 全部有界子结论、依据、定位及建议，等待人工复审 |
| 5 | ready_for_bounded_review | 完成度partial/none_completed；无上述错误；至少存在精确定位观察/比对或有效决定性缺口及可执行补查 | 只交接已支持的局部信息与未决清单；不得给整体无问题结论 |
| 6 | not_ready | 有效地承认尚未审查，但没有可交接的实质信息 | 返回未完成原因，不制造缺口或法律结论 |

`ready`的定义仅为**达到事先规定的呈现与交接条件**。是否准确、是否帮助专家、是否节省时间，必须另行评价。它绝不能直接充当联合交接有效率的分子。

若一个协议错误只涉及部分内容，第一版候选仍采用整条问题级fail-closed：完成度null、交接需修复。其他可核对信息可以作为诊断显示，但不做“部分自动挽救成功”。以后如研究分片放行，须单独设计与审批。

## 8. 不可削弱的四类守护

| 守护 | 必须拦截 | 可以改善的表达 | 禁止的修复 |
|---|---|---|---|
| G1 冲突证据显式绑定 | 声称观察到冲突，却没有有效指针，或指针不存在、跨输入、缺少双侧片段；语义相关性另审 | 模型明确引用已有check/evidence，减少重复抄写 | 程序从任意已有引文猜一个指针 |
| G2 决定性依赖不能被交接能力覆盖 | 子结论标为assessed，却同时有影响它的决定性缺口 | 子结论阻断，整体未完成，但可交接局部观察/缺口 | 为了交接改成不关键、改N、删除缺口 |
| G3 必审子结论逐项记账 | 漏写、重复、未知子结论；空缺口被当作完成证明 | 明确声明not_assessed，保留任务未完成 | 自动补claim_ids或生成未做的比较 |
| G4 禁止未经授权缩窄范围 | 把已锁定必审依赖排除；泛化“只看文字”改变问题 | 在原子问题内证明要求不适用；否则保留未决 | 把必审事项搬到范围外、以低风险代替无依赖 |

真实性、提交完整性、实际履行只在事前锁定范围允许时才可排除；当前任务若正是核验实际提交，不适用文本任务的排除规则。

## 9. 与U/N/R及旧版本的关系

三层状态不替代事实/法律判断，而是说明判断的范围与可交付性。保留每条历史原始U/N/R和原gate结果，不重新编码历史分数。

- 存在有效决定性缺口：保留“该子结论未能完成”的有效U语义；整体不能因为可交接而显示N。其他子结论已发现的受支持风险仍并列展示，不被单一U遮蔽。
- 单纯协议失败、范围关系待定、未审、截断：分别显示处理/范围/任务/技术状态，不混入有效法律U计数。
- 子结论已有风险候选且其依据充分：该子结论可标assessed；“完成”不要求结论是N。
- 一项no_supported_issue不能代替整个问题的N；局部文本观察不能代替法律比对。
- 不新增自动U→N回填器。若下游强制要求单一旧标签，本候选采用不兼容时停止该输出/指标的方式，不能猜测映射。兼容层应另行审批。

新协议不能无损迁移旧响应：新增台账、证据关系必须由新响应显式给出。旧数据最多作为只读失败诊断/守护来源，不得回填成新版原始输出。

## 10. 单一规范及机械规范化设计

审批后建议以一个规范源同时管理：字段/枚举、任务映射、kind—dependency组合、关系相容表、三层派生优先级、规范化白名单、错误码与对应守护案例。生成Prompt说明、schema、gate规则表、输出字典和测试约束，禁止分别手写两套状态规则。

涉及精确引文绑定的规则可调用已有确定性校验函数；自然语言法律充分性仍不可宣称由schema证明。规范至少给每条规则标注`rule_id`、检查阶段、读取字段、失败原因及安全测试ID。

仅允许已登记的字段别名及无歧义枚举大小写/空白规范化。别名与正式字段同时存在且冲突时停止，不择优覆盖。不允许：

- 生成新check、claim、gap、trigger引用或实质结论；
- 重新分类依赖/关系、删缺口、修法律引用或改输入；
- 把缺失的新协议台账从旧响应推断出来；
- 修改文本或定位以让引用校验通过。

独立保存原始响应hash、原始协议检查结果、规范化操作列表、规范化后结果及gate派生状态。原始字段合格率、规范化后字段合格率、关系有效率和交接呈现条件满足率分开报告。

## 11. 合成示例与离线守护计划

详见同目录`SYNTHETIC_EXAMPLES_AND_GUARDS.md`。所有“规范”均为虚构测试规则，不是真实法律指导。示例为语义结构示意，不是可直接提交现行runner的JSON。

后续最小顺序（均未在本轮执行）：审批设计→实现独立候选及同源生成→零API合成正反例→检查输出消费者与指标口径→另行决定是否线上验证。

冻结控制变量：不同时改输入、检索、法源、上下文、模型参数、材料识别候选开关或参照。旧响应不能填字段进行伪配对；实现级离线测试使用预先构造的新协议fixture，不称为LLM生成质量改善。

## 12. 成功标准与研究边界

首轮实现验收的优先级：

1. 四类负例全部保持阻断；预设守护中不当完整放行数为0，真实关键缺口被静默删除数为0。
2. 每个锁定子结论有且仅有一个记录；遗漏被明确拦截。合法部分交接不得将整体升级为完成。
3. 合法证据ID复用能够解析；无指针、错指针、循环引用和未准入法律证据不能放行。
4. 真实缺口、未审、范围待定、协议失败和技术失败在JSON、Markdown、Excel及统计读取中不互相混淆。
5. 原始/规范化结果分离，历史响应和参照hash不变；新协议未经验证不得自动上线。

这些是待执行的软件验收目标，不是本轮结果。通过后也只能说明所测约束符合设计，不能据此宣称总体法律准确率、专家一致率、Recall@5、MRR或人工成本改善。

后续如评价交接质量，应由独立人工判断：已支持信息的可用性、缺口必要性、行动可执行性、证据定位正确性和遗漏风险。保留全部失败分母，分项目/任务范围报告；不以N占比上升、U占比下降或`ready`数量上升作为成功定义。

## 13. 审批范围

本稿请求审批的是状态定义、权限分工、四类守护及零API验收计划。批准此稿不自动批准线上调用、生产替换、旧评价重算、材料识别候选开关启用或新法律结论。
