# Plan: Semantica 融合后的 Ontology Studio 产品迭代

> Source design: `ontology-product-group/18_semantica_integrated_ontology_studio_architecture.md`
>
> Status: Approved Implementation Baseline — 已完成一轮三视角 adversarial review；Product Decision Owner 于 2026-08-21 批准实施，并明确将完整 Graph Editor 纳入本轮范围。
>
> Review basis: `ontology-product-group/reviews/semantica-studio-iteration-adjudication.md`
>
> 目标：保留现有 Studio 与 Agent 产品骨架，补齐从企业材料到可执行 Ontology Solution 的自动构建、集中 HITL、完整编译与发布闭环。

## 1. 结果定义

迭代完成后，一名 Solution Builder 应当可以：

1. 新建或打开一个 Ontology Solution；
2. 添加需求、指标、数据模型、数据字典、SQL 和补充说明；
3. 点击“开始自动构建”，离开页面后任务仍可继续；
4. 在同一个 Review Center 中处理系统识别的对象、关系、指标、数据映射、公式、冲突、假设和缺口；
5. 在结构化工作台中补充或修改模型；
6. 运行确定性验证和控制案例；
7. 查看 exact diff，并发布不可变的 Ontology Version；
8. 在 Agent 侧完成绑定、认证、激活和分析；
9. 将 Agent 的语义变更请求带回 Studio 形成下一版 Draft。

首条完成链使用 ADT；在公共 Candidate/Compiler 合同冻结前，使用预登记的 materially-different 第二案例做最小 falsifier。完整 Blank/Template onboarding 与同一 frozen build 的双案例 clean run 放在后段。第二案例出现 `MissingCapability` 是合法且有价值的结果，不能为了“证明通用”而现场扩 schema 把 gate 做绿。

产品术语固定为：

- **Ontology Solution**：一个业务场景工作区，例如 ADT 或 Listing；不再使用含混的 “Case Set” 指代它；
- **Control Suite**：用于验证某一 capability 的 exact、冻结控制案例集合；它不是 Ontology Solution，也不是一个独立用户产品。

## 2. 当前基线与差距

### 2.1 已经存在，必须保留或扩展

- React 19 + TypeScript + Vite 产品前端；
- Solution Directory：新建、模板复制、编辑元数据、切换、归档、恢复和删除；
- 六个 Studio 一级菜单和稳定路径；
- ADT 与 Cash Trading 两个登记 Solution；
- PostgreSQL 17 + S3/MinIO authoritative state/artifact 基线；
- Workspace head、revision、expected-revision CAS 和 revision artifacts；
- typed package operations 与实体/Link 编辑能力；
- 当前五槽位 Qwen observation → accept/edit/reject → draft revision tracer；
- semantic validation、SHACL regression、ADT control/golden cases；
- immutable release、Agent prepare/certify/activate/verify/rollback；
- Agent → Studio Semantic Change Request；
- 当前测试基线：210 个 Python tests 可收集，45 个前端 tests 通过，React production build 通过。

### 2.2 真实缺口

- 当前 intake 主要是预登记材料，没有通用来源上传、版本、预览和加工任务；
- Semantica 尚未进入代码或部署；
- 当前 LLM observation 是 ADT 固定 slot，而不是多类型 Candidate Bundle；
- ADT 与 Cash Trading 仍有各自的 workspace model，通用 workspace 尚未完全收敛；
- 没有 durable Construction Run、阶段进度、取消、重试和 stale-result 处理；
- 没有从 Semantica raw output 到 canonical contracts 的 Analytic Case Compiler；
- Review 页面只能处理少量固定 observation，不能处理批量候选、冲突、假设和高风险映射；
- Semantic Model 主要是列表/表单，缺少可用的图谱浏览、来源定位和影响分析；
- Data 页面没有完整的 Schema、mapping、Join、sample/enum 构建工作流；
- question family、tool、answer obligation、Dashboard 和 control 的 Studio authoring 不完整；
- typed JSON 编辑器仍承担过多专家操作，不适合作为主要产品入口。
- 当前 Solution route 对 ADT 存在隐式默认，context 丢失时有编辑错 Solution 的风险；
- 当前 review 默认 ACCEPT，且 Draft patch 与 Decision 写入存在双写崩溃窗口；
- Semantica 的高层 pipeline success、parser anchor、cancel 和 dedup 语义不能直接当作产品权威。

## 3. 用户与用户故事

### 角色

- **Solution Builder**：整理材料、启动构建、维护 Draft；
- **Business/Metric Reviewer**：确认业务定义、指标口径和边界；
- **Data Reviewer**：确认 Schema、字段映射、Join、SQL observation 和样例；
- **Release Manager**：查看 exact diff、确认验证结果并发布；
- **Agent Operator**：在 Agent 域完成 runtime binding、认证、激活和回滚。

当前共享 Demo 账号可以由一个人扮演多个角色，但产品动作与记录保持区分；本轮不建设企业 IAM。

### 用户故事

- **US-01**：管理和切换多个 Ontology Solution；
- **US-02**：登记、上传、预览和版本化来源材料；
- **US-03**：启动、监控、取消、重试自动构建；
- **US-04**：查看带来源锚点的候选内容并 accept/edit/reject/defer；
- **US-05**：用列表、图谱和结构化表单维护对象、事件、关系、指标和规则；
- **US-06**：维护数据源、Schema、字段、枚举、mapping 和 Join；
- **US-07**：维护问题族、分析工具、回答义务、Dashboard descriptor 和控制案例；
- **US-08**：运行 validation、处理问题、查看 diff 和发布 exact version；
- **US-09**：把发布版本交给 Agent，并接收 Agent 变更反馈；
- **US-10**：从空白或模板快速构建第二个 Case，而不修改公共产品代码。

## 4. Durable architectural decisions

