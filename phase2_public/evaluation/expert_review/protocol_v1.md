# 专家盲评研究方案草案 v1

## Material Passport

- Origin Skill: experiment-agent
- Origin Mode: plan
- Origin Date: 2026-09-04T20:40:02+08:00
- Verification Status: UNVERIFIED
- Version Label: study_protocol_v1

## Study Overview

- **Title**: 基于三个真实招投标项目的证据驱动 LLM/RAG 合规预审专家盲评
- **Research Question 1**: 多名招投标专业人员对真实审查单元的合规类别和法规依据能达到何种一致性？
- **Research Question 2**: 冻结后的 LLM/RAG 输出与专家共识在结论、法规证据和弃权判断上有多大一致性？
- **Research Question 3**: 模型错误是否集中在专家低置信度、跨文件证据不足、地方适用性或 supplement-only 单元？
- **Design**: observational, two-stage blinded expert assessment
- **Type**: structured professional review

## Participants

- **Target Population**: 具有招投标评审、造价、采购、工程法规或建设项目合规经验的专业人员
- **Sampling Strategy**: purposive sampling；记录专业领域和经验年限但使用匿名 Expert ID
- **Target Sample Size**: 最低 3 名，优先 4 名。60 个审查单元为固定项目内评估规模，不以专家人数替代独立真实项目数量。
- **Inclusion Criteria**: 成年；具备可说明的相关专业经验；能够独立完成中文法规与招投标文件审查
- **Exclusion Criteria**: 参与过被评项目并能识别项目当事方；无法独立评分；未完成知情同意

## Review Units

- 三个项目各 20 条，共 60 条；
- 24 条既有 discovery units + 36 条按预设类别补提的 coverage/control units；
- 不按模型风险结果决定新增单元是否纳入；
- 每名专家看到相同单元，但使用单独的可复现随机顺序。

## Phase 1 — Independent Blind Rating

专家获得：脱敏项目上下文、原文摘录、source locator、统一法规库/官方数据库入口、审查问题。

专家看不到：模型结论、模型检索结果、风险标签、模型置信度、其他专家评分。

记录：三分类结论、法规名称/条款、证据定位、事实充分性、置信度 1–5、风险程度和简短理由。

## Phase 2 — AI-Assisted Reassessment

仅在 Phase 1 提交并锁定后展示冻结的模型结论、法规证据与建议。专家记录：

- `accepted / revised / rejected`；
- 法规证据是否支持结论；
- 是否存在错误适用或遗漏；
- AI 输出对复核是否有用（1–5）；
- 修改后的最终结论与理由。

Phase 2 不能覆盖 Phase 1 原始评分；两份记录分别保存。

## Analysis Strategy

| 分析目标 | 指标 | 备注 |
|---|---|---|
| 专家间结论一致性 | Krippendorff’s alpha（nominal）+ Fleiss’ kappa | 同时报告百分比一致率；不只报告单一一致率 |
| AI 与专家共识 | macro-F1、逐类 precision/recall、Cohen’s kappa、混淆矩阵 | 共识由多数规则与独立 adjudication 形成 |
| 法规证据一致性 | exact article match、law-level match、evidence Recall@5 | 专家引用标准化为法规 ID + 条号 |
| 弃权质量 | abstention rate、selective accuracy、coverage-risk | 区分合理弃权与遗漏证据 |
| Phase 2 影响 | 结论变化率、accepted/revised/rejected 分布 | Phase 1 与 Phase 2 配对比较；不把变化自动解释为改善 |
| 不确定性 | bootstrap 95% CI | 以 review unit 为重采样单位；按项目分层敏感性分析 |

Discovery stratum 与 coverage/control stratum 必须分开报告，再提供合并结果；否则模型辅助选题造成的风险富集会夸大风险检出表现。

## Ethics

- **Current status**: ETHICS_PENDING / institutional determination not yet obtained
- **Consent Method**: 待制定书面或数字知情同意；必须说明研究目的、时间投入、退出权和数据用途
- **Data Anonymization**: 专家使用随机 ID；去除姓名、单位和直接身份信息；项目文本继续脱敏
- **Data Storage**: 待用户确认安全存储位置、访问人员和备份方式
- **Retention Period**: 待确定
- **Risk**: 主要风险为专业声誉或意见可识别风险；结果不得归因到具体专家或雇主
- **Hard gate**: 未明确机构伦理审批/豁免要求前，不招募专家、不收集评分
