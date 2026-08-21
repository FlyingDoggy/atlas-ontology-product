# 新 Ontology Solution 构建与交付 Playbook

日期：2026-08-21  
适用版本：Atlas Ontology Analytics `0.15.0`  
适用对象：Solution Builder、业务/指标 Reviewer、Data Reviewer、Release Manager、Agent Operator

## 1. 这套流程解决什么问题

本 Playbook 用于把一个新的业务分析场景，从“只有需求说明、指标逻辑、数据字典、样例数据和既有 SQL”推进为：

1. 可追溯的来源材料；
2. 待人工确认的 Ontology 候选；
3. 结构化、可验证的 Canonical Draft；
4. 不可变的语义版本；
5. 经数据绑定和控制案例认证后可供 Analytic Agent 使用的运行版本。

核心原则只有三条：

- 自动化负责整理、提取、对齐、提示冲突和生成候选；人负责业务事实、口径和发布决定。
- 每条进入 Draft 的内容必须能回到来源、确定性推导、人工决定或显式 synthetic/assumption 记录。
- “能构建 Ontology”与“能在 Agent 中正确计算”是两道门。后者还需要可执行 adapter、数据 binding 和 control suite。

## 2. 最小输入包

一个新场景优先收集以下五类材料；没有的内容不补写成客户事实，而是记为 `MISSING`、`ASSUMED` 或 `SYNTHETIC`。

| 材料 | 最低内容 | 首版处理方式 |
|---|---|---|
| 需求与业务流程 | 用户、触发条件、端到端分析步骤、问题清单、期望输出、边界 | XLSX 或安全转写文本；形成 Requirement Candidate |
| 指标逻辑 | 名称、业务定义、公式、分子/分母、粒度、维度、单位、时间窗口、排除条件 | XLSX；形成 Metric/Rule Candidate |
| 数据模型 | 表/实体、主外键、关系、字段所属业务对象 | XLSX；形成 Object/Property/Link Candidate |
| Data Dictionary 与 metadata | 字段类型、业务含义、枚举、单位、nullability；可选 sample | XLSX；形成 Property/Mapping/Consistency Candidate |
| 已有 SQL/计算逻辑 | 来源表、join/filter/group、计算表达式、异常处理 | `.sql` 或安全转写文本；形成 SQL Observation/Rule Candidate |

图片或扫描件可以作为“材料存在”的证据，但如果不能生成 exact page/cell/text anchor，系统必须显示 `UNSUPPORTED`，由团队转写后再进入构建。首版对 XLSX 和安全转写文本承诺精确锚点；其他格式逐项验收后开放。

## 3. 产品内操作流程

### 3.1 新建 Solution

1. 进入 `Ontology Studio → 全部解决方案`。
2. 选择 `新建解决方案`。
3. 当前可用路径选择一个已安装模板，填写中英文名称、场景说明和负责人。
4. 系统分配新的 `solution_id` 与 `workspace_id`，并跳转到该 Solution 的六模块工作区。

模板复制 semantic/data/experience/control 的 Canonical 起点；已安装模板的 immutable seed input refs 可以供首次构建读取，但不会复制成新 Solution 自己的 Source Library 所有权、上传历史。construction runs、candidate/review history、release 和 active pointer 也不会继承。这是案例隔离，不是数据丢失。

当前 `Blank` 和 `Import package` 入口明确不可用；不要绕过 UI 手工伪装成已支持能力。

### 3.2 登记和版本化来源材料

在 `输入与证据 → 来源材料`：

1. 上传文件或粘贴安全转写文本；
2. 选择材料类别并填写说明；
3. 核对文件名、checksum、版本和处理状态；
4. 替换材料时创建新版本，不覆盖旧 bytes；
5. 在启动构建前勾选本轮 exact source set。

系统将 source bytes 存入 S3/MinIO exact version，将 metadata、状态与索引存入 PostgreSQL。旧 Run、Decision 和 Release 始终引用旧 exact ref。

### 3.3 启动自动构建

在 `输入与证据 → 构建运行`：

1. 确认选中的 source set；
2. 点击 `开始自动构建`；
3. 任务进入 durable queue，离开页面不会取消；
4. 查看来源结算、结构化提取、语义候选生成和候选预检四阶段 receipt；
5. 失败或不支持的材料必须有明确 terminal status，不能用空结果冒充成功。

Construction Engine 可以调用隔离的 Semantica worker 和 Qwen，但输出只能是 immutable Candidate Bundle。它不能修改 Draft、不能形成业务事实、不能发布，也不能激活 Agent。

### 3.4 人工复核候选

在 `质量与治理 → 复核中心`：

1. 按类型、风险和 compile eligibility 过滤候选；
2. 打开右侧 Inspector，核对定义、来源锚点、支持等级、canonical target 和限制；
3. 对每项选择：
   - `ACCEPT`：内容正确，可按建议进入 Draft；
   - `EDIT`：修改后进入 Draft；
   - `REJECT`：明确不采用并保留原因；
   - `DEFER`：本轮不决定，并声明是否阻断后续发布；
4. 先保存复核进度；
5. 全部 item 有 disposition 后，点击 `完成本轮复核并应用`。

只有最后一步才使用 expected-revision CAS 原子写入新 Draft。模型置信度只用于排序，不能代替 Review Decision。Metric、Formula、Mapping、Join、Conflict、Assumption 和 Unsupported 项不得通用批量接受。

### 3.5 维护语义与数据模型

在 `语义模型` 与 `数据` 模块完成结构化修改：