### 4.1 产品与路由

- 只有 Ontology Studio 与 Ontology Analytic Agent 两个用户产品；Semantica 是 Studio 内部 Construction Engine；
- 全局入口保持 `/ontology-studio/solutions/`；
- Solution 内所有可写路由必须显式携带 `/ontology-studio/solutions/{solution_id}/...`；无效或缺失 identity fail closed，不再静默回落 ADT；
- Solution Workspace 保持六个一级模块：概览、输入与证据、语义模型、数据、复核与验证、版本与发布；
- 前端不把 “Semantica” 暴露成菜单、品牌或需要业务用户理解的术语；正常产品文案使用“自动构建”“候选内容”“来源证据”；
- Studio 和 Agent 在产品 Header 中互相提供深链；Studio 只展示 Agent delivery 状态，Agent Control API 继续拥有 prepare/activate/rollback。

建议稳定子路径（以下 `{solution_id}` 不可省略）：

```text
/ontology-studio/solutions/{solution_id}/overview/
/ontology-studio/solutions/{solution_id}/inputs/requirements/
/ontology-studio/solutions/{solution_id}/inputs/sources/
/ontology-studio/solutions/{solution_id}/inputs/runs/
/ontology-studio/solutions/{solution_id}/semantic/model/
/ontology-studio/solutions/{solution_id}/semantic/metrics/
/ontology-studio/solutions/{solution_id}/semantic/agent-experience/
/ontology-studio/solutions/{solution_id}/data/schemas/
/ontology-studio/solutions/{solution_id}/data/mappings/
/ontology-studio/solutions/{solution_id}/data/samples/
/ontology-studio/solutions/{solution_id}/quality/review/
/ontology-studio/solutions/{solution_id}/quality/validation/
/ontology-studio/solutions/{solution_id}/quality/changes/
/ontology-studio/solutions/{solution_id}/release/versions/
/ontology-studio/solutions/{solution_id}/release/delivery/
```

现有路径只保留只读 redirect/alias；redirect 必须解析出 exact Solution，不能带着隐式 ADT context 继续可写。

Solution 生命周期沿用现有 Directory，但在首个交付 tranche 内冻结复制矩阵：默认只复制模板化 semantic/data/experience/control descriptors，不复制 raw sources、runs、candidates、review decisions、releases 或 active pointer；Archive/Restore/Delete 都先做依赖预检，Restore 不隐式激活。

### 4.2 权威与存储

- Canonical typed package、Workspace Revision 和 Immutable Semantic Release 保持产品权威；
- PostgreSQL 17 保存 Solution、Workspace head、Source metadata、Run/Attempt/lease、Candidate index、Review Batch/Decision、Release intent/index 和 audit events；它是所有 mutable 状态与 terminal outcome 的唯一权威；
- S3/MinIO exact version 保存 source bytes、parsed artifacts、raw Semantica output、Candidate Bundle、canonical revision、validation report 和 release bytes；
- graph、RDF/OWL/JSON-LD、向量与搜索索引全部是 derived read model；第一版不新增权威图数据库；
- sample/control facts 使用 content-addressed Parquet + sandboxed DuckDB；客户事实不进入 Studio 产品库。

### 4.3 Semantica boundary

- Semantica 以 pin exact version 的隔离 worker 运行，不安装进 Studio API 或 Agent runtime；
- worker 通过 product-owned stage adapters 接收 exact input refs 和 Construction Profile；parse、extract、resolve-proposal、projection 各自输出 closed stage receipt；
- LLM 调用必须通过现有 Model Gateway/Qwen 配置，Semantica 不独立持有 API key；
- worker 只能产出 immutable raw result/Candidate Bundle，不能直接写 Workspace head、Review Decision、发布版本或 Agent active pointer；
- Semantica 的 pipeline status、internal ID、confidence、resolved graph、resource scheduler 和 provider fallback 都只是 telemetry/implementation detail，不能决定产品 SUCCESS、candidate identity、证据等级或 canonical merge；
- Semantica upgrade 先进行 ADT old/new shadow diff，再切换 build；
- 初始版本使用 PostgreSQL durable job/outbox + K8s worker polling；不因一个 construction use case 引入 Redis/Celery/Temporal。

### 4.4 Construction concurrency

- 每个 Construction Run 固定 `workspace_id + base_revision/digest + selected source-set digest + profile/stage-build refs`；
- logical Run 与 execution Attempt 分离；每次 retry 创建新的 `attempt_id + lease_epoch`，只有当前 lease 可以通过 PostgreSQL CAS 提交唯一 terminal Candidate Bundle ref；
- 一个 workspace 同时只允许一个 active run，但保留全部历史 run；
- workspace/source 在运行后发生变化时，完成结果标记 `STALE`，不能应用到新 revision；首版要求 rerun，不实现自动 rebase；
- cancel 经过 `CANCEL_REQUESTED`；只有在 commit fence 之前赢得顺序才成为 `CANCELLED`，commit 后使用 discard/archive，不伪装成 cancellation；晚到 Attempt 只能成为隔离 artifact；
- worker 失败不产生 partial Candidate Bundle，也不影响当前 Published/Active version。

### 4.5 HITL 与发布

- 正式人工流程收敛在一个 Review Center；所有新 item 默认 `UNREVIEWED`，系统 actor 不能写 `ACCEPT/EDIT`；item disposition 可持续保存，但只有“完成本轮复核并应用”才以一次 expected-revision CAS 写入 Canonical Draft；
- Review action 是 `ACCEPT / EDIT / REJECT / DEFER`；DEFER 必须声明是否阻塞发布；
- confidence 只影响排序，不能自动产生 confirmed business truth；metric/formula/mapping/join/conflict/assumed/unsupported 不允许通用批量接受；
- final Review Decision、candidate terminal state、新 Draft revision 和 workspace head 在同一 PostgreSQL authority transaction 中提交；exact artifacts 可以预先 stage/read-back，但不能形成第二个权威；
- final validation 绑定 exact revision；任何后续编辑都会使 validation 变为 stale；
- publish 只批准 exact digest；后台构建和 LLM 不得修改已发布 bytes。

