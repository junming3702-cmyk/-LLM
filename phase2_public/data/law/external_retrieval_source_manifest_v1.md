# External retrieval source manifest v1

**状态**：独立来源清单已建立；尚未接入 BM25、embedding 或 LLM 运行链路。

## Scope

本清单与四层本地法规库分开维护。它登记的是外部发现、版本核验和补充资料来源，不改变本地法规库的四层结构，也不自动赋予外部结果法律效力。

## Current policy

1. 本地四层法规库仍是可复现检索的主语料。
2. 国家法律法规数据库是优先外部 fallback/verification candidate。
3. CECN 目前仅是待核验的行业信息候选，不能作为法律依据唯一来源，也未在 BM25 sanity test 中调用。
4. 所有外部结果必须记录来源标题、制定/发布机关、效力状态、公布/施行日期、URL、检索时间、原文片段和内容 hash，并经过人工确认。
5. 外部来源清单的建立不等于外部检索已经执行。

## Decision on the 100-example expansion

将外部检索试验扩展到 100 个例子不是当前本地 embedding/hybrid retrieval 对比的前置条件。当前 60 条 final synthetic gold 已足以比较本地 BM25、向量检索和 hybrid ranking。

100 条外部检索样本应作为独立的 external fallback evaluation set，至少在以下条件满足后再建立：

- 外部检索调用链已经实现并能保存可复现的来源记录；
- 国家法律法规数据库的检索、详情和下载流程已经验证；
- CECN 的域名身份、内容性质和权威角色已经人工确认；
- 样本能够覆盖本地命中、本地无匹配、版本不确定、地方来源缺失、来源冲突和外部结果不可用等触发类型。

因此，本阶段先不把 100 条外部样本与本地 embedding/hybrid 结果合并统计；仅保留其为后续专项评估目标。