- 业务模型：对象、属性、事件和关系；
- 指标与规则：指标目录、公式、粒度、单位、维度、边界和依赖；
- 知识图谱：Canonical Graph 与待复核 Candidate Overlay，支持搜索、类型过滤、单跳影响分析、新建/修改/弃用对象与关系；
- Agent 体验：问题族、工具、回答义务和可展示分析；
- Schema 与 Mapping：来源表、字段、类型、枚举、join 和 semantic mapping；
- Sample/Control：content-addressed Parquet 和确定性控制数据。

List、Table 与 Graph 必须编辑同一个 Draft revision；Graph 是读写界面，不是独立权威图数据库。RDF/OWL/JSON-LD/SHACL 是派生交换或验证投影，不覆盖 Canonical package。

### 3.6 验证、发布与 Agent 交付

1. 在 `质量与治理 → 验证结果` 对 exact Draft revision 执行 schema、语义、mapping、control、mutation 和 release-readiness 检查；
2. 任何 Draft 修改都会让旧 validation 失效，必须重跑；
3. 在 `版本与发布 → 版本` 查看 exact diff，只发布被批准的 exact digest；
4. 发布生成不可变 semantic release，不自动切换 Agent runtime；
5. 在 Delivery/Agent Control 完成数据 binding、adapter compatibility、control certification、prepare 和 activate；
6. 激活失败时旧 Active 继续服务；成功后 Agent 才消费新版本；
7. Agent 识别出的语义问题通过 typed Semantic Change Request 回到 Studio，不能自动改 Ontology。

## 4. 自行补齐材料时的记录规则

在等待客户确认期间允许为了 Engineering Demo 继续推进，但每一处矫正、假设或编造必须落入以下 ledger，不能藏在代码、prompt 或口头说明中。

| 字段 | 说明 |
|---|---|
| `record_id` | 稳定唯一 ID |
| `solution_id` / `revision` | 影响的 Solution 与 Draft |
| `record_type` | `CORRECTION / ASSUMPTION / SYNTHETIC_SUPPLEMENT / MISSING / CONFIRMATION_REQUEST` |
| `original_observation` | 客户材料原文或 exact anchor |
| `normalized_value` | 例如 `canceled → cancelled`；只做明确机械归一化 |
| `proposed_content` | 假设或 synthetic 补充内容 |
| `reason` | 为什么必须补、依据是什么 |
| `impact` | 影响对象、指标、mapping、control 或 Agent 答案 |
| `support_class` | `DIRECT_EXACT / DERIVED_DETERMINISTIC / REVIEWER_AUTHORED / SYNTHETIC / MISSING` 等 |
| `status` | `OPEN / ACCEPTED_FOR_DEMO / CONFIRMED / REJECTED / SUPERSEDED` |
| `owner` / `reviewer` / timestamps | 谁提出、谁确认、何时变更 |

规则：

- 明确拼写、大小写、空白和枚举格式归一化可以记录为 `CORRECTION` 后自行处理；
- 业务口径、字段含义、公式方向、时间窗口和排除条件不能当作“拼写修正”；
- synthetic sample/control 必须与客户事实分层存储和显示；
- 客户确认返回后，新证据形成新 revision，不回写篡改旧决策记录；
- 面向 Deloitte HK 的补充/确认清单持续维护，即使开发不等待回复。

## 5. 新案例需要多少定制开发

### 5.1 不需要改公共产品代码的情况

如果新案例只使用已支持的 primitive：

- 已支持的来源格式和锚点；
- Object/Property/Event/Link；
- 已登记 Formula AST/operator、时间、单位、维度和 aggregation；
- 已支持的 mapping/join；
- 已有 Agent question/tool/answer obligation 类型；
- 可用的 data adapter 与 control harness；

则新增工作主要是上传材料、复核候选、配置 package/binding/control，不复制 Studio 或 Agent 产品。

### 5.2 必须开发 capability 的情况

遇到以下任一项，Construction Run 应输出 `MissingCapability` 或 compile-ineligible candidate，并 fail closed：

- 新文件格式无法产生 exact anchor；
- 新公式/operator、窗口、population 或单位语义；
- 新 join/mapping 类型；
- 新 data source connector 或执行引擎；
- 新的分析工具、因果/归因逻辑或 answer obligation；
- 新 control/oracle 类型；
- 当前 Agent adapter 不能确定性执行该场景。

开发新 capability 时按纵向切片交付：public contract → parser/compiler/adapter → Studio authoring/review → validation/control → runtime execution → release evidence。禁止只加页面或只改 prompt。

## 6. 新案例发布门

每个新案例至少满足：

- source set exact version、checksum 和 processing status 完整；
- assumptions/corrections/synthetic/missing ledger 无隐藏项；
- construction run terminal、无 partial bundle、stale 结果未应用；
- candidate denominator 与 Review disposition denominator 一致；
- Canonical Draft 可重建，List/Table/Graph 对同一 revision 一致；
- schema/semantic/mapping/control/mutation validation 绑定 exact digest；
- supported、boundary、clarify/refuse/failure case 均有控制证据；
- immutable release 与 runtime binding 分开；
- prepare/certify/activate 失败不影响旧 Active；
- Agent answer 只引用本次 active snapshot 的 claims/evidence；
- 回滚、审计和变更请求可执行；
- 对外声明准确，不把 synthetic demo 说成 HKEX 业务验证或生产就绪。

## 7. 当前版本的诚实边界

`0.15.0` 已证明：ADT 与 Cash Trading 两个案例共用同一 Studio、Construction Engine、PostgreSQL/S3 持久层、Review、Graph、发布/激活骨架；模板创建的隔离新 Solution 可以完成来源驱动的自动构建和人工复核，而无需修改公共产品代码。

它没有证明：任意客户文档都能零配置自动变成正确 Ontology；任意新业务都已有可执行 adapter；Semantica/LLM 输出可以越过人工和确定性验证；当前 Quick Tunnel 具备永久域名或 SLA；当前内容已经得到 HKEX 业务确认。