### 4.6 Public data models

需要形成稳定、版本化的公共合同：

- `SourceArtifactV1`：材料类型、exact ref、checksum、classification、allowed use、display metadata；
- `ParsedArtifactV1` / `SourceAnchorV1`：exact source/parsed refs、parser build、locator kind、format-specific locator、origin map 与 snippet digest；第一批只承诺实际输入需要的 XLSX 和安全转写文本，其余格式逐个验收后开放；
- `ConstructionProfileV1`：启用的 extractors、模型 profile、输出范围和限制；
- `ConstructionResourceProfileV1`：文件/页/行/单元格/token/node/edge、LLM budget、deadline、CPU/memory/ephemeral storage、并发与 retry 上限；
- `ConstructionRunV1` / `ConstructionAttemptV1`：base revision、source-set digest、stage、status、attempt/lease、timestamps、build/profile refs 和 exactly-one terminal bundle ref；
- `ConstructionCandidateBundleV1`：candidate items、anchors、conflicts、assumptions、missing/unsupported、provenance 和 checksum；
- `CandidateItemV1`：stable occurrence key、revision digest、typed candidate、risk class、`support_class`、generation method/stage receipt、source anchors、impact refs 与 compile eligibility；
- `ReviewBatchV1` 与 `ReviewDispositionV1`：batch revision/digest、item decisions、edited value、reviewer note、blocking status 与 apply intent；
- `CaseCompilationResultV1`：canonical draft operations、unsupported observations、compile report；
- 现有 package/revision/release/runtime contracts 保持，不由上述模型替代。

`support_class` 至少区分 `DIRECT_EXACT / DERIVED_DETERMINISTIC / MODEL_INFERRED / HEURISTIC / REVIEWER_AUTHORED / SYNTHETIC / MISSING`。Semantica dedup/merge 只能输出保留原 occurrence、pairwise score、alternative 和 endpoint 的 proposal ledger；只有人工 merge decision 才能生成 canonical merge operation。

Studio 可以在同一 UI 中管理 Agent Experience 与 Control Suite 的候选和编辑视图，但权威输出保持分离：semantic release、Agent Experience profile、frozen Reference/Control/Suite refs、deployment binding 各自版本化；Studio Delivery 只读展示组合状态，Agent Control 执行 bind/certify/activate/rollback。

## 5. 前端产品与交互方案

### 5.1 设计方向

**具体对象**：面向业务建模师、指标专家和数据分析师的“语义工程工作台”。

**页面唯一工作**：让用户清楚知道自己正在编辑哪个 Solution/Revision、系统从什么材料生成了什么、还有哪些内容需要处理，以及下一步如何进入可发布状态。

当前 palette 与字体有明确产品辨识度，保留而不是重新换皮：

- `Navy #102532`：产品 Header 与稳定上下文；
- `Jade #0B776F`：主要动作和已确认状态；
- `Canvas #EDF2F3` / `Paper #F8FAF9`：高密度工作区；
- `Ink #132731` / `Ink Soft #5B6B71`：正文层级；
- `Signal #D48C32`：待确认与阻塞风险；
- 字体：Manrope + PingFang SC/Microsoft YaHei；ID、版本和 checksum 使用 IBM Plex Mono。

主要改变不是视觉换肤，而是信息结构：

- Studio 不再使用大 Hero、海报式大标题和长瀑布页面；
- 固定产品 Header + 左侧一级导航 + 页面内二级导航；
- 主区承载列表、表格、图谱或编辑器；只有选中对象时打开右侧 Inspector；
- 同一页面只保留一个主要动作；状态、过滤和上下文不伪装成 Dashboard 卡片；
- 页面标题使用用户语言，不展示内部 contract 名称；exact ID 放在可展开的“技术详情”；
- 当前仅承诺桌面端，设计基线 1280–1600px；1024px 时右侧 Inspector 改为 drawer。

**产品签名元素**：Evidence Lineage Summary。在任一候选、对象、指标、mapping 或 release 的 Inspector 顶部，统一显示实际存在的链路：

```text
Source versions (n) → Run → Candidate / Decision → Draft rN → Published vX | 尚未发布
```

它不是装饰，而是可点击的证据导航；多来源、冲突、merge、rejected/superseded 分支可展开，没有发生的阶段不得画成已完成。全产品只在这一处使用有方向性的动态过渡；其他页面保持稳定、克制，并尊重 reduced-motion。

