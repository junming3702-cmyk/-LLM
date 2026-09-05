# Law Source Manifest｜Model Phase 2（四层法规知识库）

**状态**：已按用户审批确定为“四层法规库为主、国家法律法规数据库为 fallback、外部结果必须人工确认”。本轮已完成升级文件识别、机械抽取和 RAG 语料索引准备；条款效力、版本和具体适用性仍须人工核验。

**发布包路径**：phase2_public/data/law/；原始本地根目录不随本公开包发布。

## 层级定义

### Level 1｜Primary Sources / 法律

- `Level 1 （law)\中华人民共和国招标投标法_20171227.docx`
  - SHA-256：`A1FD6EB6F87C529AD5A569669EA2AE7DE84ABB025F4E892595B4ACA788EE85F4`
  - 本地条文主文本；另保留国家市场监督管理总局 HTML 副本用于版本核验。
- `Level 1 （law)\中华人民共和国建筑法_20190423.docx`
  - SHA-256：`93720F2908DF78B4CD50F8BEA626FBFA5D8295A3A6742B4B18B08266749315E8`
  - 本地条文主文本；2019 年修正依据需继续与全国人大官方资料核验。

### Level 2｜Administrative Regulations / 行政法规

- `Level 2\中华人民共和国招标投标法实施条例_20190302.docx`
  - SHA-256：`96A42D91F34D1FF6CA1DE530C17E724C9BFC8C5F880705F3848F8B29C17E73CA`
  - 作为独立的行政法规层参与检索，不再称为“secondary verification source”。

旧文件 `Level 2\电子招标投标办法最终稿.doc` 仍保留在本地，但已识别为同名 Level 3 DOCX 的过时重复版本，**不进入 RAG 索引**。

### Level 3｜Departmental Regulations / 部门规章及相关国家级规范

- `Level 3 (Departmental Regulations)\必须招标的工程项目规定.pdf`
  - SHA-256：`A7E9BA76E5179DFBA76686808756664D23C490D0C8B796736E87704083A36628`
- `Level 3 (Departmental Regulations)\电子招标投标办法最终稿.docx`
  - SHA-256：`27F0809A6EF5079C8AAC1C1C0F346D23B9AEBC358885A28528749437C3377DC1`
  - 已从旧式 `.doc` 升级；抽取 67 个条文/结构块，作为电子招标投标法规主来源候选。
- `Level 3 (Departmental Regulations)\技术规范发布稿.docx`
  - SHA-256：`5DFE1209B5E6DE457471E6BBDD3AC8649B5BA54279276FD53416CDED14225813`
  - 已从旧式 `.doc` 升级；抽取 61 个结构块，作为 `电子招标投标办法` 的**补充性技术文件**进入 RAG。它的角色是 `supplementary_document`，不与法规主条文赋予同等证据权重。
- `Level 3 (Departmental Regulations)\房屋建筑和市政基础设施工程施工招标投标管理办法-文字版.odt`
  - SHA-256：`314CB4F7CE2E0EEE63394A256BECD9C131268E9F40E99C2277951F9F05DE357F`
  - 作为当前可读正文版本，抽取 61 个条文/结构块；同名 DOCX 只有标题和发布信息，已排除索引。
### Level 4｜Local Regulations and Standard Documents / 地方性法规及标准文件

- `Level 4 (Local regulations and standard documents)\四川省建筑管理条例_20210929.docx`
  - SHA-256：`5672F78D7BA4E31D4CBB06F2E34F3A199CC4765F858B1E232E1B721BA8A19778`
  - 仅在合同或项目上下文确认工程所在地及适用范围后加入检索上下文。

### S｜Technical Standards and Practice Materials / 技术标准与应用实务材料

该通道与 Level 1–4 法律层级并行，不把技术标准或实务材料强行归入部门规章。其用途是补充检索、技术交叉核对和候选问题发现，不能自动产生独立法律结论。

- `Level 3 (Departmental Regulations)\GB_T50500-2024_建设工程工程量清单计价标准.pdf`
  - SHA-256：`86223FE842088D3ABBF57B2BC4DB5AC9001C3F783A1FDA0C6CB3B9C6778999F8`
  - 重新定位为 `S2 / standard_application_practice_material`：文件实际标题含“应用与实务”，前言显示其由湖北省住房和城乡建设领域相关单位组织编写，并包含条文解析、案例和本地化实践内容。
  - 当前文件不是已核验的 GB/T 50500—2024 官方标准原文。它只能进入 `warning` 检索分区并标记为 `supplement_only`，不能作为独立法律依据、废标依据、合同无效依据或最终法律意见依据。
  - 如未来获得并核验正式 GB/T 50500—2024 文本，应建立新的独立 source record，不得与本应用实务材料合并。

## Verification sources（独立于四层效力等级）

- 国家法律法规数据库：<https://flk.npc.gov.cn/search>
- 中国人大网、政府部门官方发布页及公报：用于核验文本版本、制定机关、公布日期、施行状态和修正信息。

外部结果只能作为 `external_source` / `verification_candidate` 进入候选证据，必须记录 URL、标题、制定机关、有效状态、检索时间、片段和哈希，并经人工确认后才能用于最终报告。外部检索不是第五个法规层级。

## RAG evidence roles

| Role | 含义 | 默认处理 |
|---|---|---|
| `primary_candidate` | 四层本地法规库中的可读候选来源 | 可参与主检索，但版本/效力仍需核验 |
| `supplementary_document` | 技术规范等支撑性文件 | 可召回，必须保留“补充文件”标签 |
| `practice_material_only` | 标准应用、实务解析或案例材料 | 仅作 `supplement_only`，不得作为独立法律依据 |
| `verification_pending` | 来源身份、版本或效力仍待核验 | 可进入警告分区，不得直接作为确定性法律依据 |
| `verification_copy` | 官方网页本地副本 | 用于版本交叉核验，不能替代层级字段 |
| `superseded_legacy_duplicate` | 已被升级文件替代的旧式重复文件 | 排除索引 |

每个可检索块必须保留 `normative_level`、`normative_type`、`source_role`、`title`、`article`、`source_locator`、`local_file`、`file_hash`、抽取状态和人工核验状态。若不同层级来源发生冲突，模型只能并列呈现冲突证据并标记 `requires_human_legal_review`，不能自行宣布法律效力结论。