### 5.2 应用 Shell

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Atlas | Ontology Studio | Solution switcher | Jobs | Agent ↗ | User │
├────────────────┬─────────────────────────────────────────────────────┤
│ 当前 Solution   │ Breadcrumb / Page title              Draft r12     │
│ 工作/发布/运行版 │ Secondary navigation                               │
│                ├─────────────────────────────────────────────────────┤
│ 概览            │                                                     │
│ 输入与证据      │ Main workspace                                     │
│ 语义模型        │                                                     │
│ 数据            │                                      Inspector →   │
│ 复核与验证      │                                                     │
│ 版本与发布      │                                                     │
│                │                                                     │
│ 全部解决方案    │                                                     │
└────────────────┴─────────────────────────────────────────────────────┘
```

全局 Header 只负责产品、Solution 和跨产品切换；工作区版本与状态固定在 Sidebar Context，不能随着页面滚动消失。

Solution switch、refresh、back/forward、多 tab 都必须保持 route 中的 exact Solution context；找不到、已删除或无权限时显示明确阻断页，不能默认打开 ADT。Jobs tray 显示 Solution 名称与真实服务端状态，避免把不同 workspace 的运行混在一起。

### 5.3 输入与证据

**Sources 页面**

- 表格列：名称、材料类型、版本、处理状态、最近使用、问题数、操作；
- `添加材料` 打开 drawer：上传文件或粘贴安全转写文本，填写材料类型和说明；
- 上传完成后先显示 checksum/版本和 `READY`，不自动启动构建；
- 点击一条材料，Inspector 显示预览、source anchors、使用它的 candidates/objects 和版本历史；
- 替换材料形成新 version，旧 run 和已发布版本继续指向旧 exact ref；
- 第一批 source adapter 只对当前真实输入需要的 XLSX 与安全转写文本承诺 exact anchor；其他格式显示 `暂不支持精确证据定位` 和转写指引，不以近似 page/cell 冒充 exact。

**Construction Runs 页面**

```text
┌ Selected sources ─────────────────────┬ Current / recent run ───────┐
│ ☑ Requirements v2                    │ RUNNING                      │
│ ☑ Metric logic v1                    │ 读取材料                      │
│ ☑ Data dictionary v3                 │ 解析结构                      │
│ ☑ Existing SQL v1                    │ 提取对象与关系  ← current     │
│                                      │ 去重与冲突                    │
│ [开始自动构建]                        │ 生成候选 / 预检                │
└──────────────────────────────────────┴───────────────────────────────┘
```

- 不显示虚假百分比，只显示已完成 stage、当前 stage、处理数量和持续时间；
- 用户可以离开页面，Header 中显示小型 run indicator；返回后从后端状态恢复；
- UI 状态至少区分 `QUEUED / LEASED / RUNNING / CANCEL_REQUESTED / COMMITTING / SUCCEEDED / CANCELLED / FAILED_RETRYABLE / FAILED_TERMINAL / LEASE_LOST / STALE / DISCARDED`；
- running 时可请求 cancel；只有服务端进入 `CANCELLED` 才显示取消完成；失败时显示可操作错误、失败 stage、是否可 retry；
- success 后主动作变为 `查看待复核内容`；stale run 只能查看和 discard/rerun。

### 5.4 Review Center

```text
┌ 风险与类型 ─────┬ Candidate queue ─────────────────┬ Evidence Inspector ─────┐
│ 阻塞发布   3     │ [Metric] Average Daily Turnover  │ 来源片段 / 页码 / 单元格  │
│ 高风险确认 11    │ current: ratio of sums           │ 生成方式与模型/build      │
│ 假设补齐   6     │ conflict: simple avg monthly ADT │ 冲突值与影响对象           │
│ 缺失信息   4     │                                  │ Lineage Strip             │
│ 普通候选  27     │ Accept  Edit  Reject  Defer      │                          │
└────────────────┴───────────────────────────────────┴─────────────────────────┘
```

- 默认首先显示 `阻塞发布`，不按生成顺序平铺；所有 item 初始为 `UNREVIEWED`，不预选 Accept；
- 每条 candidate 必须在不离开页面的情况下看到 exact source evidence；
- Evidence 不能 round-trip 时显示 `APPROXIMATE / UNRESOLVABLE`，并禁止把它标成 source-supported；reviewer 改写了 anchor 未支持的值后，support 自动变为 `REVIEWER_AUTHORED`，除非重新选择证据；
- `Edit` 打开与 candidate type 对应的结构化表单，不要求用户编辑 JSON；
- low-risk items 支持多选与批量 accept/reject，但必须显示选中数量、共同类型/来源/影响及隐藏筛选项；metric/formula/mapping/join/conflict/assumed/unsupported 不允许通用批量接受；
- disposition 即时保存到 Review Batch，但不立即写 Canonical Draft；
- `完成本轮复核并应用` 先等待 autosave，服务端核对 exact Review Batch digest，显示新增/修改/忽略/未决定/blocking defer 数量，确认后一次性 atomic CAS；
- CAS conflict 时不覆盖他人修改，展示“当前 Draft 已更新”，允许查看 diff 后 rerun/review；
- raw response、prompt、API key 和内部异常不出现在界面。

### 5.5 语义模型

- List/Table 与 Graph 是同一 canonical semantic revision 的两种完整视图；任何一边的修改都编译成相同的 typed Object/Link/Event operations，并使用同一个 expected-revision CAS；
- Graph Editor 纳入本轮正式范围，支持浏览、筛选、展开邻居、建立/修改/删除候选关系、创建对象、查看冲突、来源、上下游影响和 exact diff；删除 canonical object/link 必须经过影响预检与显式确认；
- Semantica raw/merged graph 只作为 candidate projection 进入 Review Center。未复核节点和边在图中使用 Candidate overlay 呈现，只有人工 `ACCEPT/EDIT` 并完成 atomic apply 后才进入 canonical graph；
- Graph 布局、坐标、折叠与视觉分组是用户偏好/derived state，不进入 semantic release；节点、边、类型、方向、约束和来源引用才进入 canonical operations；
- Graph 与 List 必须相互深链并保持选择、过滤与 revision 上下文；图服务不可用时 List/Table 仍是完整降级路径，不能阻断编辑、验证或发布；
- 选择对象后 Inspector 展示 definition、properties、links、metrics、source anchors、governance state、下游影响；
- 对象、事件、关系、指标和规则分别使用结构化 editor；原 typed JSON editor 移到“高级/诊断”；
- `指标与规则` 使用表格和 dependency view，明确 grain、population、period、unit、formula、rounding、null handling；
- `Agent 体验` 配置 question family、answer obligation、allowed tools、Dashboard sections 和 evidence presentation，不编辑 system prompt；保存后形成独立 versioned Experience component，而不是偷偷改变 semantic release。

### 5.6 数据

- `Schema` 页面以 source/table/field 层级展示数据模型、类型、枚举和 sample classification；
- `Mappings` 使用三栏工作台：Logical field、Suggested physical mapping、Inspector；不依赖拖拽，支持键盘和明确的 `确认映射`；
- mapping 显示为什么建议、source anchor、类型/单位兼容、影响指标；
- Join 使用可读的 join cards/table + 小型关系图，必须明确 keys、cardinality、grain change 和 unmatched policy；
- SQL 只作为 source observation/对照；系统显示解析出的 filter、join、aggregation 和 formula，用户确认 typed operator，不直接把任意 SQL 交给 Agent；
- `样例与枚举` 管理 synthetic/public sample、枚举字典和 control fixtures，并明确分类和适用范围；Control Suite UI 是现有 exact Reference/Control/Suite manifests 的编辑投影，冻结后任何 denominator/expected/tolerance/fixture/evaluator 变化都必须形成新 version 并使旧 validation stale。

### 5.7 Validation 与 Release

- Validation 按 Package、Semantic、Data、Computation、Control、Projection、Experience 分组；
- 每个失败项显示 affected capability、证据、修复建议和深链；
- PASS 只来自后端 exact revision，编辑后立即显示 `STALE`；
- Versions 页面按五类合同展示 semantic diff，而不是只展示 JSON diff；
- Publish drawer 显示 exact revision、version、validation time、阻塞项、assumption/missing 摘要和发布影响；
- 主按钮始终叫 `发布版本`，成功反馈叫 `版本已发布`；
- Delivery 页面展示 Published → Bound → Certified → Active → Verified 状态，并链接到 Agent Operator 页面；Studio 不偷偷执行 activate；
- 新版本认证失败时显示旧 Active 仍在服务，并提供查看失败证据的入口。

### 5.8 空态、错误与可访问性

- 每个空态都给出下一步动作，例如“还没有来源材料 → 添加材料”；
- error 文案说明发生在哪个 stage、哪些内容未改变、用户可以做什么；
- loading 使用 skeleton 或 stage status，不使用无限旋转掩盖长任务；
- destructive 操作使用明确对象名称和结果，不用只写“确定吗”；
- 所有关系/影响任务都有 list/table 路径；
- focus、表单 label、错误关联、键盘操作和 reduced-motion 进入每个 slice 的验收；
- 本轮桌面发布验收 1024/1280/1440/1600px，并覆盖 100%/200% zoom；1024px Inspector 为 drawer、可 Esc 关闭并恢复焦点，不把移动端适配塞进当前范围。

## 6. Revised vertical implementation slices

本轮评审后的执行原则：

- Phase 0 可以是只读 discovery，但不得写任何权威状态；
- 从第一条可写 slice 起，每条能力都必须穿过 exact source/candidate → human decision → Draft → affected validation/diff，并证明失败不改变 Published/Active；
- 不按“先做完语义页、再做完数据页、最后才发布”的水平层建设；
- Semantica 只实现明确 allowlist 的 stage；public contract 只提升被 ADT 与 materially-different 第二案例共同证明的 primitive；
- 每个阶段都有 GO / NARROW / EXTEND / STOP 或明确的进入/退出条件，不靠 UI 看起来完成来放行。

---

### Phase 0: Product contract and Semantica compatibility preflight

**Estimate**: 3–5 active person-days；只读 learning slice，不授权 Draft/Release/Active mutation。

#### What to build and decide

- 冻结 12–15 分钟 ADT hero flow、Solution route identity、copy/lifecycle matrix、第二案例 falsification manifest；
- 冻结 Graph Editor 的 typed-operation boundary、Candidate overlay、List/Graph 等价性和 graph-off 降级合同；不得把 Semantica raw graph 或画布坐标升级为 canonical truth；
- 在目标 ARM/K8s 架构构建 pin exact Semantica image，只启用明确 parse/extract/proposal stage；
- 使用当前 External Reviewer 输入中的 XLSX 与现有 ADT registered sources 做只读 compatibility run；
- 证明 Qwen 只能经过 product Model Gateway，worker 无 provider key、无任意 base URL；
- 测量 image/startup/RSS、parse/anchor yield、model calls/tokens、candidate counts、失败与资源上限；
- 输出 GO / NARROW / STOP 和 A1 fresh WBS。

#### Acceptance criteria

- [ ] no-op handler、空 pipeline、selected source 未逐一结算、全部 extractor 失败均不能得到 product SUCCESS；
- [ ] worker 无 Draft/Decision/Release/Active 写权限，非 Model Gateway 外连为 0；
- [ ] current XLSX 的 sheet/A1/raw formula/value locator 可回读；无法 exact 定位的内容明确 UNSUPPORTED_ANCHOR；
- [ ] 超过文件/单元格/token/时间/内存上限时 bounded failure，Studio API 与旧 Active 保持可用；
- [ ] 第二案例在看运行结果前已冻结 material differences、3–5 个问题、truth/control 与合法 MissingCapability outcome。

---

### Slice A1: Durable ADT mixed-risk shadow construction

**User stories**: US-02, US-03, US-04
**Estimate**: 6–10 active person-days。

#### What to build

以现有 exact ADT sources 为入口，建立 PostgreSQL Run/Attempt/lease/outbox、S3 immutable stage artifacts、product-owned Candidate Bundle 与服务端状态机。Candidate 至少覆盖 Object/Link、一个 metric 或 amount mapping、一个 conflict、一个 missing/unsupported；Review Center 可读、可筛选、可查看 exact evidence，但 shadow 不允许 apply。

#### Frontend interactions

- 显式 Solution context、Sources/Run、durable stages、Jobs tray；
- mixed-risk candidate queue、support class、Evidence Inspector、impact summary；
- CANCEL_REQUESTED / COMMITTING / LEASE_LOST / STALE 等服务端真实状态；
- completed shadow 与当前 fixed-slot tracer 的差异视图。

#### Acceptance criteria

- [ ] logical Run 与 Attempt 分离，duplicate delivery、lease expiry、late A/retry B、cancel-vs-commit 后每个 Run 最多一个 terminal bundle ref；
- [ ] candidate key 跨进程、输入顺序和 Python hash seed 稳定；revision digest 能识别模型内容变化，旧 decision 不误复用；
- [ ] adjacency heuristic、model inference、reviewer-authored、direct exact 等 support class 不因 confidence 改变；
- [ ] raw occurrences、pairwise dedup proposals、alternatives 和原 Link endpoints 全部保留，Semantica 不能先做破坏性 merge；
- [ ] selected N 个 sources 有 N 个 terminal outcomes，partial result 不得冒充 success；
- [ ] shadow 运行、失败、取消、stale 对 Draft/Published/Active 的写入次数均为 0；
- [ ] current ADT Agent golden/release regressions保持通过。

---

### Slice A2: Transactional Review Center and active apply

**User stories**: US-04, US-05, US-06
**Estimate**: 5–8 active person-days。

#### What to build

把 Review Center 从 shadow 提升为正式 human decision surface：所有 candidate 默认 UNREVIEWED，typed edit、REJECT、DEFER、有限 low-risk batch、durable resume、stale recovery 和一次 transactional apply。Review Decision、candidate terminal state、新 revision/head 使用同一 PostgreSQL transaction/CAS；随后运行受影响 validation 并展示 semantic diff。

#### Frontend interactions

- 三栏 Review workspace、键盘 next/previous、virtualized queue；
- hidden-filter/selected/undecided/high-risk counts；
- edited value 的 support change、apply preview、autosave/batch digest；
- stale batch 的“查看差异 / 归档 / 基于当前 revision 重跑”；
- CAS conflict 不覆盖，返回后保留 filter、selection 和 queue position。

#### Acceptance criteria

- [ ] 自动生成 ACCEPT/EDIT decision 数为 0；high-risk 通用 batch accept API fail closed；
- [ ] crash injection 后只能是旧 head + 无 apply，或新 head + 完整 Decision/candidate states；同 request digest 重试幂等；
- [ ] apply 前服务端验证 exact batch digest，in-flight autosave 不会被漏掉或静默覆盖；
- [ ] 60-item mixed-risk fixture 中，目标 reviewer 能找全 blocker、完成指定任务且 0 accidental accept；首轮实测用于重定时间阈值；
- [ ] apply 后 validation 绑定新 exact revision；任何后续编辑立即 STALE；
- [ ] feature flag 只有在上述 gate 通过后从 shadow 切 active。

---

### Gate A: Materially-different second-case falsifier

**Estimate**: 3–5 active person-days；可以在 A1 完成后与 A2 部分并行。

#### What to prove

使用 Phase 0 冻结的第二案例，在同一 Run/Candidate/Decision seam 上完成最小 source → candidate/gap → human decision。优先 Listing SLA/Backlog；只有当 Cash Trading manifest 证明 event/grain/time/population/operator 差异足够时才可替代。此 Gate 不要求完整 Agent case，也不允许现场扩公共 schema 只为通过。

#### Acceptance criteria

- [ ] 输出 difference ledger、MissingCapability list、run receipts 与 CONTINUE_TO_FACTOR / NARROW / EXTEND / STOP Decision；
- [ ] MissingCapability 在 model/query 前 fail closed、old Active 不变、portability claim 为 false；
- [ ] 只有两个案例都证明等价的 candidate/support/decision primitive 才能进入 public common contract；
- [ ] Gate A 与 A2 都通过后才允许公共 Case Compiler factorization，并强制重估后续 WBS/ROM。

---

### Slice B: First self-service Source Adapter

**User stories**: US-02, US-03
**Provisional estimate**: 4–7 active person-days；Gate A 后重估。

#### What to build

把当前 registered inputs 提升为 self-service Source Library，第一批只承诺当前真实材料需要的 **XLSX + 安全转写文本**：upload/paste、exact version、preview、format-specific anchor、selected source set、cancel/retry/stale，并一直走到 Candidate/Review。DOCX/PDF/TXT binary adapter 不打包承诺，按真实 fixture 逐个追加。

#### Acceptance criteria

- [ ] source replacement 形成新 exact version，旧 Run/Release 继续渲染旧 evidence；
- [ ] XLSX anchor 包含 workbook version、sheet、A1 range、raw formula/value 与 snippet digest；
- [ ] parser 只读取 selected exact refs，不能扫描 workspace/bucket 其他材料；
- [ ] upload/API/worker restart、duplicate delivery、cancel 和 unsupported format 状态收敛；
- [ ] Preview 从 anchor 唯一高亮 exact source；无法回读时不能 source-supported accept；
- [ ] empty/loading/error/stale/cancel/retry 通过真 API桌面测试。

---

### Slice C: One complete analytic capability

**User stories**: US-05, US-06, US-07, US-08, US-09
**Provisional estimate**: 8–13 active person-days；Gate A 后重估。

#### What to build

以一个 ADT supported question 为 tracer，把 semantic definition、metric、mapping、join、Formula/Query AST、Agent Experience、frozen Control Suite、validation、semantic publish、Agent bind/certify/activate/answer 纵向闭合。SQL 只产生 observation + unresolved spans；Agent 只执行 closed typed operators。

#### Frontend interactions

- Review deep-link 到 Semantic/Data/Agent Experience editor，再返回原 queue；
- metric 展示 grain/population/period/unit/formula/rounding/null policy；
- mapping/join 展示 source evidence、类型/单位、cardinality、grain change 和影响；
- Validation 显示 correctness 与 coverage 两套结果及 exact fix link；
- Versions 显示 component-aware diff；Studio Delivery 只读，Agent deep link 执行 operator动作。

#### Acceptance criteria

- [ ] ratio-of-sums、trading-day denominator、unit、amount mapping、fanout join mutations 被独立 gate 捕获；
- [ ] generated query 与独立 reference interpreter/control oracle differential 为 0；Preview=Agent 只证明 consistency，不替代 correctness；
- [ ] unknown AST/SQL construct 为 UNSUPPORTED，query execution count 为 0；
- [ ] semantic release、Experience、Control Suite、Binding 以独立 refs/owners 组合，修改其一不伪装成其他 component 变更；
- [ ] publish 不 activate；prepare/certify/activate 失败时旧 Active 继续服务；
- [ ] Agent SCR 只能创建 proposed change，不能自动成为 truth。

---

### Slice D: Coverage expansion by capability

**User stories**: US-05, US-06, US-07
**Provisional estimate**: 10–18 active person-days；由 Gate A 和 Slice C actuals重估。

#### What to build

按真实用户问题逐项增加 Event、Link、Rule、更多 metric/formula/operator、mapping/join、question family、evidence/control 与必要 source adapter。每一项都沿用 Slice C 的完整纵链，不能按页面整层铺开。同时交付完整 Graph Editor：由 Semantica Candidate Graph 与 canonical package 生成两个明确图层，支持 typed node/link editing、关系方向、影响预检、来源与 Review 深链；List 与 Graph 必须对同一 revision 得到等价结果。

#### Acceptance criteria

- [ ] 每个新增 capability 都有 source/candidate/decision/draft/validation/diff/Agent 或明确 non-runtime outcome；
- [ ] Formula/Query AST 的 supported denominator、property/differential/mutation cases 同步扩展；
- [ ] duplicate merge 保留 occurrence/provenance/rejected edges，不静默吞冲突；
- [ ] derived relationship/impact read model 可重建，不成为第二权威；
- [ ] Graph 中新建/修改/删除节点或边与 List 中等价操作生成相同 canonical digest；stale revision、非法类型/方向、未复核 candidate 和删除受依赖对象均 fail closed；
- [ ] 500 节点/1,500 边的基准图在目标桌面环境可交互，过滤、选中、展开、Inspector 与键盘路径可用；超出前端阈值时采用按需邻居加载而不是一次性绘制；
- [ ] 新 source format 只有 exact anchor/preview/failure/resource fixture 全过后才标 supported。

---

### Slice E: Consolidated validation, release and handoff

**User stories**: US-08, US-09
**Provisional estimate**: 4–7 active person-days。

#### What to build

统一 Package、Semantic、Data、Computation、Control、Projection、Experience 的 validation/readiness；提供 component-aware diff、幂等 publish intent/recovery、Studio read-only delivery timeline、Agent deep link 与 SCR triage。该 slice 只做跨 capability consolidation，不把 validation/publish 留到最后才首次接入。

#### Acceptance criteria

- [ ] process death发生在 artifact stage/read-back/index/head任一边界时，authoritative ref 与 exact bytes 始终一致；同 intent幂等；
- [ ] unresolved blocker、compile unsupported、stale validation、control failure 阻断对应 publish/capability；
- [ ] Studio 正常路径、alias、快捷键对 prepare/activate/rollback mutation endpoint 调用数为 0；
- [ ] delivery 显示 Published → Bound → Certified → Active → Verified，失败时明确旧 Active 正在服务；
- [ ] 发布、交付、失败、回滚和 SCR 均有真 API Playwright coverage。

---

### Slice F: Blank/template onboarding and final two-case proof

**User stories**: US-01, US-10
**Provisional estimate**: 5–8 active person-days。

#### What to build

补齐 Blank、Template、Import Package onboarding；用同一 frozen build 从 clean state 运行 ADT 与第二案例。由一名未参与实现的 core engineer 只依赖 playbook 完成第二案例安装/构建，记录时间、帮助、修改文件和 core diff。此阶段只允许形成“工程师可扩展”的有界主张；fresh business builder self-service 需要后续 author-kit/proxy gate。

#### Acceptance criteria

- [ ] Solution create/copy/edit/switch/archive/restore/delete 有明确资产矩阵与真 API E2E；copy 后 raw source/run/review/release/active refs 交集为 0；
- [ ] route、cache、counts、Inspector、Draft/Published/Active 在 refresh/back/multi-tab 中始终隔离，缺失 identity fail closed；
- [ ] same frozen build 双案例运行；公共 primitive 的任何变化进入 core diff/Decision，不伪装成 profile asset；
- [ ] 两案例各有 supported/boundary/failure 或合法 MissingCapability control；
- [ ] 两名独立 proxy 能解释 Source → Candidate → Decision → Draft → Publish，以及 LLM/Semantica 不拥有 truth/publish authority；
- [ ] 形成新增 Solution playbook、demo script、lesson learned 与受限 portability conclusion。

## 7. Dependencies, funding envelope and milestones

~~~text
Phase 0
  └─ Slice A1
      ├─ Slice A2 ───┐
      └─ Gate A ─────┴─ Join: reviewed ADT + generalization decision
                         ├─ Slice B
                         └─ Slice C
                              │
                              └─ Slice D
                                  └─ Slice E
                                      └─ Slice F
~~~

实际 join 条件是 **A2 + Gate A** 均通过后才能冻结公共 compiler primitives；Slice B 与 Slice C 可在 join 后并行，Slice D 消费二者结果。

- **首个可批准 learning/delivery tranche**：Phase 0 + A1 + A2 + Gate A，共 **17–28 active person-days**；这是当前唯一 decision-grade envelope；
- 原 39–61 pd 总 ROM 在本轮评审后作废，不再作为交付承诺；
- Slice B–F 当前仅是 **31–53 active pd 的低置信 planning hypothesis**，Gate A 后必须根据 worker/anchor/review throughput、second-case gaps 和 Slice A actuals重做 P50/P90 WBS；
- 每个 WBS 必须覆盖 code、schema/migration、tests、docs/runbook、deploy/rehearsal、唯一 owner、dependency、confidence 和 excluded wait；
- 并行只缩短日历时间，不减少 active effort，也不能把半条链当成里程碑。

建议里程碑：

- **M0 Compatibility evidence**：Phase 0；
- **M1 Trusted Source-to-Decision**：A1 + A2；
- **G1 Generalization decision**：Gate A；
- **M2 First complete ADT capability**：B + C；
- **M3 Coverage and governed handoff**：D + E；
- **M4 Authorability and two-case proof**：F。

## 8. Test and evaluation strategy

### 8.1 Retained regression

- 当前 Python、frontend、build、ADT golden、Cash Trading、release lifecycle、Qwen 和 Studio CAS tests 全部保留；
- 每个 phase 首先补 red tests，再实现通过；
- Semantica 不进入 Agent runtime dependency tree，使用依赖/image assertions 验证。

### 8.2 新测试层

- Contract：closed Candidate Bundle、support class、stable key + revision digest、unknown type、missing/approximate anchor、stale base、digest mismatch；
- Worker：no-op/empty、success/failure/cancel/crash/retry/duplicate delivery、lease expiry、late attempt、no partial commit、resource limit；
- Security/data flow：only selected source refs、Model Gateway only、retry/repair/shadow同一 projection/budget、非 gateway egress 为 0、no raw provider response、secret/error containment；
- Anchor：XLSX sheet/A1/formula/value、转写文本 span、重复内容、插行/插列、source replacement、tamper round-trip；
- Semantic mutation：wrong definition、relation direction、metric denominator、unit、mapping、join fanout、destructive transitive merge；
- Review：默认 UNREVIEWED、all dispositions、batch restrictions、autosave/apply race、transactional crash、stale archive/rerun、review resume；
- Control/correctness：frozen Control Suite、independent oracle、property/differential/mutation denominator；
- UI：完整 run状态、empty/loading/success/failure/stale/conflict、Solution isolation、keyboard、1024/1280/1440/1600 与 100%/200% zoom；
- End-to-end：ADT source → candidate → review → validation → publish → Agent answer → SCR；
- Generalization：预登记第二案例允许 MissingCapability；factorization 后同一 frozen build 双案例 clean run。

### 8.3 Evaluation gates

- **Construction integrity**：来源身份、anchor、provenance、重复运行与 partial failure；
- **Semantic correctness**：ADT control/mutation 与人工 review 结果；
- **Coverage**：五类 Case Contract 是否完整，不与 correctness 混为一个百分比；
- **Interaction usability**：3 名目标角色能否完成主流程、是否理解状态与下一步；
- **Agent behavior**：Answered、Clarify、Refused、Failed、No-data 分开报告；
- **Generalization**：第二案例差异、MissingCapability 和等价 primitive 分开报告；只对两案例共同证明的能力形成 portability claim。

## 9. Rollout, feature flags, fallback and rollback

- feature flag：`studio_construction_engine=off|shadow|active`；
- Phase 0 无写权；Slice A1 为 shadow，只展示 Candidate/差异、不允许 apply；Slice A2 的 transaction、review、usability gate 通过后才 active；
- 每个 workspace 可继续使用现有 manual/typed authoring，不依赖 Construction Engine 才能编辑和发布；
- Semantica worker unavailable 时，Sources/Review history 可读，手工 Studio 和当前 Agent 正常；
- Candidate Bundle/Compiler schema version 不兼容时 fail closed，并保留旧 worker/build；
- graph/vector read model 可全部重建；Graph Editor 只消费 derived graph projection 并提交 canonical typed operations。graph read service 失败时自动回退 List/Table，已发布语义与 Agent runtime 不受影响；
- 新 Studio 前端使用 route/feature flags 逐页切换；旧页面 alias 只能 exact redirect/只读，不能保留隐式 ADT 写路径；
- 发布和 Agent runtime rollback 沿用当前 exact previous snapshot/CAS 路径。

## 10. 明确不在当前迭代范围

- 企业 IAM/SSO、细粒度 RBAC 和 customer 生产权限集成；
- 直接连接 customer 原始数据平台或从安全区外发原材料；
- 手机端和小屏移动端产品适配；
- 通用 autonomous agent framework；
- Semantica Explorer 整体替换现有 React Studio；
- 把 RDF/OWL/SPARQL 变成事实分析执行路径；
- 在没有规模证据前引入权威图数据库、Redis/Celery/Temporal；
- Knowledge Center 总体平台建设；
- 生产 HA/SLA、灾备、Object Lock/KMS 和客户 K8s 适配认证。

## 11. 进入开发前的决策点

需要主决策人确认：

1. 六个一级菜单与显式 `/solutions/{solution_id}/...` 二级路径是否作为产品 IA；
2. Semantica 是否保持后台 Construction Engine，不作为第三产品或品牌，并接受 Phase 0 compatibility evidence 后再进入可写实现；
3. 一次集中 Review Center、默认 UNREVIEWED、有限 low-risk batch、transactional apply 是否作为正式 HITL 模型；
4. 是否批准 **Phase 0 + A1 + A2 + Gate A 的 17–28 active-pd tranche**，并接受 Gate A 后重估而不是继续承诺旧 39–61；
5. 第二案例是否采用 Listing SLA/Backlog 作为默认 falsifier；如果坚持 Cash Trading，需要先证明其 material difference；
6. 已确认 full Graph editor 本轮交付；第一批 self-service source 仍只承诺 XLSX + 安全转写文本；
7. 是否接受“一个 Studio UI、多个独立 versioned component authority”：semantic release、Agent Experience、Control Suite、Binding 不合并成一个 compound release。
