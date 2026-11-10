# Ontology Analytics Product Family — Common Product + Ontology Package 完整设计与技术方案

状态：`Approved Baseline v1.0 — Implementation Authorized`

日期：2026-08-20

Decision Owner：Muyu

主要读者：产品、架构、工程、数据、AI、安全、External Review Team 交付团队

上游约束：

- `01_product_group_strategy.md` v1.0 Approved Baseline；
- `02_shared_product_contract.md` v0.1 Approved/Frozen；
- `17_architecture_approval_and_stack_decision.md` Approved / Implementation Authorized；
- 当前已部署的 constructed-synthetic ADT LLM Engineering Demo；
- customer 原始业务材料默认不能离开安全区，External Review Team 只能按要求安全转写；
- 当前推荐交付目标是 constructed-synthetic `Scenario-Portable Engineering Demo`，不是生产 IAM、完整 Knowledge Center、企业级多租户平台，也不冒充完整 Stage 1 governed-evidence conformance。`Governed General Demo / Product Target` 在同一架构中定义，但只有 exact Product-Domain PRD、Profile/Annex/vectors 获得 Approved/Frozen authority 后才可实施和宣称。

---

## 1. Executive Decision

### 1.1 目标产品形态

二阶目标定义为：

> 使用同一套 Ontology Studio 与 Ontology Analytic Agent 产品构建物，通过加载不同的、独立寻址的语义、Agent experience、reference/control 和环境 binding components，运行不同的企业表格/KPI 分析场景。ADT 是第一个 reference solution，不是产品代码中的固定业务逻辑。

用户可见产品仍然只有两个：

1. **Ontology Studio**：把 Cleared Input 转化为可审核、可验证、可版本化的语义与分析发布物；
2. **Ontology Analytic Agent**：消费已激活的运行快照，完成 Dashboard、问数、比较、拆解、探索和证据说明。

`Shared Contracts & Kernel` 是代码与合同底座，不是第三个用户产品。`ScenarioDistributionBundle` 与 build/test CLI 只是运输/交付机制，不是第三个产品，也不是 GSR、VRS、Activation 或 Eligibility authority。

#### 两个诚实的交付层级

| 层级 | 当前作用 | 可以宣称 | 不可以宣称 |
|---|---|---|---|
| Scenario-Portable Engineering Demo | 用 ADT + 第二 synthetic scenario 尽早证伪 component boundary；复用 current local controls | same minimal product build 在已声明 capability ceiling 内运行两个 exact scenario；constructed-synthetic engineering evidence | Stage 1 conformant、customer validated、production/durable、任意业务 3–7 天接入 |
| Governed General Demo / Product Target | 完整实现 Frozen authority chain、durable commit、restore/revocation 和正式 Release Manager flow | 仅在 exact authority manifest、conformance 与 release gates 全部 PASS 后按其 claim ceiling 宣称 | 不能由本 architecture approval、当前 Engineering Demo 或 bundle digest 自动获得 |

推荐的下一项投资是第一层，并以端到端纵向切片同时落地 React、PostgreSQL、S3-compatible Artifact Store 与 Kubernetes；不建设脱离用户路径的四条水平基础设施工程。

### 1.2 通用性的准确边界

首版只承诺一类问题域：

> **企业结构化/表格数据的有界指标分析**。只有 Governed Product Target 通过 exact authority chain 后，才可附加 governed-evidence claim。

首版支持：

- 业务对象、关系、流程、指标、规则、维度、数据映射和访问政策；
- tabular 数据源、字段映射、受限 Join、过滤条件和时间范围；
- 基础聚合指标、派生指标、比率指标；
- 指标事实、范围/期间比较、分组贡献、排名、有限的顺序分解和证据追溯；
- AgentExperienceProfile-driven Dashboard、登记问题族和有界 LLM 探索；
- Source → Observation → Human Decision → Draft → Release → Runtime Activation。

首版不承诺：

- 任意业务文档一键生成正确 Ontology；
- 任意 SQL、Python、图算法、预测、优化或 AutoML；
- 任意复杂公式都能通过配置表达；
- 通用 RAG/Knowledge Center；
- 多租户 SaaS、生产 IAM、HA、SLA、跨区域灾备；
- 包内可执行任意 Python/JavaScript 插件。

如果新案例需要当前能力语法不存在的operator、source connector或policy mechanism，它必须形成`MissingCapabilityRequest`并使当前portability claim失败，不能伪装成component-only onboarding。

### 1.3 关键技术决定

1. **Human-authored YAML 只是 authoring source；Semantic Approval 覆盖的 canonical JSON GSR subject 才是跨产品 semantic authority。** RDF store 不是写入权威。
2. **Canonical typed JSON 是语义 authority。** RDF/JSON-LD 如被某个已登记的 lineage/impact 用户任务启用，只能是 versioned derived projection；SHACL、SPARQL 与 projection fidelity 都在 exact product-owned `SemanticProjectionProfileRef + ShapeSetRef + projector build` 下运行，事实分析不走 SPARQL。
3. **当前 Portable track 默认 `graph_feature=off`。** 复用现有 RDF/SHACL regression 资产，但不新建 SPARQL surface、`KnowledgeGraphPort` 或 triplestore；只有 exact graph-dependent hero task 获批才开启有界 RDFLib + pySHACL 实验。
4. **任何物理 bundle 都不是 compound authority。** Studio 正式输出是 GSR；RuntimeSnapshotPayload、five VerificationAttempts、SEALED VRS、Activation、Eligibility 和 ResultReleaseCommit 保持独立 identity/lifecycle。
5. **PostgreSQL 17 是新产品状态的 implementation baseline。** 现有 filesystem/SQLite state 只作为已部署 ADT demo 的迁移来源、兼容回退和 isolated-test adapter；从第一条新架构纵向切片起，新的权威产品状态写入 PostgreSQL，客户事实表仍不进入产品事务库。
6. **不可变 bytes 使用 content-addressed Artifact Store；demo facts 使用 content-addressed Parquet + DuckDB；企业环境通过 `QueryEnginePort` 绑定可寻址 snapshot。** 产品事务库不承载客户事实表。
7. **Agent 保留当前 typed、bounded、可审计的自研 orchestration。** 现在不创建宽泛 framework port，不引入 LangGraph/DeepAgents；未来 adapter 也不能拥有 policy、facts、evidence 或 commit authority。
8. **LLM 只负责 open-language → closed candidate/goal、受限 next-tool selection 和 Studio observation proposal；数字、SQL、权限、发布和事实 clause 仍由 deterministic components 负责。** Scenario components只能提供 typed domain data/labels/examples，不能靠 bundle 自动改变 system prompt/tool/policy。
9. **React + TypeScript + Vite 是前端 implementation baseline。** 迁移按 ProductContext 与 safe presentation descriptor 驱动的逐 route 纵向切片进行，不做 big-bang rewrite；browser 永远没有事实 authority。
10. **S3-compatible exact-version object storage 与 Kubernetes 是部署 baseline。** local/test 使用 MinIO，当前自有 EC2 使用 k3s；它们提供稳定的工件与编排底座，但不自动产生 semantic authority、HA/SLA、生产 IAM 或 customer readiness。
11. **产品镜像与场景 components 独立发布。** 最终 frozen image digest 必须 clean-run ADT 与第二案例；单 deployment 首版只激活一个 exact scenario context，多租户/catalog 后置。

---

## 2. First Principles and Permanent Invariants

### 2.1 先区分什么稳定、什么变化

| 稳定的产品能力 | 随案例变化的 scenario components | 随环境变化的 Deployment 内容 |
|---|---|---|
| lifecycle、CAS、release、activation、rollback | 业务词汇、对象、关系、流程 | 环境 ID、workspace binding |
| source/observation/decision workflow | 指标、公式、规则、维度 | 数据位置、dataset identity |
| component loader、validator、evidence | 数据模型、mapping、join requirement | credential、secret、network |
| generic analysis operators | capability graph、question family | Qwen account/model/region |
| LLM gateway、安全投影、budget、product-owned prompt contract | typed domain vocabulary/examples、question parameters | egress decision、rollout |
| schema-driven frontend renderer | Dashboard/editor/view descriptor | auth、URL、feature flags |
| query-engine ports | control suite、sample/demo data | query-engine/data/policy binding；channel另属Activation |

### 2.2 永久不变量

- Agent 不读取 Studio draft、review comment、authoring profile、原始治理附件或整个 DistributionBundle；
- Agent 不写 Ontology，不签 gate，不 publish，不 activate；
- Studio 的唯一正式跨产品 semantic output 是 environment-independent immutable GSR；它不发布 control/data、Agent prompt、Activation 或 target runtime；
- LLM 输出永远是 candidate/observation/goal，不是 truth、SQL authority 或 release authority；
- Missing / Withheld / Unconfirmed 不由模型补齐；
- User Evidence 不包含 SQL、参数、表列、物理 locator、raw row、secret、prompt 或 stack trace；
- GSR、component artifact、RuntimeSnapshotPayload、VerificationAttempt、VRS、Activation、Eligibility、Execution、Evidence 和 ResultReleaseCommit 各有独立 identity 和 checksum；
- publish、payload assembly、five-gate verification、seal、activate、eligibility、query 和 result commit 是不同动作；失败时旧 active snapshot 只有在当次 eligibility 仍为 ALLOW 时才继续服务；
- 不支持的能力显式 `UNSUPPORTED`/`FAILED_PRECONDITION`，不走静默 fallback；
- browser 永不计算 authoritative facts，也没有 browser-only analysis fallback；
- 正确性、coverage、Clarify、Refuse、Failed、Claim coverage 和 leakage 分开报告。

### 2.3 Generalization proof

不能先造“通用 compiler”再拿第二案例为它背书。证明顺序固定为：

```text
preregister materially-different second scenario
→ build the smallest dual-scenario discovery tracer
→ record every difference and missing capability
→ record a DiscoveryOutcome
→ STOP / NARROW / EXTEND / CONTINUE_TO_FACTOR investment decision
→ promote only evidence-backed common primitives
→ freeze one product build
→ clean-run both external component sets
→ issue PORTABLE_PASS only at the final generalization gate
```

合法的 `DiscoveryOutcome` 有三种：

- `SUPPORTED_CANDIDATE`：最小 dual-scenario tracer 在预登记范围内产生了可进入 factorization 的证据；它**不是** portability PASS；
- `FALSIFIED_MISSING_CAPABILITY`：精确暴露缺失 operator/connector/policy，当前 portability claim 为 false，但实验成功产生了决策证据；
- `INVALID_TEST_CASE`：场景不够不同、truth/control不能独立冻结或超出本 edition ceiling，换案例但保留失败记录。

`GateAInvestmentDecision` 只能是 `STOP / NARROW / EXTEND / CONTINUE_TO_FACTOR`。`PORTABLE_PASS` 是另一种 final evidence conclusion，只能在 common factorization、同一 frozen build、ADT clean run、clean state、Listing clean run和全套行为/control/claim检查完成后追加，不能由 Gate A 或 presenter 产生。

Gate A 必须消费不可变 `GateAEvidenceManifest`：Listing/Reference/Control/Suite/DataIdentity refs、D1 contract、exact component/build/egress refs、两场景run receipts、query/model counts、MissingCapability list、common/scenario diff ledger、regression结果、actual active effort、`portability_claim=false|unknown`和单独的DecisionRecord。`INVALID_TEST_CASE` 不能进入factor；换案例必须保留原manifest与失败证据。

优先 falsifier 仍为 constructed-synthetic `Listing Application Processing SLA & Backlog`，但必须先冻结 `ListingFalsificationManifest`：Application/StageEvent grain、state transition、as-of cutoff、timezone/business calendar、open/censored/reopen、SLA denominator、backlog semantics、3–5 questions、Clarify/Refuse、ReferenceManifest、DataIdentity、controls和mutations。它不能通过预计算 duration/status 字段绕过真正要验证的语义。

---

## 3. Reconciled Current Baseline

### 3.1 已经完成并必须保留

- portable Studio release 与 Agent-local runtime binding 已拆分；
- immutable release、snapshot checksum、prepare/certify、expected-current CAS activation 已实现；
- `ScenarioAdapter` exact `id@version` seam 已实现；
- 33 项 semantic/data/SHACL checks 和 ADT 8-case golden suite 已实现；
- Agent deterministic Dashboard、claims/evidence 和 boundary outcomes 已实现；
- Qwen `qwen3.8-max` Agent closed question-family flow 已实现；
- Studio five-slot observation → human disposition → CAS draft flow 已实现；
- browser 只消费真实 API，browser analysis fallback 为 0；
- Docker/Compose、ARM64 方向、EC2 HTTPS demo、共享登录和双产品跳转已实现；
- 当前 release record 报告 119 backend tests、33/33 package checks、真实 Qwen/Playwright desktop flows 通过。

这些能力不因“做通用版”而重写。

### 3.2 当前阻断通用化的事实

- `Scenario` schema 写死 `market_id`、固定 periods；
- `AnalysisPattern.intent` 写死 ADT/segment/turnover 类意图；
- default registry 只安装 `AdtScenarioAdapter`；
- planner/compiler/runtime/LLM tools 直接引用 ADT metric IDs 和 operator；
- Studio workspace 只支持一个固定 workspace、四个 draft fields 和五个 slots；
- intake parser 直接识别 `M-03`、中文固定句式和 ADT 文件名；
- Console 内置 ADT ontology、Q3/Q4、oracle、Dashboard 和问题；
- API 固定 package ID、role、environment 和 scenario path；
- Docker image 直接 `COPY scenarios`，model profiles 直接引用 `/app/scenarios/adt`；
- 当前只有一个 scenario，无法证明哪些 abstractions 真正 common。

### 3.3 当前与目标的准确关系

当前系统是：

> `ADT vertical product with portable lifecycle and an adapter seam`

目标系统是：

> `component-driven product runtime with ADT as one independently versioned solution assembly`

### 3.4 Anti-rebuild migration guard

D-1必须把每个现有module/API/artifact标为`retain / wrap / parameterize / replace / delete`。默认规则：

- current release/prepare/certify/CAS、calculator、Formula evaluator、SQL compiler、Facts/Claims/Evidence、closed renderer、Qwen private-buffer/automatic-off、Studio observation/disposition CAS全部retain或wrap；
- existing 119 tests、33 checks、ADT 8-case、registered Qwen cases、Studio five-slot cases形成immutable regression inventory；
- 每个migration slice比较old/new outcome、Facts、Claims、projection bytes/digest、tool sequence、fallback和commit behavior；只允许预登记identity-adapter差异；
- calculator/compiler/formula/renderer改动若没有approved migration reason和新增mutation test，CI/release gate失败；
- legacy path只作shadow comparator，不拥有truth、fallback或release authority。

---

## 4. Target System Architecture

### 4.1 Logical architecture

```text
┌────────────────────────── Ontology Studio ──────────────────────────┐
│ Intake Registry → Extraction/Observation → Human Decision           │
│ → Candidate Graph → Validation → Semantic Approval → Immutable GSR  │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ unique formal semantic output
┌──────────────────────────────▼───────────────────────────────────────┐
│ Shared Contracts & Kernel                                           │
│ Component Loader │ Contract Registry │ Projection │ Payload Assembly │
│ Five Verifications │ VRS Seal │ Activation/Eligibility │ Evidence    │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ activated + currently eligible VRS
┌──────────────────────────────▼───────────────────────────────────────┐
│ Ontology Analytic Agent                                             │
│ Resolver → Policy → Goal/Plan → Typed Tools/SQL → Facts/Claims       │
│ → Evidence → Closed Renderer → Result Commit                         │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
             ┌─────────────────┼─────────────────┐
             ▼                 ▼                 ▼
      Query Engine Port   Artifact Store   Model Gateway Port
      DuckDB/warehouse    local/S3         Qwen/approved provider
```

### 4.2 Runtime deployment context

正式 Product Target 的对象链固定为：

```text
GSRRef
+ RuntimeSemanticProjectionRef
+ [if graph_feature=on] SemanticProjectionProfileRef/ShapeSetRef/projector/query-template build refs
+ AgentExperienceProfileRef
+ ProductBuild/CapabilityRegistryRef
+ DeploymentBinding/DataIdentity/Policy refs
+ Reference/Control/Suite/Evaluator refs
= immutable RuntimeSnapshotPayloadManifest

Payload + five exact PASS VerificationAttempts
= SEALED VRS

SEALED VRS + append-only Activation(channel)
+ point-in-time Eligibility
= RuntimePackageView resolvable by Agent
```

其中：

- GSR 只含 environment-independent semantic subject、lineage/decisions、binding/capability/policy/disclosure requirements 与 limitations；
- AgentExperienceProfile 是 Agent Domain 拥有的 question family、answer obligation、safe presentation descriptor 与 product-owned prompt/task refs；
- DeploymentBinding 只描述 environment、opaque resources、query/model/policy refs，不包含 secret 或 activation channel；
- Reference/Control/Suite 与 synthetic data 有独立 truth/control authority，不由 DistributionBundle 获得 authority；
- VRS 只证明 exact payload 与五份 PASS refs 已被 seal，不包含永久 READY；
- channel 只属于 Activation/Eligibility；Agent 不解析 bare GSR、bundle、payload 或未 seal VRS。

Scenario-Portable Engineering Demo 不使用 GSR、VRS、Eligibility 或 ResultReleaseCommit 作为对象名。它有一条单独、规范化但明确降级的对象链：

```text
trusted INSTALL intent + exact raw bundle digest
→ PackageSafety PASS + immutable ComponentInventory
→ EngineeringSemanticRelease
+ ProductBuild/installed Capability refs
+ EngineeringDeploymentBinding + Exact DataIdentity
+ Reference/Control/Suite refs
+ Policy/Model/Egress refs
+ EngineeringMinimumControlProfile/v1
→ EngineeringRuntimeSnapshot
→ EngineeringActivationRecord (current expected-head CAS)
→ closed EngineeringRuntimeView
→ EngineeringDemoResponseCommit
```

`EngineeringSemanticRelease` 是 current Studio release seam 的明确非 conformant identity；它不能被提交到 formal GSR endpoint，也不能作为 Semantic Approval/PUBLISH authority。`EngineeringRuntimeSnapshot`、`EngineeringActivationRecord` 与 `EngineeringDemoResponseCommit` 同理，schema、API path、UI label和telemetry都不得使用 formal names。

`EngineeringMinimumControlProfile/v1` 是 D1 前置的最低执行合同，至少绑定：

- exact Studio engineering release、component inventory、ProductBuild、installed capability implementation/build digests；
- immutable `ExactQueryDataHandleV1`/DataIdentity、Reference/Control/Suite、policy/model/egress refs；
- current expected activation head、private response buffer、no-partial commit、eligible old-active preservation；
- PackageSafety、zero package code/network、closed query/tool surface、browser authority=0、reserved product wording和四维claim ceiling；
- Agent 对 raw bundle、AuthoringProfile、source/review bytes和control expected targets物理不可达。

它明确**不**声称 five independent VerificationAttempts、SEALED VRS、formal point-in-time Eligibility、durable ChannelScope ordering或disaster-safe restore monotonicity。Engineering mode 的 exact manifest无法开启 formal endpoints，formal manifest也不能把 Engineering receipts当作gate evidence。

### 4.3 Product process separation

建议单仓库、多个进程、共享 contracts。以下是 Product Target 的 logical layout；当前 discovery 只新增被 tracer 实际用到的目录，不一次性建立全部 services：

```text
apps/
  console-web/            React/TypeScript/Vite；descriptor-driven route migration
services/
  studio-api/             Studio product API
  agent-api/              Agent user API
  operator-api/           internal release/activation API
  model-gateway/          only service holding model key
  background-worker/      only when measured async jobs require it
packages/
  contracts/              Pydantic/JSON Schema/OpenAPI contracts
  kernel/                 lifecycle, identity, projection, evidence
  tabular-analytics/      bounded common operators
scenario-packages/
  adt/
  listing-sla-reference/
```

Studio 和 Agent 可使用同一个 Python wheel/image，但必须保留独立 API app、状态机、权限和发布节奏。

`ScenarioDistributionBundle` 只负责把 exact component bytes/refs 交付到目标环境；它没有业务 UI、独立 backlog 或 lifecycle，因此不会成为第三产品。

---

## 5. Complete Technology Stack

技术选择分为四种状态；`17_architecture_approval_and_stack_decision.md` 已把 React、PostgreSQL、S3-compatible storage 与 Kubernetes 从候选项提升为 implementation baseline：

- `ADOPT-NOW`：支持 dual-scenario discovery/portable tracer 的必要能力；
- `TARGET`：Governed/Durable Product Target 才需要的附加能力，不等于当前 dependency lock；
- `EXPERIMENT`：有触发条件、stop/continue test 的有界试验；
- `DEFER`：当前无 acceptance case，不进入 image/Compose/ROM。

| Concern | Scenario-portability track | Governed/Durable target | Decision |
|---|---|---|---|
| Frontend | TypeScript strict + React + Vite；ProductContext/safe descriptors | 同一构建物逐 route 扩展 | ADOPT-NOW baseline |
| Backend | Python 3.13、FastAPI、Pydantic 2 | same；SQLAlchemy/Alembic/psycopg for persistence | ADOPT-NOW baseline |
| Product state | PostgreSQL 17；filesystem/SQLite仅迁移与isolated-test兼容 | 同一事务底座增加formal authority schema | ADOPT-NOW baseline |
| Immutable artifacts | S3-compatible exact-version store；local/test MinIO | AWS S3/enterprise compatible adapter | ADOPT-NOW baseline |
| Demo facts/query | content-addressed Parquet + sandboxed DuckDB | QueryEnginePort to approved warehouse | now / future connector |
| Semantic identity | nonconformant canonical JSON EngineeringSemanticRelease | approved canonical JSON GSR | now / permanent formal target；never alias |
| Ontology graph | retain existing projection/SHACL regression；`graph_feature=off` by default | product-owned profile/shapes + bounded RDFLib query；enterprise adapter only on measured need | conditional experiment / defer triplestore |
| Agent framework | current typed bounded state machine | possible narrow LangGraph adapter only after experiment | now / defer |
| LLM | internal model-gateway → Qwen `qwen3.8-max` | approved provider adapter/profile | now / portable port |
| Async jobs | synchronous/bounded existing paths | PostgreSQL outbox worker only if acceptance requires | defer until needed |
| Vector retrieval | exact/full-text search | pgvector only with recall/latency evidence | defer |
| Deployment | Kubernetes；当前自有EC2使用k3s；Compose仅本地兼容 | 标准K8s/Helm-compatible配置；HA另行验收 | ADOPT-NOW baseline / hardening later |
| Access | HTTPS + shared demo session | OIDC/enterprise IAM | now claim-limited / future |

### 5.1 Frontend

| Status | Layer | Choice | Why / boundary |
|---|---|---|---|
| ADOPT-NOW | Context/descriptor seam | React + TypeScript strict + Vite + typed `ProductContextV1` / safe presentation descriptors | 证明同一 frontend build 能渲染两个场景；删除 ADT oracle/fixture/browser calculator；framework本身不构成通用性证据 |
| ADOPT-NOW | API boundary | generated JSON Schema/OpenAPI types where practical + runtime schema check | browser 只做 UX/transport validation，backend 才是 authority；schema mismatch readiness fail |
| ADOPT-NOW | Charts | current chart components or ECharts only when a descriptor acceptance case needs it | descriptor只能选择 product-owned component enum/fields/budgets，不能注入 HTML/JS/CSS/expression |
| ADOPT-NOW | Tests | current smoke + Playwright true API desktop E2E | ADT/Listing context、Dashboard、Ask、Studio、failure、claim ceiling、browser fallback=0 |
| ADOPT-NOW / route-by-route | Language/framework/build | TypeScript strict + React + Vite | 从第一条纵向切片开始；`tsc --noEmit` 独立执行；每条 route 有feature-flag/legacy rollback，具体minor在lockfile冻结 |
| ADOPT-NOW / route-by-route | Routing/server state/forms | React Router + TanStack Query + React Hook Form + Zod boundary | 不缓存authoritative answer为offline truth；保持`/ontology-studio/`与`/ontology-agent/`独立入口和双向link |
| DEFER | Ontology/process graph | React Flow | 只有 safe graph editing 成为真实 MVP task 才引入；当前 catalog/trace table 足够 |
| DEFER | Full i18n platform | i18next-compatible catalog | 当前先用 product-owned zh/en trust messages + scenario domain labels；package不能覆盖 reserved keys |

React 已进入 implementation baseline，但迁移仍按纵向切片而非 big-bang 执行。当前视觉 tokens、login、导航和真实 API flow 先做 characterization 并复用；每个进入 scope 的 route 同时锁定依赖、真实 API E2E 与回滚开关。

### 5.2 Backend and APIs

| Status | Layer | Choice | Why / boundary |
|---|---|---|---|
| ADOPT-NOW | Language/API | Python 3.13 + FastAPI | 复用现有 image/API；目标 ARM64；不因 generalization 重写 |
| ADOPT-NOW | Contracts | Pydantic 2 + JSON Schema 2020-12 | closed schemas、`extra=forbid`、unknown version fail closed |
| ADOPT-NOW | Persistence boundary | explicit repositories/ports + PostgreSQL implementation；filesystem/SQLite compatibility adapters | 第一条新架构纵向切片即运行PostgreSQL；同一conformance suite覆盖迁移与isolated tests |
| ADOPT-NOW | Serialization | frozen canonical-JSON profile + SHA-256 | safe YAML parse 后生成 canonical JSON；YAML bytes不拥有发布 authority |
| ADOPT-NOW | API client | generated or schema-checked DTOs | browser不手写 drifting authoritative DTO |
| ADOPT-NOW | Logging/telemetry | allowlisted structured JSON + lightweight trace IDs/metrics | 不记录 raw prompt/row/SQL/secret/locator；当前 stdout exporter足够 |
| ADOPT-NOW | Persistence implementation | SQLAlchemy 2 stable + Alembic + psycopg 3 + PostgreSQL 17 | 产品状态、history、read model和工程版release/runtime head从首条slice进入；formal scope-order/commit语义仍受Frozen Shared Contract约束 |
| TARGET only if async acceptance exists | Durable worker | PostgreSQL outbox/job lease | 不预装 Redis/Celery；没有真实 async job 时也不创建通用 worker platform |
| DEFER | Full observability backend | OpenTelemetry collector/backend | SDK/port可保留，部署与运营平台待 workload/ops 决定 |

API 分层：

- `/studio-api/v1/*`：intake、workspace、observation、decision、validation、release；
- `/agent-api/v1/*`：context、dashboard、question family、analyze、execution/evidence；
- `/operator-api/v1/*`：prepare、certify、activate、rollback、verify；只在内部网络；
- `/model/v1/*`：内部 model gateway；browser 不可访问。

### 5.3 Operational database

**新产品 implementation baseline 选择 PostgreSQL 17.x；当前已部署 demo 的文件/SQLite 状态按显式迁移策略处理。** 选择原因：

- 是当前仍受官方支持的稳定版本，支持期至 2029；
- 比刚发布的 major 更保守，适合自管容器和未来 managed service；
- JSONB、事务、row-level locking、advisory lock、full-text search 足以支持 Governed General Demo；
- 产品合同不绑定某一 major；PostgreSQL 18 compatibility 只有在独立 acceptance/CI budget 获批后才加入，不阻塞当前 ARM64 demo。

主要表域：

```text
studio_workspace
intake_submission / intake_asset / source_anchor
observation_set / observation / review_decision
draft_revision / semantic_decision / validation_run
governed_semantic_release / artifact_ref
runtime_snapshot_payload / verification_attempt / sealed_vrs
authority_decision / policy_decision / eligibility_decision
channel_scope_order / activation_record / revocation_record
execution / fact_manifest / claim / evidence_projection / result_release_commit
llm_run / engineering_demo_response_commit / automatic_off_latch
durable_job / outbox_event / audit_event
```

设计规则：

- mutable head 与 immutable history 分表；
- immutable envelope 使用 JSONB + digest，但常用 identity/scope/status/time 关系化并建立约束；
- governance draft CAS 使用 expected revision/head + transaction；
- Product Target 中每个 ChannelScope 有唯一 `authority_sequence + channel_eligibility_epoch + active_vrs_ref + revocation_high_watermark` row；activate、revoke、任何可令ACTIVATE/PRE_QUERY/RESULT_RELEASE/EVIDENCE_READ从ALLOW变DENY的scope-local policy/authority mutation、以及ResultReleaseCommit锁定同一row/等价serializable domain、比较exact expected state并原子append/bump；
- external immutable policy/authority decision必须带exact digest与expiry；ResultReleaseCommit在同一DB transaction使用database time验证`commit_time < min_expiry`。无法进入ChannelScope顺序域或不可重读的revocation/policy source使commit fail closed；
- HTTP 只在 ResultReleaseCommit 事务成功后读取并释放 committed projection bytes；commit 前 analytic bytes=0；
- payload digest 不包含自己的 digest、后续 attestation 或 mutable status；
- 大型 attachments、component/bundle bytes、Parquet、raw provider response 不进 PostgreSQL；
- raw provider response 默认不持久化；需要 eval 时进入隔离、短 TTL artifact namespace。

迁移必须先完成 authoritative-state inventory、idempotent import、shadow compare、single-writer cutover、expand/migrate/contract、backup/restore与failure injection；不能让旧 files 与 PostgreSQL 同时成为 head authority。新功能不得继续扩张文件/SQLite权威面。

`pgvector` 为 `DEFER`：未来可用于获准文本的候选检索，但永远不是 Ontology truth、metric resolution 或 policy authority。只有 recall/latency evidence 与独立 acceptance case 成立时才进入 dependency lock。

### 5.4 Artifact store

通用 artifact port 只注入 installer/projector/operator，不注入 Agent API 进程：

```python
class ArtifactStorePort(Protocol):
    def begin_publish(self, intent: ArtifactPublishIntent) -> PublishLease: ...
    def stage_and_promote(self, lease: PublishLease, body: bytes) -> ArtifactRef: ...
    def read_back(self, lease: PublishLease, ref: ArtifactRef) -> VerifiedArtifact: ...
    def commit_ref(self, lease: PublishLease, ref: ArtifactRef, expected_head: HeadRef) -> CommitReceipt: ...
    def abort(self, lease: PublishLease) -> None: ...
    def get_exact(self, ref: ArtifactRef) -> bytes: ...
```

`ArtifactPublishIntent` 绑定 exact key/digest/size/media/schema、action、scope、owner、lease token、expiry与state。固定状态机：

```text
durable INTENT + lease
→ stage / verify / atomic promote
→ read-back exact bytes
→ authority transaction compare live intent + expected head
→ append exact ref and consume lease as COMMITTED
→ release operational lock
```

authority append与`COMMITTED`转换必须是同一transaction/等价CAS。GC只可处理明确`ABORTED/EXPIRED`、无active lease且在权威index第二次compare仍无引用的对象；已commit对象永不由orphan GC删除。baseline S3 adapter使用exact version + PostgreSQL durable intent row；local filesystem adapter仅用于isolated tests/迁移兼容并使用SQLite/file-lock的进程间durable lease，不能用in-memory flag。process death、lease expiry、clock jump和DB retry都必须收敛到`authoritative_ref ⇒ exact object exists and read-back digest matches`。

实现：

- local/test：MinIO S3-compatible bucket，versioning enabled；CI可使用明确标注的in-process/fake adapter做port conformance；
- 当前自有EC2 demo：k3s内MinIO或AWS S3，均使用exact version ID + SHA-256；
- Governed/Durable/customer target：AWS S3-compatible object store或企业artifact registry adapter，另有off-host authority high-watermark/checkpoint。

PostgreSQL authority index只在artifact已durable/read-back verified且publish lease仍有效时append exact ref；DB失败留下受lease/expiry管理的orphan，不留下可解析权威ref。ResultReleaseCommit也遵守同一协议。S3 Versioning用于恢复accidental overwrite，不替代product-level immutable digest/CAS。Object Lock、KMS signature和legal retention后置到生产安全方案。

### 5.5 Fact data and query engines

- Demo fixture：CSV 可作为 intake/source evidence；prepare 将运行副本转换/导入为 **content-addressed、read-only Parquet object**，不直接查询 mutable intake path；
- Local analytic engine：DuckDB `>=1.4,<2`；
- join-heavy、重复查询数据可加载到 DuckDB database；简单 scans 直接 query Parquet；
- Product PostgreSQL 不承载客户事实表；
- 企业目标通过 `QueryEnginePort`：DuckDB、PostgreSQL、Trino/Spark/warehouse adapter；
- compiler 只接受 typed `AtomicQueryContract`；scenario semantic model只引用 opaque logical binding IDs，Deployment adapter把它们解析为预注册、dialect-validated、正确 quote 的 identifiers/immutable dataset handles；
- DuckDB 禁止 external access、extension install/load/autoload、`ATTACH`、`COPY`、任意 file/network table function；以只读 UID/volume、statement timeout、memory/CPU/row/byte budget 和 result schema validation形成第二层 sandbox；
- Query session 必须消费 `ExactQueryDataHandleV1`，而不是在precheck后重新解析普通path；receipt的`observed_data_identity`必须从**实际被查询的 sealed private object**重新计算并绑定同一query session；任一时点与runtime binding identity不同，answer bytes=0；
- existing SQL 是 source evidence/对照材料，不能直接作为 Agent 可执行 SQL。

Local `ExactQueryDataHandleV1` 固定顺序为：按runtime binding取得expected object/version并获取store pin/lease → `openat/O_NOFOLLOW` exact source version → 从该descriptor复制到private object并同步计数bytes → 对private object施加不可逆write seal（例如sealed memfd；仅`chmod 0444`不算seal）→ **对sealed、实际将被查询的bytes重新计算digest/size/schema并与expected DataIdentity比较** → 只有相等时才把同一sealed object注册给DuckDB → receipt从该sealed object digest/version与同一query-session ID生成observed identity → commit/abort后释放lease。source fd上的precheck只能early reject，绝不能成为observed identity或跳过sealed-object认证。父目录alias、公开content-addressed path或resolver在query开始后不得再次解析；source precheck后即使存在retained writer fd、ABA rename、in-place overwrite或GC/recreate，也只能得到认证后的A control或safe failure，禁止“B/mixed result + A receipt”。

DuckDB 官方支持读取Parquet并进行projection/filter pushdown；Parquet同时避免DuckDB内部storage format跨版本兼容成为data contract。企业adapter必须在同一read transaction/session使用engine-enforced snapshot/time-travel token；无法寻址历史数据时必须降低replay claim，不能用pre/post watermark或certification identity冒充execution identity。

### 5.6 Ontology technologies

| Concern | Choice |
|---|---|
| Human authoring | safe-profile typed YAML split files；duplicate key/tag/alias bomb rejected |
| Semantic source identity | exact mode one-of：Engineering=`EngineeringSemanticReleaseRef` canonical JSON subject + explicit non-formal limitations；Governed=approved `GSRRef` canonical JSON subject + frozen canonicalization profile；两者不可cross-fill |
| Portable semantic projection | conditional：JSON-LD + deterministic IRI-only canonical N-Quads；Turtle 仅 human-readable export |
| Graph validation | conditional SHACL Core with pySHACL；exact product-owned ShapeSet only |
| Graph query | conditional allowlisted SPARQL 1.1 over one exact semantic-release-scoped RDFLib graph |
| Relational lookup | PostgreSQL normalized indexes / JSONB |
| Business calculations | SQL + deterministic operators |
| Inference | no OWL reasoning in release/runtime critical path |

限制：

- `SemanticProjectionProfileRef`、`ShapeSetRef`、projector build和query-template registry均由ProductBuild/Shared Contract owner批准；bundle内自带shapes/report永不成为gate authority；
- 禁止 SHACL-JS 和 package-supplied executable rules；
- 禁止 blank-node/remote context/network dereference；projector build/profile/graph digest进入 payload/evidence；
- SHACL 证明 graph structure/constraints，不证明指标业务正确；
- SPARQL 只运行 product-owned allowlisted templates；禁止 UPDATE、SERVICE、LOAD/remote URI，并有 time/result budget；不访问事实数据，不产生业务数值答案；
- OWL 可作为未来 export vocabulary，但不参与首版 policy、formula 或 query execution；
- graph source、projection receipt与cache key必须包含`semantic_release_kind + full exact semantic_release_ref/digest + projection profile + projector build + graph digest`。Engineering只接受`EngineeringSemanticReleaseRef`且formal registry/endpoint writes=0；Governed只接受`GSRRef`；both/none/cross-fill/wrong endpoint在projection前失败。cache可丢弃重建，不使用mutable latest；
- 每个启用的投影profile把promised fields/edges与typed dependency index做differential set-equality；SHACL PASS不能替代projection fidelity PASS；`graph_feature=off`时graph-dependent claim固定为`UNAVAILABLE`且不引入SPARQL/runtime graph dependency。

### 5.7 Agent and LLM stack

| Layer | Choice |
|---|---|
| Agent orchestration | current custom typed state machine；当前不新建 broad framework port |
| LLM provider | Alibaba Cloud Model Studio / Qwen `qwen3.8-max` through provider adapter |
| Model API | OpenAI-compatible HTTPS from internal model-gateway only |
| Tool model | closed typed capability registry resolved from activated/eligible RuntimePackageView |
| State | explicit Pydantic `AgentRunState`; no hidden message memory |
| Session memory | off by default; only allowlisted interaction metadata |
| Result rendering | closed AnswerClause/Presentation contract, deterministic |
| Optional future | narrow LangGraph adapter only after bounded experiment；never owns authority |

不直接采用 LangGraph/DeepAgents 的原因：

- 当前 bounded orchestrator 已有执行、evidence、no-partial、commit 和 automatic-off tests；
- framework checkpoint 不等于 product authority/evidence commit；
- 当前主要问题是scenario portability，不是缺少loop framework；
- 把 deterministic gates 藏进 agent graph 会降低可审核性。

未来采用 LangGraph 的 reopen 条件：

- 第二案例需要结果依赖的三步以上动态 branching；
- 用户需要暂停、恢复、人工批准后继续；
- custom state machine 的变更成本和 fault rate 被数据证明高于 adapter migration；
- LangGraph checkpoint 仍只存 orchestration state；resolver、policy、tool execution、Facts/Claims、Projection、VRS、Evidence 与 ResultReleaseCommit authority全部留在 deterministic services。

---

## 6. Scenario Components and Distribution Contract

### 6.1 “ADT Ontology 包”是交付视图，不是 compound authority

业务上可以把一套 ADT 内容称为 “ADT solution package”，但技术上必须拆成有独立 owner、schema、digest 和 lifecycle 的 components：

| Component | Accountable product/role | Contains | Explicitly excludes |
|---|---|---|---|
| `AuthoringProfile` | Studio Domain Owner | intake manifest、typed slots、safe source selectors、editor/patch descriptors | GSR approval、Agent runtime、control truth、raw customer content |
| `EngineeringSemanticRelease` | Studio Domain Owner under exact Engineering manifest | current canonical semantic subject + engineering release checksum + explicit nonconformant limitations | Semantic Approval/PUBLISH authority、formal GSR endpoint/name、environment、control、channel |
| `GovernedSemanticRelease` | Studio Release authority after Semantic Approval | canonical semantic subject、lineage/decisions、requirements、limitations、derived projection refs | environment/data identity、runtime build、control/suite、channel、activation |
| `SemanticProjectionProfile + ShapeSet` | Shared Contract / ProductBuild owner | promised typed fields/edges、projector build、exact SHACL shapes、query-template registry | scenario-supplied gate policy、precomputed PASS authority、facts |
| `AgentExperienceProfile` | Agent Domain Owner | question families、answer obligations、safe dashboard descriptors、product-owned prompt/task refs、typed domain labels/examples | system prompt override、tool implementation、policy bypass、secret |
| `ReferenceEvaluationBundle` | Truth/Control roles | ReferenceManifest refs、ControlManifest、suite、mutations、synthetic fixture refs、oracle/evaluator provenance | semantic approval、runtime implementation authority |
| `DeploymentBinding` | target environment operator/Data Approver | environment、opaque resource refs、DataIdentity expectation、query/model/policy refs、feature flags | secret bytes、activation channel、mutable latest |
| `ScenarioDistributionBundle` | Delivery tooling | ordered exact refs and optionally verified component byte copies | any new business/runtime/activation authority |

正式 Governed 对象图：

```text
AuthoringProfile → Studio workflow → GSR

GSR + AgentExperienceProfile + ProductBuild/CapabilityRegistry
+ DeploymentBinding/DataIdentity/Policy
+ ReferenceEvaluationBundle
→ RuntimeSnapshotPayloadManifest
→ five exact PASS VerificationAttempts
→ SEALED VRS
→ append-only Activation(channel)
→ point-in-time Eligibility
→ RuntimePackageView
```

Engineering对象图按§4.2的`EngineeringMinimumControlProfile/v1`执行，不能把`EngineeringSemanticRelease`填入上述GSR位置。

Agent的可达对象只从`RuntimePackageView`或`EngineeringRuntimeView`开始。Installer/projector在独立service identity与storage namespace中读取distribution/authoring/reference-control bytes，生成closed immutable runtime projection后写入Agent专属read-only namespace。Agent container不挂载raw bundle、authoring、source/review或control-expected namespace，也不持有其credential；Agent代码依赖只能注入`RuntimeViewStorePort.get_exact_runtime_view(...)`与`ExactQueryDataHandleV1`，不能import/inject通用`ArtifactStorePort`。cross-scope、wrong-class和missing读取对普通调用者返回不可区分的safe error。

closed RuntimeView只包含执行所需的typed semantic projection、exact capability/build refs、safe AgentExperience fields、opaque data binding + expected DataIdentity、policy/model/egress refs、claim ceiling和limitations；明确排除AuthoringProfile、ClearedInput/source bytes、review/Decision rationale、Control expected targets、fixture generator inputs、raw physical schema/locator、bundle inventory和secret。

### 6.2 Distribution bundle example

Scenario-Portable Demo 采用 deterministic ZIP `.osb`（Ontology Solution Bundle）；OCI/S3 registry 只作为以后 transport adapter，不改变 component authority：

```text
adt-reference.osb
├── distribution-manifest.json
├── components/
│   ├── authoring-profile.json
│   ├── {engineering-semantic-release.json | governed-semantic-release.json}  # exact one-of
│   ├── agent-experience-profile.json
│   └── reference-evaluation-manifest.json
├── projections/                  # only when graph_feature=on；off时目录必须不存在
│   ├── semantic.nq
│   └── semantic.jsonld
└── fixtures/                    # constructed-synthetic only
    ├── data-manifest.json
    └── sha256/<digest>.parquet
```

`distribution-manifest.json` 必须声明`mode=ENGINEERING|GOVERNED`和exact one-of semantic ref，只记录full typed refs、media type、size和digest。Bundle digest证明运输完整性，不替代任何component digest/approval。仅当`graph_feature=on`时，bundle内projection才可作为可丢弃transport copy；installer必须从mode-matched exact semantic subject（Engineering=`EngineeringSemanticReleaseRef`；Governed=`GSRRef`）用product-owned projection profile/build重新生成或byte-verify，并重跑exact product-owned ShapeSet与fidelity differential，projection receipt/cache必须绑定该full typed ref，预计算report不得进入gate。`graph_feature=off`时，bundle/installed inventory/runtime lock都不得出现projection、ShapeSet、SPARQL或graph-query dependency；只保留现有ADT source-tree regression，不把它复制成新scenario runtime surface。只改presentation、control、fixture或authoring descriptor时，formal GSR digest必须保持不变；相应runtime payload/VRS或Engineering snapshot/Studio profile identity按依赖变化。

### 6.3 Exact capability references

Scenario component只能请求 product-owned closed registry中的 `CapabilityContractRef`：

```yaml
capability_id: tabular.aggregate
contract_version: 1
input_schema_digest: sha256:...
output_schema_digest: sha256:...
semantic_precondition_digest: sha256:...
failure_policy_digest: sha256:...
obligation_digest: sha256:...
conformance_suite_digest: sha256:...
```

prepare 将上述要求解析为 exact installed implementation/build refs并写入 payload。相同 `id@version` 但任一 digest不同是 integrity conflict；package不能自带tool schema/implementation或用range/latest解析。

### 6.4 PackageSafetyProfile/v1

Install 固定按以下顺序：

```text
trusted INSTALL intent binds expected raw artifact digest/scope
→ isolated staging
→ raw size/digest check
→ safe archive inventory/extraction
→ safe YAML/JSON closed-schema parse
→ canonical JSON + component digest verification
→ content-addressed immutable promote/read-back
→ PostgreSQL/file authority index append
```

安全 profile 至少要求：

- path 使用 UTF-8 NFC、case policy、closed inventory；拒绝 absolute、`..`、duplicate/case collision、symlink/hardlink/device；
- entry count、single/expanded bytes、compression ratio、path depth/length 有上限；
- YAML 1.2 safe subset；duplicate key、unknown tag、alias/depth bomb、implicit ambiguous date/number全部拒绝；
- Formula AST、graph、selector、descriptor 有 node/depth/cycle/type/unit/fan-out budget；selector使用closed grammar，不允许 package regex/template expression；
- JSON-LD remote context、network URI、SHACL-JS、SPARQL SERVICE/UPDATE和任何隐式下载全部拒绝；
- install/validate阶段 network、model和Query Engine call count必须为0；
- package/code 仍禁止 Python、JavaScript、shell、WASM、arbitrary SQL/HTML/CSS和secret；
- product-owned outcome/trust/claim message keys不能被scenario override；scenario只提供有长度/Unicode/URL约束的domain labels/help。

### 6.5 DeploymentBinding is not Activation

Deployment binding采用closed、mode-discriminated one-of，而不是一个允许`gsr_ref`和`engineering_semantic_release_ref`随意混填的宽schema：

- `ontology-engineering-deployment-binding/v1`：`mode`固定为`ENGINEERING`，必含exact `engineering_semantic_release_ref`，禁止`gsr_ref`；
- `ontology-governed-deployment-binding/v1`：`mode`固定为`GOVERNED`，必含exact `gsr_ref`，禁止`engineering_semantic_release_ref`，并须解析到Frozen Shared Contract兼容的formal Binding subject；
- transport/API envelope只允许上述exact one-of。both、none、unknown mode、wrong ref class、cross-fill和把一种binding提交到另一种endpoint都在任何snapshot assembly前fail closed。

以下是 Governed-only 示例：

```yaml
contract: ontology-governed-deployment-binding/v1
mode: GOVERNED
environment_id: ec2-demo-cn
workspace_id: workspace.adt.reference
gsr_ref: { object_id: gsr.adt, version: 2.0.0, digest: sha256:... }
resource_bindings:
  source.trade_fact:
    connector_id: duckdb.parquet.local
    resource_ref: dataset-object.adt.trade-fact
    expected_data_identity: sha256:...
query_engine_ref: { id: duckdb.local, build_digest: sha256:... }
model_profile_ref: { id: qwen38max.demo.v1, digest: sha256:... }
egress_decision_ref: { id: egress.adt.demo.v2, digest: sha256:... }
feature_flags: { agent_llm: true, studio_llm: true }
```

Engineering binding使用同一resource/model/egress字段形状，但header必须是：

```yaml
contract: ontology-engineering-deployment-binding/v1
mode: ENGINEERING
engineering_semantic_release_ref: { object_id: engineering-release.adt, version: 2.0.0, digest: sha256:... }
```

`resource_ref` 是 target-local opaque alias，不是 `file://` 路径。Secret只进入获准 gateway/connector的read-only secret file/provider。`activation_channel` 明确禁止出现在两种Binding及payload/VRS/snapshot；切换channel必须新建对应mode的append-only ActivationRecord。

### 6.6 Reference truth and evaluation independence

ReferenceEvaluationBundle可以携带verified copies，但其truth authority来自先冻结的`ReferenceManifest`，而不是bundle author：

- 每个candidate truth先有非bundle/oracle的ClearedInput与Truth Owner；
- ControlManifest、suite denominator/expected/tolerance、mutation profile和reference manifest在fixture/runtime之前冻结；
- Truth Owner与Independent Control Reviewer必须是不同自然人；Fixture Author不得兼任Reviewer；
- fixture generator/runtime不得import expected targets；runtime output不能反向生成control；
- control/suite/data/evaluator任一变化产生新digest并使旧Control PASS不适用；
- independent evaluator/recomputation必须能捕获fixture/runtime共享的calculator defect；
- second scenario分别报告correctness、coverage、Clarify、Refuse、Failed、Claim coverage和leakage，不能只报告E2E green。

---

## 7. Ontology Studio Design

### 7.1 User flow

```text
Create/Open Workspace
→ Register Cleared Input Bundle
→ Parse common template + register attachments
→ Produce typed ObservationSet + Source Anchors + Gaps
→ Human accept/edit/reject and record Decisions
→ Materialize Candidate Semantic Graph
→ Validate structure/semantics/source closure/[if graph_feature=on] SHACL + fidelity differential
→ exact Semantic Approval + PUBLISH authority
→ Publish immutable GSR only
```

以上是Governed formal flow。Engineering mode复用Source→Observation→Human Decision→Draft→Validation，但随后只可通过独立engineering endpoint生成`EngineeringSemanticRelease`及nonconformant limitations；它不执行Semantic Approval/PUBLISH authority action，不写GSR registry，也不让engineering receipt进入formal evidence chain。

### 7.2 Common intake

继续遵守 External Review Team 能力前提：

- 需求与指标逻辑按我们提供的简单模板转写；
- 数据模型、数据字典、sample/enums 和现有 SQL 作为文件或安全描述登记；
- 不要求 External Reviewer 填 RDF/OWL/SHACL/Formula AST；
- 初版不要求自动解析任意 Word/Excel/SQL；
- parser 无法确认的内容产生 `Missing/Gap/Conflict`，不能猜。

Discovery只实现D0 source manifest实际调用的两个exact adapters，用它们暴露差异；不能在Listing运行证据前命名为`Common*`或宣称universal parser：

- `requirements-template.zh-en/v1`；
- `metric-logic-template.zh-en/v1`。

数据模型、数据字典/sample-enum和SQL在D1只作immutable registered attachments + human decisions；`DataDictionaryCsvXlsxAdapter`、`DataModelDescriptorAdapter`与`SqlEvidenceRegistryAdapter`均为`DEFER`，只有exact hero task/source manifest需要其结构化输出且WBS单独批准时才提升。首版SQL始终只是checksum/evidence，不自动成为execution truth。

### 7.3 Evidence-backed authoring model

以下是待 dual-scenario discovery 验证的最小 common candidate model，不是先验冻结的通用 compiler：

```text
CandidateNode(object_type, object_id, proposed_fields, anchors, status)
CandidateEdge(predicate, from_ref, to_ref, anchors, status)
CandidateConflict(subject_ref, alternatives, blocking)
SemanticDecision(subject_ref, selected_value/ref, approver, evidence)
DraftOperation(op_type, target_ref/path, typed_value, source/decision_ref)
DraftRevision(base_digest, ordered_operations, result_digest)
```

AuthoringProfile slot manifest 可声明：

- slot ID、candidate object/path；
- source selector；
- value kind；
- required/optional；
- allowed refs/values；
- validator IDs；
- allowed draft operation；
- missing behavior。

Discovery 阶段 ADT/Listing exact adapter可以临时拥有自身 slot translation；每项差异进入 core-change ledger。只有两个场景等价使用的 node/edge/decision/patch primitive才提升到 common code。最终 common build 中除显式migration allowlist外不得出现 `metric.definition`、`mapping.amount`、ADT/Listing IDs。

### 7.4 LLM in Studio

LLM 可做：

- 从已批准 projection 提出 typed observations；
- 标识可能的对象、指标、规则、映射和 Gap；
- 帮助生成给业务方的 clarification questions；
- 比较现有 draft 与新材料，提出 change candidates。

LLM 不可：

- 读取 registered-not-cleared attachments；
- 自动确认业务定义；
- 自动形成 Decision；
- 自动 publish；
- 补齐 Missing/Withheld；
- 将 SQL text、物理 schema、raw sample 发给模型，除非另有 exact approved projection。

ProductBuild拥有system/task/tool prompt合同。AuthoringProfile只能提供typed domain vocabulary、field labels、source anchors和few-shot data examples；它们作为untrusted data进入prompt，不能修改provider、tools、policy、budget或output obligations。引号、delimiter或“data”标签**不是**prompt-injection安全边界；安全性来自positive ModelInputProjection、closed tool/query registry、deterministic metric/claim validators、budget和no-partial commit。multilingual/encoded/bidi恶意labels/examples最多导致bounded safe failure，不能扩大tool/egress/commit authority。任何instruction-bearing PromptModule必须有独立digest、Disclosure/Egress approval、evaluation和rollout，不能因bundle install自动生效。

Source selector永远只能在ClearedInput/Disclosure允许字段与ModelInputProjection的交集内取值；profile selector不能扩大classification、purpose或egress范围。

### 7.5 Studio views

- Intake completeness / missing overview；
- Source → Observation → Decision trace；
- Candidate catalog 和 safe graph view；
- Gap/Conflict inbox；
- version diff；
- validation/readiness dashboard；
- release history。

Studio Dashboard 是治理工作台，不展示客户业务事实 Dashboard。

Studio不会发布AgentExperienceProfile、ReferenceEvaluationBundle或DeploymentBinding。它可以显示这些外部component的derived readiness view，但view不是identity-bearing authority。

---

## 8. Ontology Analytic Agent Design

### 8.1 User journeys

1. 打开 AgentExperienceProfile-driven Dashboard，看稳定 KPI、趋势、分组和限制；
2. 选择登记问题或输入允许的自然语言变体；
3. 系统绑定 intent、metric、scope、period、dimension；
4. 有歧义时 Clarify，不访问数据；
5. 不支持/越权时 Refuse，不访问数据；
6. 生成 closed typed Analysis Plan；
7. 执行 typed tools/SQL；
8. 形成 Facts、Claims、Evidence；
9. final reread/commit 后展示答案；
10. 用户查看口径、范围、版本、数据身份和 safe lineage。

### 8.2 Capability grammar：先发现，再冻结

当前 ADT 已验证的候选 primitives如下；它们在 Listing discovery前只是`candidate common registry`，不能因改成generic名称就自动进入kernel：

```text
tabular.aggregate/v1
metric.derive/v1
scope.compare/v1
group.delta-contribution/v1
group.rank/v1
decomposition.sequential/v1
evidence.lookup/v1
```

每个 operator 定义：

- typed input/output schema；
- supported metric semantic type：value type、unit dimension、base/result grain、additivity/semadditivity、time aggregation、population/denominator、null/zero policy、allowed dimensions；
- required binding features；
- failure codes；
- policy obligations；
- deterministic implementation/build ID；
- conformance suite与reconciliation invariant。

`group.delta-contribution/v1` 默认只接受其precondition允许的additive/decomposable metric。SLA breach rate等非加性ratio不得把分组rate delta直接相加；在weighted numerator/denominator decomposition完成独立control与reconciliation实验前必须`UNSUPPORTED`。Sequential decomposition的method、factor order和build identity必须进入Plan/Claim/Evidence。

ADT capability graph 组合：

```text
aggregate eligible turnover
+ aggregate trading-day count
→ derive ADT
→ compare Q3/Q4
→ group delta by segment
→ rank contribution
→ optional sequential decomposition
→ claims/evidence
```

Listing discovery很可能暴露 event ordering、duration、as-of population、business calendar或state-transition能力。发现这些缺口时先产生 `MissingCapabilityRequest`，Query Engine access=0；实验可以以 portability claim失败结束，不能在live query临时执行arbitrary SQL或预埋case branch。

### 8.3 Agent orchestration

```text
TrustedRequest
→ Resolve exact scope/channel Activation + SEALED VRS
→ PRE_QUERY point-in-time Eligibility
→ project closed RuntimePackageView
→ Policy and boundary check
→ LLM or deterministic goal binder
→ closed BoundGoal
→ deterministic planner
→ bounded tool loop
→ fact/schema/reconciliation validation
→ Claim builder
→ allowlisted renderer
→ private response projection
→ RESULT_RELEASE point-in-time Eligibility
→ durable response commit in ChannelScope order
→ after commit release exact committed bytes
```

LLM 可以根据 tool results 选择下一步，但：

- tool set、iteration、token、time、row/byte budget 都由 active runtime 限定；
- model 不能改变 metric、formula、binding、population 或 policy；
- model output 不直接成为 displayed factual prose；
- deterministic renderer 只从 verified Claim/AnswerClause 生成 factual text；
- provider/schema/tool/deadline/revocation 失败，private answer buffer 丢弃；
- fallback 必须从原始 trusted request 重新进入 approved deterministic path，不能拼接 partial model state。

Scenario-Portable Engineering Demo继续使用现有 bounded engineering commit/activation seam并明确label；Governed Product Target才使用Frozen VRS/Eligibility/ResultReleaseCommit名称。两者不能通过class rename混称。

### 8.4 Dashboard and Ask relationship

- Dashboard：AgentExperienceProfile 定义稳定业务视图，确定性执行，可在 LLM off 时工作；
- Ask：处理探索、比较、拆解、追问和证据；
- Dashboard 的 card 可以生成一个 pre-bound question/action，但不能绕过 API；
- Ask 的结果可链接到 Dashboard filter state，但不修改GSR、ExperienceProfile或任何scenario component。

---

## 9. Data Architecture and Storage Formats

### 9.1 Data classes

| Data class | Canonical authority / format | Derived index/cache / query path |
|---|---|---|
| Human input templates | XLSX/DOCX/Markdown as ClearedInput artifacts | Studio intake adapters |
| Data dictionary/model | CSV/XLSX/YAML/Markdown registered artifacts | Studio structured parser/manual mapping |
| Existing SQL | `.sql` immutable artifact/checksum | human comparison; optional later parser |
| Candidate/draft/decision | PostgreSQL relational + JSONB envelope；legacy file/SQLite只作迁移来源 | Studio API/read models |
| Human authoring source | safe-profile split YAML | compiler input；not release authority |
| Approved semantic release | exact canonical JSON GSR bytes in Artifact Store + authority envelope/index | typed semantic index |
| Component artifacts | exact content-addressed bytes + own manifest/digest/owner | DistributionBundle inventory |
| RDF projection | conditional deterministic N-Quads/JSON-LD derived from exact semantic subject + product-owned projection profile/build | RDFLib/SPARQL droppable cache；off by default |
| SHACL shapes | exact product-owned `ShapeSetRef` + Turtle bytes | pySHACL conditional gate；bundle copy/report无authority |
| Demo facts | exact content-addressed read-only Parquet + DataIdentity manifest；CSV只作source | DuckDB executor/cache，不拥有data truth |
| Runtime heads/authority | PostgreSQL append/read models；formal target增加ChannelScope order | Agent resolver/runtime view |
| Facts/claims/evidence/commit | PostgreSQL envelopes + exact large artifact refs | evidence API |
| LLM metadata | allowlisted metadata in PostgreSQL | evaluation/operations |
| Raw LLM trace | off by default；exact approved encrypted short-TTL artifact | reviewer-only；absolute expiry/deletion receipt |

### 9.2 Data does not move by default

企业接入目标：

- GSR/ExperienceProfile 描述 logical contract、mapping/capability requirement和safe analytic surface；
- DeploymentBinding 绑定目标环境 opaque resource与data identity；
- QueryEngineAdapter 在客户已有平台执行聚合；
- 产品只接收 typed aggregate result/evidence，不默认复制 raw enterprise facts；
- PoC synthetic data是ReferenceEvaluation fixture，不代表生产数据移动方案。

### 9.3 Data identity

每个 runtime binding 与每次 query receipt 至少绑定：

- dataset ID/version/checksum 或 warehouse snapshot/watermark；
- schema fingerprint；
- row/grain uniqueness checks；
- time coverage；
- freshness captured_at；
- binding profile；
- validation/certification result。

Local demo的source文件先复制/转换到`sha256/<digest>`namespace，但content-addressed pathname、`0444`权限、source fd precheck与query前后path hash都不构成execution identity。`ExactQueryDataHandleV1`必须记录expected object/version、store lease、source handle、sealed query-object digest/size/schema和query-session ID；QueryEngine只能读取先sealed、再按实际bytes认证通过的同一private object，不能把source预检digest沿用为observed identity，也不能在precheck后重新解析alias/path。`QueryReceiptV1.observed_data_identity`由sealed query object + session生成。Warehouse在同一read transaction/session使用engine-enforced snapshot/time-travel token。任何expected/observed mismatch、跨水位join、handle失效或mid-query替换都禁止Engineering response commit/Formal ResultReleaseCommit。

DataIdentity验收必须包含四个barrier：source precheck后/private copy前、private copy期间/seal前、seal后/first scan前、scan后/receipt前。分别执行A→B→A rename、保留writer fd的in-place A→B→A overwrite、mid-copy overwrite、GC/recreate和same-key different bytes；认证必须针对sealed copy重新计算。完整A只可得到A control；任何B或mixed copy必须identity mismatch并safe fail且analytic bytes=0，禁止B/mixed结果绑定A receipt。

没有可寻址 source snapshot 时只能承诺当次aggregate evidence replay，不承诺相同历史数据重执行；界面和export必须显示该replay ceiling。

---

## 10. Ontology Storage and Query Strategy

### 10.1 Why not one graph database

Ontology 产品同时有四类不同任务：

1. authoring transaction；
2. immutable release identity；
3. graph dependency/lineage query；
4. large fact aggregation。

用一个 graph database 处理全部任务会把事务、发布、事实计算和知识导航混为一体。因此采用polyglot logical architecture。Scenario-Portable Demo即部署PostgreSQL + S3-compatible Artifact Store + DuckDB；Governed/Durable target在同一基础栈上补足formal authority/restore能力。RDFLib graph是进程内可重建cache，不是第四个authority database。

### 10.2 Write/read model

```text
Studio relational/write model
→ safe authoring compiler
→ exact mode one-of semantic source
   ├─ ENGINEERING: Human Decision → immutable EngineeringSemanticRelease
   │                (non-formal limitations；formal registry/endpoint writes=0)
   └─ GOVERNED: Candidate GSR subject → Semantic Approval/PUBLISH → immutable GSR
→ typed semantic/dependency index bound to that exact release ref
→ [only when graph_feature=on] exact product-owned projection profile + ShapeSet
→ deterministic RDF projection + SHACL rerun + fidelity differential
→ disposable semantic-release-scoped RDFLib graph cache
```

权威顺序：

```text
exact mode-matched canonical semantic subject
  (EngineeringSemanticRelease with non-formal limitations | approved GSR)
> typed semantic/dependency index
> conditionally verified generated RDF projection
> SPARQL query result
> LLM/vector retrieval result
```

上述顺序只表达derived graph的source precedence，不把Engineering release升级为formal semantic authority。Engineering graph-on的projection/cache/evidence全链必须保留`semantic_release_kind=ENGINEERING`和full `EngineeringSemanticReleaseRef`；Governed全链必须保留`semantic_release_kind=GOVERNED`和full `GSRRef`，两种cache entry不可复用。

### 10.3 Query routing

| Question | Engine |
|---|---|
| 某指标定义/版本/owner | exact GSR typed index / current repository or PostgreSQL |
| 某指标依赖哪些属性和规则 | typed dependency index；获批graph task可用SPARQL并做set-equality |
| 某 mapping 影响哪些 metrics | typed dependency index；获批graph task可用SPARQL |
| Q4 ADT 是多少 | SQL/DuckDB/warehouse |
| 为什么变化 | deterministic comparison/contribution/decomposition tools |
| 在材料中找可能相关描述 | approved full-text/optional vector retrieval |

当`graph_feature=on`时，SPARQL endpoint不直接公网开放；Agent/Studio只能通过product-owned allowlisted query IDs和typed params调用。parser/AST拒绝UPDATE、SERVICE、LOAD、remote URI和unknown template，并执行deadline/result budget。普通用户、scenario component和LLM都不能提交arbitrary SPARQL。默认off时不创建endpoint/dependency，graph-dependent feature返回`UNAVAILABLE`。

### 10.4 Graph feature / future store reopen

当前不预建`KnowledgeGraphPort`。如果D3预登记一条用户可见的lineage/impact任务，则在product-owned query service内部用单一RDFLib实现：exact query ID、typed params、ShapeSet/Profile/build refs、typed-index set-equality、latency/result budget和claim/evidence检查缺一不可。无该任务时，只保留现有projection/SHACL regression资产，不新增双序列化、SPARQL template或runtime graph surface。

只有出现第二个真实graph backend、标准endpoint要求或下列measured workload时，才从已经存在的query service抽出窄port；不能为单一RDFLib实现预建wide abstraction。任何未覆盖的canonical semantic construct要么在graph feature publish前fail，要么feature明确`UNAVAILABLE`，不得静默漏edge。

Reopen dedicated triplestore discussion when：

- GSR graph超过单进程cache的容量/latency envelope；
- 多 workspace 跨 release federation 成为真实任务；
- enterprise Knowledge Center 要求标准 SPARQL endpoint；
- measured workload 证明 RDFLib/PostgreSQL dependency index 不足。

候选可包括企业已有 graph service、Apache Jena/GraphDB/Neptune 等，但当前不冻结。这些trigger只能启动一份**新architecture/catalog decision**；`P-GRAPH`、`P-KC`或任意graph/Knowledge-Center ID都不在§17.3的closed Gate B catalog中，不能靠一份proposal自注册为当前productization track。

---

## 11. API and Contract Design

### 11.1 Public context APIs

Frontend 不再内置 ADT identity，启动时读取：

```text
GET /agent-api/v1/context
GET /agent-api/v1/dashboard
GET /agent-api/v1/question-families
GET /studio-api/v1/context
GET /studio-api/v1/workspaces/{id}/editor-descriptor
GET /studio-api/v1/workspaces/{id}/catalog
```

Context 返回：

- product/build identity；
- exact one-of `GovernedSemanticReleaseRef | EngineeringSemanticReleaseRef`、active `VRSRef | EngineeringSnapshotRef`、AgentExperienceProfile和scenario distribution identities（只投影用户获准字段；两种mode不能同时出现）；
- 四维 claim ceiling：business truth、governance/conformance、identity/operations、portability；product/platform限制与scenario限制取最严格交集，scenario不能放宽；
- locale/messages；
- current activation/eligibility derived status，不使用persistent READY；
- allowed UI component descriptor versions；
- enabled product links。

### 11.2 Analysis API

```json
POST /agent-api/v1/analyses
{
  "question": "...",
  "question_case_id": "optional",
  "requested_locale": "zh-CN"
}
```

Server 从 trusted session 获得 principal/workspace/purpose，不接受 request body 自报 role/scope。返回 closed outcomes：

- `ANSWERED`
- `CLARIFY`
- `REFUSED`
- `FAILED_PRECONDITION`
- `FAILED_EXECUTION`

所有非ANSWERED结果使用`FailureEnvelopeV1`/boundary envelope：closed reason family、retryable/retry-after、correlation ID、query/model call counts、analytic bytes、fallback flag和safe evidence handle。ordinary user与operator有不同allowlist projection；内部exception/path/object existence不出现在普通API。`ANSWERED`只在存在对应有效commit时成立。

### 11.3 Component and deployment APIs

- DistributionBundle install 是operator transport action，要求exact raw digest与INSTALL authority；它不创建semantic/runtime authority；
- Studio GSR publish不install、不prepare、不seal、不activate；
- Product Target payload assembly绑定exact GSR/components/DeploymentBinding/DataIdentity；caller显式选择five PASS refs后seal；
- activate使用exact VRS、ChannelScope与expected-current/epoch CAS；channel不从Binding读取；
- rollback 是新的 activation，不能修改历史；
- current active lookup 不允许 `latest` fallback。

Operator API在Scenario-Portable mode必须使用独立 engineering names/labels；只有authority manifest exact Approved/Frozen时才开放conformant GSR/VRS endpoints/claims。

### 11.4 Schema evolution

- API、GSR/component/distribution、artifact schema独立version；
- only additive compatible changes within a version；
- breaking change 产生新 schema/profile 和 migration adapter；
- unknown version fail closed；
- OpenAPI client 与 backend schema digest 进入 deployment smoke。

---

## 12. Security, Privacy and Trust Boundaries

### 12.1 Model egress

任何真实 model call，包括 retry/repair/eval，必须绑定：

- exact product/task/GSR/VRS-or-engineering-snapshot/experience/model profile；
- principal/scope/purpose；
- provider/account/region/model；
- allowed classification and fields；
- expiry、approver、decision=ALLOW；
- positive allowlist `ModelInputProjection`；
- wire payload digest receipt。

共享 Demo 账号默认只允许服务器登记的 synthetic question families 和 source projections。任意 paste 不能直接外发 Qwen。

### 12.2 Secret isolation

- Qwen key 只存在 model-gateway；
- browser、Studio、Agent、operator、worker 不持有 key；
- database password 和 query credentials 使用 container secret/env injection；
- logs/errors/traces 运行 secret canary；
- provider response 不进入 normal logs；
- scenario components、DistributionBundle 和 DeploymentBinding 不包含 secret bytes。

Engineering Demo优先使用只读file-mounted secret/secret provider与最小UID；若当前Compose继续env injection，必须邻接记录demo risk并通过全链canary。Raw provider response默认不持久化；例外`RawTraceDecision`必须绑定exact run/classification/audience/purpose、encrypted namespace、absolute expires_at、backup/export exclusion和deletion receipt，过期后review API也不可解析。

### 12.3 Injection and tool safety

- 模型看到的 source text 被标记为 untrusted data；
- system/task/tool contract由ProductBuild/approved PromptModule拥有，不从source text、scenario labels或bundle动态生成；
- tool names/schema来自activated RuntimePackageView + exact installed capability registry；scenario只能请求refs；
- no shell/filesystem/browser/arbitrary HTTP/Python/SQL tools；
- model output strict schema + deterministic semantic validator；
- unknown tool/ref/field fails closed。

### 12.4 Demo auth and future IAM

Engineering Demo保留当前HTTPS + shared demo credential + signed HttpOnly session cookie。它只证明访问控制存在，不宣称individual identity/audit；该限制属于product-owned四维claim ceiling，scenario messages不能隐藏。

未来通过 `IdentityContextPort` 接 OIDC/enterprise IAM；trusted principal 永远来自 server-verified session/token，不来自问题或 request body。

### 12.5 Product-owned four-dimensional claim ceiling

| Dimension | Scenario-Portable Engineering Demo wording |
|---|---|
| Business truth | constructed-synthetic；not customer/customer validated |
| Governance/conformance | bounded engineering controls；not full Stage 1 governed-evidence conformant |
| Identity/operations | shared demo account；not individual audit；temporary ingress/no SLA；not production-ready |
| Portability | only exact ADT + exact second synthetic scenario on stated build/capability/source/presentation ceiling；not arbitrary enterprise ontology onboarding |

Product context把product/platform和scenario limitations取最严格交集。Scenario component只能增加限制，不能改写reserved trust/outcome keys。以上四维必须在Agent主结果、Studio主视图、evidence replay/export、operator receipt、runbook和presenter script邻接可见；不能只藏在hover/drawer。

---

## 13. Degradation, Fallback and Rollback

### 13.1 Principles

- degradation 只能减少能力，不能降低 correctness/security gate；
- fallback 必须重新从 trusted request 开始，不能拼接 partial model state；
- stale/cached business result 默认不可显示为 live；
- failed new candidate不得部分生效；old active只有在exact bytes仍可读取且当次Activation/Revocation/Policy/Eligibility为ALLOW时才可继续服务；
- UI 必须明确区分 unavailable、unsupported、clarify、refuse 和 failed。

### 13.2 Failure matrix

| Failure | Allowed behavior | Forbidden behavior |
|---|---|---|
| Qwen unavailable/rate-limited | deterministic Dashboard；登记问题可走独立 deterministic binder；Studio manual flow可用 | browser/model-free text 假装 LLM answer；partial answer |
| model schema/identity mismatch | automatic-off exact rollout epoch；返回 safe failure | repair 成自由文本；换未批准模型 |
| model deadline exceeded | cancel/abandon；丢弃 private buffer | late response commit |
| component/bundle candidate invalid | block install/publish/prepare；eligible old active may continue | 修改 active bytes in place |
| Agent requests raw bundle/authoring/control/source ref | OS/API deny before resolution；safe non-enumerating error | 通用ArtifactStore credential/mount；digest当authorization |
| capability not installed | prepare fails with exact missing capability list | runtime 临时执行 package code |
| certification/golden fail | candidate not activatable；old active continues | warning override |
| Artifact Store unavailable | digest-verified cached exact active bytes + current eligibility may continue；new install/publish blocked | mutable latest/local unknown bytes；cache绕过revocation |
| Artifact publish lease expired/GC race | abort intent；no authority append；orphan later bounded-GC | read-back结果过期后仍append ref；删除committed object |
| legacy file/SQLite migration source unavailable | 已完成cutover的PostgreSQL路径不受影响；未迁移workspace只读并显示migration blocked | 临时恢复legacy head authority；无校验地跳过import |
| PostgreSQL unavailable | Studio writes和新analysis/result commit unavailable；health显示degraded | 无durable commit仍释放answer；fallback到filesystem head |
| expected/observed DataIdentity mismatch | query/result release fail；answer bytes=0；old activation不被candidate修改 | 用认证A的identity解释实际B的结果；使用stale number |
| Query Engine/data unavailable | `FAILED_EXECUTION`/unavailable，query evidence记录 | 使用旧数值冒充 live |
| graph query/cache failure | typed catalog basic lookup可用；graph-dependent feature unavailable | LLM 猜 lineage |
| projection-fidelity failure | block GSR/runtime graph-dependent release；typed source保留 | 仅凭SHACL PASS继续；缓存错误graph |
| prompt/egress/profile mismatch | no provider call；manual/deterministic registered flow可用 | bundle prompt自动生效；repair/retry绕过approval |
| frontend/API unavailable | 明确 unavailable/retry | browser-side calculator fallback |
| activation conflict | one winner；loser stable conflict | highest-sequence-wins overwrite |
| revoke before result commit | answer bytes=0 | 已 revoke execution 继续输出 |
| egress denied/expired | no provider call | shadow/retry 绕过 decision |

### 13.3 Deterministic fallback eligibility

只有同时满足以下条件，LLM-off request 才能走 deterministic fallback：

- AgentExperienceProfile明确登记同一question family/case或deterministic resolver pattern；
- 从 original trusted request 重跑；
- exact active VRS/engineering snapshot、policy、tool budget重新解析；
- renderer 和 evidence contract 与正常路径相同；
- response 标记 `model_called=false, fallback_used=true`；
- fallback success 与 provider success 分开报告。

### 13.4 Rollback

- Runtime：activate previous still-valid、not-revoked VRS/snapshot via new activation record；
- Model：rollout epoch → `off`，新 epoch 才能恢复；
- Product image：previous image + same active semantic release；bootstrap 不回滚 Studio 新 release；
- Database：expand/migrate/contract，应用回滚不能依赖 destructive schema downgrade；
- Frontend：static build version pin；API contract mismatch readiness fail；
- Feature：per-product/task feature flag，默认 off；
- Revoked digest 永远不能通过 rollback 复活。

### 13.5 Result-release linearization

Governed Product Target中，Activation、Revocation和ResultReleaseCommit共享一个ChannelScope顺序域：

```text
lock/serializable compare exact scope-order row
→ reread active head + revocation watermark + ChannelEligibilityEpoch
→ verify exact policy/authority decisions and expiry using database commit-time clock
→ create phase-specific RESULT_RELEASE Eligibility
→ persist exact Evidence + sanitized projection artifact ref
→ append ResultReleaseCommit + authority sequence in one transaction
→ transaction commits
→ HTTP reads exact committed bytes and releases them
```

任何activate/revoke/policy-or-authority deny mutation先赢得顺序，都必须在同一ChannelScope row bump epoch并使旧expected state的commit稳定失败。外部decision source不可重读、expiry跨过commit time或writer试图不bump epoch时fail closed。renderer后、artifact后、DB commit前的所有fault都必须产生analytic bytes=0。Scenario-Portable Demo保留current bounded engineering commit但不得使用Frozen名称或claim。

---

## 14. Deployment Architecture

### 14.1 Scenario-Portable Engineering Demo — single EC2 / k3s

```text
temporary managed HTTPS ingress / no SLA
        ↓
Nginx + Demo Auth
        ├── React descriptor-driven Console
        ├── Studio API container
        ├── Agent API container
        └── Operator API container (not public route)

Internal k3s network:
  model-gateway
  PostgreSQL product-state service
  MinIO/AWS S3-compatible artifact namespace
  installer-only distribution/authoring/control access policy
  projector-only component namespace
  Agent-only closed EngineeringRuntimeView namespace (read-only)
  QueryEngine-only pinned synthetic Parquet handle namespace
```

同一backend image使用不同command启动Studio、Agent、operator、model-gateway；产品边界由API、state machine和权限保持。只有第二场景证明需要异步job时才增加worker。Docker Compose保留为开发机兼容路径，不是新产品部署authority。

Governed/Durable Product Target复用同一PostgreSQL/S3/Kubernetes底座；只有formal authority-order、outbox/worker、off-host checkpoint、restore quarantine、HA/SLA等新增能力仍需各自合同与验收。基础栈采用不改变两个Product Domain边界。

### 14.2 Image/component separation

```text
ontology-products-backend:0.4.0
ontology-products-console:0.4.0
scenario-bundle-adt-reference:2.0.0.osb
deployment-binding-adt-demo:v1
```

Dockerfile不再`COPY scenarios`。DistributionBundle/components在deploy/install时由独立installer identity单独mounted/downloaded，先按raw digest与PackageSafetyProfile验证；projector只把closed RuntimeView写入Agent专属namespace。Kubernetes ServiceAccount/NetworkPolicy/Secret与object-store credential必须显式证明Agent workload没有distribution/authoring/reference-control/admin访问。Agent最终只加载activated runtime view与exact query handle，不读取raw bundle。stable custom domain/individual identity、HA/SLA和structured operations hardening仍是后续项。

### 14.3 ARM64 and Kubernetes

- current EC2 target锁定并smoke实际CPU architecture；镜像必须能按目标平台构建，ARM64是当前已知要求；
- 当前自有EC2使用k3s，标准Kubernetes manifests/Helm-compatible values不得依赖k3s私有语义；
- ConfigMap仅放非敏感config，secret由Secret/external provider注入；artifact走S3-compatible API，不依赖共享hostPath；
- 每个公开/内部workload均定义readiness、liveness、resource request/limit、security context、rollback image与migration ordering；
- 多副本、autoscaling、跨AZ、PDB与managed database属于HA/SLA hardening，不由“已经使用K8s”自动获得；
- 目标 customer cluster/network/security approval 不由当前 EC2 demo 证明。

### 14.4 Backup and recovery

Scenario-Portable Demo：

- release前备份current state volumes与content-addressed artifact manifest；
- upgrade失败必须保留current active和Studio later release，不由bootstrap回滚；
- 明确其不宣称disaster-safe monotonic revocation、HA或RPO/RTO。

Governed/Durable target：

- PostgreSQL PITR/logical + pre-release consistent backup；Artifact Store exact version inventory；
- backup manifest绑定DB LSN/transaction boundary、artifact versions、schema/build与activation/revocation high-watermarks；
- authority/revocation high-watermark有独立rollback-resistant current-head authority：单调sequence + digest + scope coverage的conditional-CAS record/ledger，使用与DB backup/restore分离的credential，拒绝delete、same-sequence different-digest和sequence降低；immutable checkpoint object本身不能自称“latest”；
- 恢复实例必须在线读取该independent current head及proof；head source不可达、旧sequence、fork、缺scope或stale cache时持续quarantined/readiness=false，不能用被一同回滚的DB/config alias判断latest；
- DB@T1/artifact@T2、backup后revoke后只提供旧checkpoint、alias指旧version、deleted/forked head、missing journal和corrupt manifest全部fail closed；
- secrets/raw expired traces不进入backup；恢复后需operator promotion record、exact refs/digests重验和two-scenario desktop smoke。

---

## 15. Observability and Operations

### 15.1 Signals

- request/outcome latency；
- GSR/component/bundle/payload/VRS-or-engineering-snapshot/context identities；
- operator/tool call count、duration、result row count；
- Qwen call count、returned model identity、tokens、deadline result；
- fallback_used、automatic_off reason；
- validation/certification pass/fail；
- query access count for Clarify/Refuse；
- answer analytic bytes before commit；
- evidence/claim coverage；
- outbox/job lag（仅async acceptance启用后）；
- active head、authority sequence、activation/revocation epoch与commit result；
- expected/observed DataIdentity、artifact read-back、projection-fidelity和package-safety outcomes。

### 15.2 Prohibited telemetry

- raw question by default；
- raw prompt/response；
- SQL/params/raw rows；
- physical table/column/locator；
- secrets/tokens；
- Studio original attachment content；
- user-visible answer before commit。

Raw provider body、scenario physical identifiers和exception cause只能在exact approved、短TTL、受限incident/eval surface存在；normal logs/metrics/traces均使用positive allowlist。

### 15.3 Runbooks

- DistributionBundle install/validate/component promotion；
- GSR publish、payload/five attempts/seal/activate/eligibility，或engineering-mode对应流程；
- Qwen automatic-off and recovery；
- package/capability incompatibility；
- PostgreSQL/artifact/query-engine outage；
- activation conflict/revocation；
- rollback；
- public demo URL/credential rotation；
- data-identity mismatch/TOCTOU；
- backup restore、revocation high-watermark reconciliation与quarantine promotion。

### 15.4 Requirement / test / runbook applicability

以下矩阵是scope authority；未映射到当前slice acceptance ID的dependency、service、adapter、test或runbook不得进入portable lockfile、image、Compose、WBS或GO checklist：

| Capability | Engineering D-1/D0/D1 | Portable D2–D4 | Governed / separately-approved hardening |
|---|---|---|---|
| PackageSafety、exact component/build、RuntimeView physical isolation | implement D1 | retain/conformance | required |
| ExactQueryDataHandle/DataIdentity、DuckDB sandbox | implement D1 | retain/mutation | required + warehouse snapshot adapter |
| filesystem/SQLite compatibility ports | characterize/import only | retain for isolated tests/rollback evidence | remove from product authority after migration exit |
| PostgreSQL product state | implement first vertical slice | retain/conformance/migration rehearsal | add formal ChannelScope/five attempts/VRS/restore-head only with exact authority |
| React ProductContext/descriptor console | implement first vertical slice | factor D2c、rehearse D3/D4 | retain；new routes follow same descriptor boundary |
| React Router/TanStack/Form/Zod | implement only as current route requires | retain/conformance | expand route-by-route；React Flow/full i18n remain conditional |
| existing RDF/SHACL regression | retain/no-change | retain | retain |
| new RDF/SPARQL/fidelity user surface | conditional graph task only | conditional D3 acceptance | bounded experiment only；not selectable in current Gate B catalog |
| three extra intake parsers | defer | conditional exact source task | separate authoring track |
| worker/outbox/full OTel | reject/defer | defer | conditional measured async/ops task |
| S3-compatible store + Kubernetes/k3s | implement first vertical slice | release/rollback/fault rehearsal | stable domain/individual IAM/HA/SLA remain separate hardening tracks |
| LangGraph/triplestore/pgvector/Knowledge Center | reject | defer | measured task may trigger new architecture/catalog decision；not current Gate B track |

Product & Delivery DRI维护machine-readable applicability/WBS mapping；Shared Contract Owner维护technical status。conditional/defer项提升为must-have必须有DecisionRecord、acceptance ID、owner与重估，不能靠文档中出现名称自动进scope。

---

## 16. Testing and Evaluation Architecture

### 16.1 Test layers

| Layer | Tool/evidence |
|---|---|
| Contract/schema | pytest, JSON Schema vectors, canonical digest fixtures |
| Domain module | pytest boundary tests against public module interfaces |
| Property/mutation | Hypothesis-style generation + fixed mutation profiles |
| Persistence | current adapter conformance now；real PostgreSQL container/concurrency/migration tests for Governed target |
| Query engine | DuckDB local stand-in + compiler golden tests |
| RDF/SHACL | existing regression always；new graph surface only when `graph_feature=on`：exact profile/shapes、deterministic graph、typed-index↔SPARQL differential、drop/rewire mutations |
| Components/bundle | build reproducibility、component-only change matrix、PackageSafety malicious corpus、inventory/digest/tamper tests |
| Agent | correctness/coverage/Clarify/Refuse/Failed/Claim/evidence separately |
| LLM | frozen Qwen eval + model-off/fault/leak/mutation |
| Frontend | Vitest/component + Playwright true API E2E |
| Authority/data | Engineering：same-handle ABA/lease/reachability/current-CAS；Governed：five-attempt mutations、activate/revoke/policy-epoch/commit races、artifact/DB kill points、rollback-resistant restore quarantine |
| Deployment | Compose config、clean/in-place upgrade、restart/rollback、actual target-architecture desktop smoke |

### 16.2 Component and distribution conformance kit

每套scenario solution必须分别通过：

1. DistributionBundle/component full-ref、schema、inventory、raw/canonical digest closure；
2. PackageSafetyProfile malicious corpus与resource budget；
3. mode-discriminated semantic/binding closure：Engineering必须验证`EngineeringSemanticRelease + ontology-engineering-deployment-binding/v1 + EngineeringMinimumControlProfile`、limitations完整且formal registry/endpoint write count=0；Governed必须验证`GSR + ontology-governed-deployment-binding/v1 + Semantic Approval/PUBLISH/source/decision/requirement closure`；both/none/cross-fill/unknown mode全部拒绝；
4. formula/grain/unit/additivity/time/population/operator-precondition validation；
5. mapping/join/source schema compatibility与exact CapabilityContract/installed build mapping；
6. presentation descriptor allowlist、reserved trust keys和locale/Unicode/URL checks；
7. product-owned prompt/tool/slot dependency、egress/eval/rollout digest closure；multilingual/encoded/bidi malicious label/example corpus证明system/task/tool digests与budget不变、forbidden wire fields/unapproved tool/query=0、事实仍由deterministic claims支撑，最坏为safe failure且partial bytes=0；
8. 若`graph_feature=on`：先按mode exact one-of解析semantic source（Engineering=`EngineeringSemanticReleaseRef`且formal writes=0；Governed=`GSRRef`），再用exact product-owned profile/shapes重新生成RDF、重跑SHACL与fidelity differential，并让projection receipt/cache绑定`semantic_release_kind + full ref/digest + profile + build + graph digest`；cross-fill/both/none/跨mode cache复用全部拒绝；若off：bundle、installed inventory、runtime lock和dependency中的projection/ShapeSet/SPARQL均为0且graph claim=`UNAVAILABLE`；
9. independently frozen ReferenceManifest/control/suite/mutation denominator与role separation；
10. zero executable code/secret/unsafe path/network/model/query during install；
11. `ExactQueryDataHandleV1` expected/observed equality、A→B→A barrier mutations、lease/pin与QueryEngine sandbox；
12. Agent process/storage dependency只能到closed RuntimeView + exact query handle；raw bundle/authoring/control/source跨namespace读取OS/API deny且不泄露存在性；
13. ArtifactPublishIntent/lease/GC/process-death interleaving满足`authoritative_ref ⇒ exact object exists`；
14. formal mode下五份exact attempts、seal、Activation、ChannelEligibilityEpoch、phase Eligibility和rollback-resistant restore head完整。

### 16.3 Generalization gate

```text
freeze ListingFalsificationManifest before generic implementation
→ run minimal ADT + Listing discovery tracer
→ record differences and MissingCapabilityRequests
→ DiscoveryOutcome: SUPPORTED_CANDIDATE / FALSIFIED_MISSING_CAPABILITY / INVALID_TEST_CASE
→ Gate A Decision: STOP / NARROW / EXTEND / CONTINUE_TO_FACTOR
→ factor only evidence-backed common primitives
→ freeze product images once
→ clean install/run ADT exact components
→ clean state
→ clean install/run Listing exact components
→ compare core-change ledger and behavior
→ append final PORTABLE_PASS or PORTABILITY_NOT_PROVEN record
```

最终`PORTABLE_PASS`：

- frozen backend/frontend core diff=0，只有scenario components/DeploymentBinding不同；
- common code除migration allowlist外ADT/Listing identifiers=0；
- each promoted primitive有两个scenario的concrete use/equivalence law；
- both scenarios pass context、Studio、Release Manager、Agent、model-off/failure、evidence、activation/rollback flows；
- unsupported capability在prepare前以exact list失败，Query Engine=0；
- ReferenceManifest/control independence、correctness、coverage、Clarify、Refuse、Failed、claim coverage和leakage分别报告。

`FALSIFIED_MISSING_CAPABILITY`也是成功的学习结果，但portability claim必须为false，不能为了让gate变绿而现场扩kernel。

D1 schema/API根本不包含`PORTABLE_PASS`。只有final record可使用该值，并必须绑定GateAEvidenceManifest、factorization decisions、frozen backend/frontend digests、ADT与Listing clean-run receipts、zero forbidden case tokens/core diff、controls和claim audit。`INVALID_TEST_CASE`必须停止factorization；`FALSIFIED_MISSING_CAPABILITY`只能进入STOP/NARROW/EXTEND，不能被DecisionRecord改写成事实PASS。

### 16.4 Reader and demo tests

- 3名未参与设计的proxy viewer分别观看PASS候选与MissingCapability分支；3/3必须通过以下理解测试，否则External GO失败：
- fresh user can explain Studio Source → Proposal → Decision → Draft；
- fresh user can explain Dashboard → Ask → Evidence；
- fresh user knows LLM did not calculate the number or publish ontology；
- fresh user knows constructed-synthetic is not customer validation；
- fresh user可区分DistributionBundle与GSR/VRS/Activation authority；
- fresh user能说出四维claim ceiling：不是customer truth、不是完整Stage 1（除非exact authority真的通过）、不是individual audit/production、portability只限两个exact场景与声明ceiling；
- fresh user能解释MissingCapability为何是有价值证据、Gate A只决定是否继续投资、不是PORTABLE_PASS；
- “fresh package author无需RDF/SHACL/internal AST”在独立proxy test通过前只是future target，不是当前claim。

---

## 17. Gated Discovery and Vertical Delivery Plan

本节保留v0.9已经通过fresh-reader的generalization evidence gates，但`17_architecture_approval_and_stack_decision.md`改变了实施起点：React、PostgreSQL、S3-compatible storage与Kubernetes现在是每条新架构纵向切片的共同baseline，不再等待Final Generalization或Gate B。原`39–62 pd`、`11–19 pd`、`30–51 pd`和`21–36 pd`全部撤回，不再是当前投资或日期承诺；当前实施顺序以§17.4及`plans/common-product-vertical-slices.md`为准。

### 17.1 General Demo Charter

进入任何实现前，Decision Owner先判断本轮模式：

- Primary audience：customer/External Reviewer业务、数据和技术stakeholders；
- 唯一要支持的投资决定：是否值得进入“真实customer安全区内的一个场景discovery + governed productization”下一阶段；
- Engineering hero flow（15–20分钟）：Cleared synthetic input → Studio proposal/human decision/`EngineeringSemanticRelease` → Release Manager exact install/prepare/`EngineeringActivationRecord` → Agent Dashboard/Ask/Evidence/`EngineeringDemoResponseCommit` → failed candidate/old-active proof → Gate A investment decision；全程禁止GSR/VRS/Eligibility/ResultReleaseCommit命名；
- Governed hero flow是另一份互斥脚本，只有exact Approved/Frozen authority manifest后才可选择，使用GSR→payload→five attempts→VRS→Activation/Eligibility→ResultReleaseCommit；
- Listing MissingCapability是Engineering脚本的合法分支：展示exact missing list、query/model=0、ADT old-active仍可用、portability claim=false和下一步成本；
- External GO：Product & Delivery DRI，且必须使用四维claim ceiling；
- deferred：accepted SCR→new GSR/VRS→changed answer的完整co-work loop、生产IAM、Knowledge Center。

### 17.2 Recommended slices

#### 17.2.1 D1DiscoveryExperimentContract

D1开工前必须冻结exact `D1DiscoveryExperimentContract`。它不是DAG外的隐式root：B-02先完成本次Reference/Control/Suite/DataIdentity与separation receipts，再由Product & Delivery DRI作为B-02 terminal output编制full-ref contract；Shared Contract Owner验证schema，Decision Owner只确认其exact subject/digest且不成为producer。Contract canonical subject只绑定先前已存在的A-01/A-02/B-01 outputs和B-02 prerequisite refs/receipts，明确排除自身ref/digest与包含自身的B-02 aggregate exit digest，因此没有self-hash cycle：

- **Inputs**：A-01 `ImplementationAuthorityManifest`、A-02 reuse/applicability/role manifest、current image/source digests、B-01 Listing manifest、B-02 prerequisite Reference/Control/Suite/DataIdentity refs与separation receipts（不含contract自身或B-02 aggregate exit digest）、ADT baseline、immutable regression inventory、EngineeringMinimumControlProfile和two exact adapter IDs；
- **Allowed common diff**：trusted INSTALL + complete PackageSafetyProfile、durable ArtifactPublishIntent、closed ComponentInventory、EngineeringRuntimeView projector/physical namespace、exact capability resolver、ExactQueryDataHandle、ProductContext/descriptor和repository seam；除此之外common diff必须有新Decision；
- **Required ADT path**：外置bundle完成existing Dashboard + one Ask/Evidence path，value/Fact/Claim/evidence/projection parity；
- **Required Listing path**：install→context→one preregistered priority case，或在query前返回exact MissingCapability且query/model=0；
- **Scenario-specific allowance**：只有experiment目录/registry entry内的two exact translations；逐文件进入ledger，不能成为package code、kernel primitive或public common contract；
- **Outputs**：exact run receipts、common/scenario diff、security/mutation results、regression inventory、actual effort、`DiscoveryOutcome`和GateAEvidenceManifest；
- **Stop rules**：unsafe install、raw-bundle reachability、wrong data handle、unapproved common operator、control不独立或case无效立即STOP/INVALID；不能为过gate现场扩kernel。

D1从clean build启动，Dockerfile不得`COPY scenarios`。Bundle在PackageSafety通过前不能promote；只有install receipt不能resolve runtime。Agent UID读取raw bundle/AuthoringProfile/control expected/source bytes必须OS/API双重deny。common source除approved migration allowlist外，`ADT|Listing|M-03|Q3|Q4`命中为0；scenario-specific文件100%进入ledger。

#### 17.2.2 Pre-evidence acceptance-to-WBS

每个acceptance ID恰好映射一条WBS；数字是low-confidence active-pd hypothesis，不是日期。`Delivery accountable role`每行必须恰好一个canonical role；独立truth/gate/approval authority在下一列列示，但不与delivery A合并：

| WBS / acceptance ID | Exact output | Delivery accountable role | Required artifact/gate authorities and separation | Active pd |
|---|---|---|---|---:|
| A-01 | ImplementationAuthorityManifest、双mode endpoint/name gate、两份hero scripts、four-dimensional surface scan | Product & Delivery DRI | Decision Owner选择mode；DRI不能自批implementation authority | 1–2 |
| A-02 | retain/wrap/parameterize/replace/delete inventory、named role map、§15.4 applicability lock | Product & Delivery DRI | Shared Contract Owner确认contract seam；各Domain Owner确认product surface | 1–2 |
| B-01 | ListingFalsificationManifest、priority cases、2 semantic + 1 binding difference、legal outcomes | Product & Delivery DRI | Reference Truth Owner拥有truth selection；DRI只拥有delivery output | 2–3 |
| B-02 | independent Reference/Control/Suite/DataIdentity、fixture、oracle、mutations与role separation receipts；随后产出绑定A-01/A-02/B-01与B-02 prerequisite refs/receipts（排除自身/aggregate exit）的`D1DiscoveryExperimentContractRef` | Product & Delivery DRI | Reference Truth Owner冻结reference；Data Approver确认DataIdentity；Independent Control Reviewer冻结control/suite并复核；Fixture & Adapter Author实现fixture且不得兼任Reviewer；Shared Contract Owner验contract schema；Decision Owner只确认exact final digest | 2–4 |
| C-01 | trusted installer、complete PackageSafety malicious corpus、ArtifactPublishIntent/lease/GC tests | Shared Contract Owner | Disclosure & Policy Approver不被installer实现owner代替 | 3–5 |
| C-02 | Engineering object graph、ComponentInventory、closed RuntimeView、Agent physical reachability deny tests | Shared Contract Owner | Agent Domain Owner确认Agent product reachability结果 | 3–5 |
| C-03 | exact capability/build、ExactQueryDataHandle、DuckDB sandbox与ABA barriers | Runtime Capability Owner | Data Approver确认expected DataIdentity；Independent Control Reviewer独立执行identity/mutation验收 | 3–5 |
| C-04 | two exact scenario translations、ProductContext、ADT parity + Listing priority path/safe fail | Product & Delivery DRI | Studio/Agent Domain Owners分别确认产品surface；truth/control authorities不转移 | 4–7 |
| C-05 | GateAEvidenceManifest、core-change ledger、actual-effort record、3/3 proxy comprehension rehearsal | Product & Delivery DRI | Decision Owner只签Gate A投资决定；不能签出事实PASS | 2–3 |

上述 **21–36 active pd** 是已撤回的v0.9 pre-evidence hypothesis，只保留为review history，不得用于排期。新baseline需要在第一条可运行tracer后，以真实migration/infrastructure evidence重新估算；acceptance覆盖率、duplicate/unmapped=0和新增dependency可追溯要求继续有效。

**Decision Gate A：** 只签`STOP / NARROW / EXTEND / CONTINUE_TO_FACTOR`与新WBS/ROM；D1完成自动使后续任何旧estimate过期。Gate A不能签`PORTABLE_PASS`。

#### 17.2.3 Normative phase / DAG manifest

Phase、WBS和edge不再由章节顺序推断，规范映射固定如下：

| Phase/node | Exact predecessor | Exact output / exit | One delivery A | Failure / rollback target |
|---|---|---|---|---|
| D-1 / A-01 | current Approved/Frozen baseline + named DRI | exact `ImplementationAuthorityManifest` or explicit NO-GO | Product & Delivery DRI | 不产生package/runtime mutation |
| D-1 / A-02 | A-01 | exact reuse/change/applicability/role manifest | Product & Delivery DRI | 保留read-only discovery evidence；不进入D0 |
| D0 / B-01 | A-02 | frozen `ListingFalsificationManifest` | Product & Delivery DRI | 保留invalid/failed preregistration；不写runtime |
| D0 / B-02 | B-01 | exact Reference/Control/Suite/DataIdentity refs + separation receipts + final `D1DiscoveryExperimentContractRef`（唯一producer） | Product & Delivery DRI | 保留不可变truth/control/contract记录；未确认exact digest不进入fixture/runtime build |
| D1 / C-01 | B-02 exact exit（含confirmed `D1DiscoveryExperimentContractRef`） | trusted installer + PackageSafety + durable artifact evidence | Shared Contract Owner | staging/orphans按lease清理；old active不变 |
| D1 / C-02 | C-01 | closed Engineering object graph/RuntimeView + reachability-deny receipts | Shared Contract Owner | 不publish/activate候选；old active不变 |
| D1 / C-03 | C-02 | exact capability/data-handle resolution + sealed-object identity/sandbox evidence | Runtime Capability Owner | query/result bytes=0；old active不变 |
| D1 / C-04 | C-03 | ADT parity receipt + Listing priority receipt or exact pre-query MissingCapability | Product & Delivery DRI | feature flag回current ADT path；candidate不替换old active |
| D1 / C-05 | C-04 | immutable `GateAEvidenceManifest` + `DiscoveryOutcome` | Product & Delivery DRI | evidence retained；没有自动factorization |
| Gate A | C-05 | exact `STOP / NARROW / EXTEND / CONTINUE_TO_FACTOR` DecisionRecord | Decision Owner | 前三种与`INVALID_TEST_CASE`都不能进入D2 |
| D2a | Gate A=`CONTINUE_TO_FACTOR` | component-boundary vertical receipt | Shared Contract Owner | 回D1 exact implementation；无half-installed authority |
| D2b | D2a | shared capability/data vertical receipt | Shared Contract Owner | 回滚contract adapter；old active继续 |
| D2c | D2a | shared ProductContext vertical receipt | Product & Delivery DRI | descriptor feature flag回current ADT view |
| D3a | join(D2b, D2c) | same frozen build dual-scenario Dashboard receipts | Product & Delivery DRI | no portability conclusion；old active继续 |
| D3b | D3a | dual-scenario Ask/Evidence/model-off/failure/rollback receipts | Product & Delivery DRI | no-partial；no portability conclusion |
| Final Generalization Gate | D3b | exact `PORTABLE_PASS` or `PORTABILITY_NOT_PROVEN` record | Decision Owner | NOT_PROVEN不能进入D4 external release |
| D4 | Final=`PORTABLE_PASS` | Portable EC2 release evidence + separate External GO/NO-GO | Product & Delivery DRI | previous image + exact active snapshot |

Machine-readable DAG edge set必须等于：

```text
A-01 -> A-02 -> B-01 -> B-02 -> C-01 -> C-02 -> C-03 -> C-04 -> C-05 -> GateA
GateA[CONTINUE_TO_FACTOR] -> D2a
D2a -> D2b
D2a -> D2c
join(D2b,D2c) -> D3a -> D3b -> FinalGeneralizationGate
FinalGeneralizationGate[PORTABLE_PASS] -> D4
```

DAG linter必须证明acyclic、所有node从A-01可达、每个非baseline input ref只有一个declared producer（`D1DiscoveryExperimentContractRef.producer=B-02`且C-01消费exact同一digest）、每node恰好一个canonical delivery A、非法Gate A outcome没有到D2的edge、`PORTABILITY_NOT_PROVEN`没有到D4的edge，以及每个failure edge都有上表的rollback target。missing/wrong/old contract digest或Decision Owner confirmation subject不一致时，C-01不可达且package/runtime writes=0。任何edge、owner、output class或gate enum变化都产生新manifest digest并触发WBS/ROM重审；旧21–36 hypothesis已经由Decision 17撤回。

#### 17.2.4 Post-gate vertical checkpoints

只有Gate A=`CONTINUE_TO_FACTOR`后才细化、估算和批准：

| Checkpoint | User/API-visible vertical outcome | Rollback / exit | Canonical accountable role |
|---|---|---|---|
| D2a — Component boundary | 从已工作的D1 paths提炼exact component refs/projector；两场景install→closed RuntimeView或stable safe failure | feature flag回D1 exact implementations；不留half-installed authority | Shared Contract Owner |
| D2b — Capability + data | 两场景用同一exact capability/data-handle contract完成one analytic outcome或pre-query MissingCapability | 回滚contract adapter；old active继续，partial bytes=0 | Shared Contract Owner |
| D2c — ProductContext | 同一console build渲染两场景context + one Studio/Agent task，无browser authority | descriptor feature flag回current ADT view | Product & Delivery DRI |
| D3a — Dashboard tracer | 同一frozen build完成ADT与Listing Studio→Release Manager→Agent Dashboard | 任一case/control/claim失败则无PORTABLE_PASS | Product & Delivery DRI |
| D3b — Ask/Evidence tracer | 两场景Ask→Fact/Claim/Evidence、model-off、failure、old-active/rollback | no-partial、exact receipts；失败保持previous active | Product & Delivery DRI |
| D4 — Portable EC2 release | clean/in-place upgrade、restart、fault injection、rollback、desktop E2E、claim audit与temporary HTTPS/no-SLA | previous image + exact active snapshot；External GO由DRI单独签 | Product & Delivery DRI |

每个checkpoint必须有exact input/output digests、一个canonical A、responsible owners、test inventory、feature flag/rollback和failure owner；缺任一项为`NO_GO`。React、PostgreSQL、S3-compatible storage与Kubernetes属于共同implementation baseline；formal five gates、stable domain、individual IAM、author kit、HA/SLA和new graph surface仍不由本路径自动获得。

### 17.3 Productization Investment Gate B and optional tracks

`Productization Investment Gate B`是**Portable Generalization证据完成后的产品化投资门**，不是Gate A别名、不是D4发布门，也不是一个允许所有target capability同时开工的总开关。它最早只能在`FinalGeneralizationGate`已经写出immutable final record之后运行；D4是否发布与Gate B是否投资是两个独立分支，互不作为前置。

#### 17.3.1 Architecture-level decision rule

Gate B在本文件中只定义到**产品投资决策**层，不提前设计未来的digest schema、CAS、签名、并发或审批服务。那些内容只有在某条Product Target track真正获准、进入自己的PRD和Shared Contract extension时才设计；它们不应阻断当前D-1/D0/D1。

Gate B的最早输入是immutable Final Generalization result，以及支持这个result的双场景run evidence、actual effort、remaining capability/security/operability gaps和claim ceiling。Product & Delivery DRI为每条希望投资的track准备一份独立proposal，至少包含：业务目的、exact scope、一个named accountable owner、entry dependencies、acceptance→WBS、fresh ROM与excluded wait、test/rollback/exit和不能宣称什么。Decision Owner是唯一批准人。

Gate B只有三种决定：

| Decision | Meaning | What may happen next |
|---|---|---|
| `STOP_PRODUCTIZATION` | 没有足够价值或证据继续 | 保留证据，不启动Product Target工作 |
| `REWORK_DISCOVERY` | 产品假设需要重新证伪 | 启动一个**新版本**discovery cycle，重新preregister、WBS和执行A-01→B-02；旧PASS/contract不能冒充新证据 |
| `APPROVE_NAMED_TRACKS` | portability evidence和逐track business case足够 | 只允许所点名的track进入各自PRD/technical design/implementation approval流程 |

`PORTABILITY_NOT_PROVEN`只能得到STOP或REWORK，不能批准Product Target建设。Gate B不能产生或补签`PORTABLE_PASS`，不能替代某条track自己的Approved/Frozen authority、implementation approval、release gate或External GO；Gate B获批也不等于代码可以立即写入production path。

#### 17.3.2 Ordering and scope boundary

```text
Final Generalization result
├─ PORTABLE_PASS ──> optional D4 Portable Demo release ──> separate External GO
│
└─ Gate B ──> STOP
           ├─ REWORK ──> new versioned discovery cycle
           └─ APPROVE_NAMED_TRACKS ──> one separate proposal/PRD/WBS per named track

PORTABILITY_NOT_PROVEN ──> Gate B: STOP or REWORK only
```

D4和Gate B是两个独立分支：可以发布Portable Demo而暂不投资Product Target，也可以基于Final evidence先准备后续投资而不把D4当作前置。任何未点名的track都没有预算、backlog或implementation authority；不存在`all/default/future`通配批准。若同一final evidence下出现互相冲突的Gate B决定，必须先形成新的、明确supersede关系的DecisionRecord，旧记录保持可追溯；具体记录格式和原子提交规则留给获选track的Shared Contract extension。

#### 17.3.3 Named track catalog

- `P-AUTHOR` Minimum author kit：scaffold、simple templates、schema/examples、path-specific lint、deterministic build/diff/test、两名proxy；原`6–10 pd`仅为pre-Gate-B hypothesis。在通过前只宣称core-engineer-authored packages。
- `P-GOVERNED-AUTHORITY`：ChannelScope order、five gates/VRS/Eligibility/ResultReleaseCommit、restore quarantine；PostgreSQL是其底座，但不等于这些formal语义已实现。
- `P-ACCESS`：stable domain、individual identity、enterprise IAM与审计接入。
- `P-OPS-HARDENING`：HA/SLA、跨AZ、autoscaling、PDB、managed backup/restore与structured operations；Kubernetes baseline本身不等于该track已完成。

React、PostgreSQL、S3-compatible storage和Kubernetes已由Decision 17批准，不再出现在Gate B catalog中。当前可点名的optional tracks只有上面四项。Conditional graph task仍是§10.4的bounded experiment，不是Gate B track。Knowledge Center不在当前catalog；未来即使出现measured workload，也必须先形成新的architecture decision和独立WBS，不能借Gate B顺手带入。

每个WBS acceptance item只能映射一次，必须包含code、data/schema migration、tests、docs/runbook、deploy/rehearsal、owner、dependency、confidence与excluded wait。所有初始区间在Gate B批准前都不是implementation authority或delivery commitment。

### 17.4 Active implementation sequence

以下七条是当前approved delivery order；每条都是可运行、可演示、可回滚的vertical slice，不是四条水平技术项目：

1. **New-infrastructure ADT tracer**：React产品外壳、PostgreSQL产品状态、S3/MinIO工件、k3s部署共同承载一个真实ADT context/active-snapshot只读路径；现有API与ADT回归保持通过。
2. **Persistence lifecycle tracer**：ADT release→prepare→activate→rollback在PostgreSQL/S3上闭环，legacy files/SQLite不再拥有新head authority。
3. **Generic Studio tracer**：ADT成为外置solution components；Studio完成intake→observation→human decision→draft→release，产品代码不出现ADT业务常量。
4. **Generic Agent tracer**：descriptor-driven Dashboard + Ask + Evidence；前端不读取ADT字段名或计算公式，backend继续拥有facts/claims/release authority。
5. **Listing falsifier**：同一build加载第二个materially-different synthetic solution，合法结果可以是完整运行或pre-query `MissingCapability`，query/model调用为0。
6. **Dual-scenario factorization**：只有被ADT和Listing共同证明的primitive进入shared kernel；scenario-specific translation继续留在solution components。
7. **Kubernetes release slice**：clean/in-place upgrade、migration、restart、fault injection、rollback、desktop E2E与claim audit；单EC2/k3s成功不提升HA/SLA/IAM/customer claim。

第一条slice通过后，用实际数据库迁移、object-store、React和k3s证据重新形成剩余WBS/ROM。任何slice若只能展示“组件已经安装”而没有用户/API-visible outcome，不算完成。

---

## 18. New Case Onboarding Flow

在已由两个场景证明的capability envelope内，未来目标流程是：

```text
scenario-kit init <case>
→ 放入简单需求/指标模板和获准附件
→ register + parse
→ Studio review observations/gaps
→ human decisions
→ emit exact EngineeringSemanticRelease, or publish exact GSR only in Governed mode
→ define/approve AgentExperienceProfile and ReferenceEvaluationBundle
→ solution lint/build/tamper/differential test
→ install exact DistributionBundle/components
→ bind immutable target/synthetic DataIdentity
→ Engineering prepare/CAS activate/commit，或Governed verify/seal/activate/eligibility/commit
```

当前只承诺**core-engineer-authored two-scenario proof**。在minimum author kit与两名独立proxy test完成前，不宣称fresh author能够完成、不承诺3–7 active person-days，也不要求External Reviewer填写RDF/SHACL/internal AST。

两条路径：

- **Fast path**：现有operator/source/presentation component与semantic types足够，只改scenario components与DeploymentBinding；
- **Extension path**：产生`MissingCapabilityRequest`；先形成bounded operator/connector/policy RFC、至少两个场景的use/equivalence law和conformance suite，再决定是否进入kernel；
- **Outside-ceiling path**：预测/优化、arbitrary code/SQL或不受治理数据任务明确拒绝，不用插件绕过。

---

## 19. Rejected Alternatives

### 19.1 每个场景一个 Python ScenarioAdapter

拒绝作为最终常规onboarding路径，但允许在D1 discovery中用两个exact、受控的scenario implementations暴露真实差异。它们不能成为package插件市场；只有双场景证明的primitive才提升为受版本管理的product capability，单场景code留在experiment并阻断portability claim。

### 19.2 Package 内允许 arbitrary Python/SQL/JavaScript

拒绝。它破坏可移植性、安全审查、ARM compatibility、deterministic validation 和升级边界。

### 19.3 RDF/triplestore 作为所有数据的唯一数据库

拒绝。authoring transaction、immutable artifact、graph navigation 和 fact analytics 有不同工作负载。Typed contracts/PostgreSQL/Artifact Store/SQL engine 各司其职。

### 19.4 立即引入 LangGraph/DeepAgents 重写 Agent

拒绝当前实施。它不解决ADT hard-code，且可能重建已经通过测试的release/evidence/no-partial边界。保留reopen criteria，但不为单一实现预先创建宽framework seam。

### 19.5 保留 3,194 行 Vanilla JS，再增加更多配置分支

拒绝继续增加case branch；同时也拒绝在第二场景前big-bang React rewrite。先抽ProductContext/descriptor seam并删除browser oracle/calculator，再根据证据逐route迁移。

### 19.6 一开始建设 multi-tenant registry/Knowledge Center

拒绝当前范围。第二案例和真实企业接入证据尚不足；先验证component-driven single deployment。

### 19.7 自动解析客户 SQL 并把结果当 Ontology truth

拒绝。SQL 可以提供候选 lineage/mapping evidence，但需要人工 Decision 和 independent runtime validation。

### 19.8 Compound bundle 作为 GSR/VRS/Activation authority

拒绝。DistributionBundle只证明transport integrity；改presentation/control/data不能隐式改semantic authority，channel不能进入Binding/payload。

### 19.9 第二场景前冻结通用 compiler

拒绝。先preregister和运行dual-scenario discovery；允许MissingCapability使portability claim失败，再提炼common primitives。

### 19.10 Scenario component 直接控制system prompt、tool schema或trust wording

拒绝。Scenario只提供typed domain data/labels/examples并可收紧limitations；product-owned prompt/tool/trust contracts与independent approval不被bundle install替代。

---

## 20. Decision and Approval Gates

### 20.1 当前已决定

- 一个产品组、两个独立 Product Domains、一个 Shared Kernel；
- ADT 是 constructed-synthetic reference，不是 customer validation；
- External Review Team 默认只能安全转写；
- Studio/Agent 都需要 LLM，但 LLM 不拥有 truth/execution/release authority；
- Dashboard + Ask 并存，Studio 使用治理 dashboard；
- React + TypeScript + Vite、PostgreSQL 17、S3-compatible storage与Kubernetes是implementation baseline；当前EC2/k3s demo仍不证明customer target readiness、HA或SLA。

### 20.2 Decision Owner 已接受的实施方向

1. 当前先批准或拒绝`Scenario-Portable Engineering Experiment`，其ceiling为bounded tabular/KPI analytics discovery，不包含governed-evidence claim；
2. 采用component graph + non-authoritative `ScenarioDistributionBundle`，而不是compound Ontology Package authority；
3. 采用discovery-before-factorization顺序，并接受Listing实验可能以MissingCapability结束；
4. React逐route迁移、PostgreSQL产品状态、S3/MinIO ArtifactStore和Kubernetes/k3s从第一条新架构vertical slice进入；legacy console/filesystem/SQLite/Compose仅作为characterization、迁移或isolated-test兼容；
5. ArtifactStorePort使用S3-compatible exact-version实现，local/test默认MinIO；
6. 当前`graph_feature=off`、不新增SPARQL/KnowledgeGraphPort；只有exact lineage/impact hero task获批时才启用product-owned profile/shapes下的RDFLib/pySHACL有界实验；
7. current typed orchestrator保留，LangGraph后置；
8. content-addressed Parquet + sandboxed DuckDB作为demo fact path；
9. Listing SLA/Backlog作为优先falsifier并先冻结exact manifest；
10. D-1/D0/D1 generalization gates与external claim ceiling继续有效；旧`21–36 active pd` hypothesis已经撤回，第一条infra tracer后重新WBS/ROM。

### 20.3 Remaining blockers before promotion or external claims

- Decision 17已经授权Engineering implementation；任何Governed mode或formal Stage 1 claim仍必须有exact Approved/Frozen authority manifest；
- Decision Owner确认ListingFalsificationManifest的business decision、truth/control roles、questions和legal FAIL outcomes；
- Decision Owner确认`D1DiscoveryExperimentContract`、EngineeringMinimumControlProfile、GateAEvidenceManifest与Gate A只作投资决定；
- Product & Delivery DRI落实canonical role→named individual mapping与General Demo Charter；
- 每条active vertical slice的acceptance-to-WBS覆盖率必须100%、duplicate/unmapped=0；
- D1之后新的WBS/ROM必须另行accept，不能沿用pre-discovery hypothesis；
- graph-dependent hero task默认不选；若提升，必须同时批准ShapeSet/Projection owner、acceptance与WBS；
- author kit、formal governed authority、individual IAM和HA/SLA hardening仍需单独Decision；React/PostgreSQL/S3/Kubernetes不再等待Gate B。

当前transport contract继续是deterministic bundle + independently addressed components；S3只实现同一ArtifactStorePort，不改变contract。具体minor version、CSS system、CI provider、未来graph vendor不应阻断第一条vertical slice。

---

## 21. Acceptance Gate for This Architecture

本文件由Candidate转为Approved Baseline所需的审查条件如下；v1.0已经满足，但后续重大边界变化仍需重新走相同门：

- 三位独立 reviewer 使用同一 current-baseline review packet；
- Architecture、Correctness/Security、Delivery/Product 完成两轮 review；
- 所有 P0 关闭；所有实施前 P1 关闭或有 bounded experiment、owner 和 explicit blocker；
- 至少一个非显而易见的 failure mode 有当前代码/数据证据；
- 已完成的 release/runtime/LLM/evidence 工作没有被方案重建；
- 技术栈、存储、Ontology query、Agent framework、degradation、rollback 全部有明确边界；
- General Demo 与 long-term Knowledge Center 清楚分离；
- fresh reader 能准确回答产品边界、DistributionBundle/component authority、事务/工件/事实/图四类存储、LLM权限、失败时行为、两个交付层级和第二案例gate；
- Decision Owner批准后只能写为Approved Baseline/Implementation Authorized；不得冒充Shared Contract Approved/Frozen、实现完成或External GO。

---

## 22. External Technical References

- React current versions: https://react.dev/versions
- Vite official guide: https://vite.dev/guide/
- FastAPI features: https://fastapi.tiangolo.com/features/
- PostgreSQL versioning/support: https://www.postgresql.org/support/versioning/
- Alembic: https://alembic.sqlalchemy.org/en/latest/
- DuckDB Parquet: https://duckdb.org/docs/stable/data/parquet/overview
- RDFLib SPARQL: https://rdflib.readthedocs.io/en/stable/intro_to_sparql.html
- SHACL Recommendation: https://www.w3.org/TR/shacl/
- pySHACL: https://github.com/RDFLib/pySHACL
- SPARQL 1.1 Protocol: https://www.w3.org/TR/sparql11-protocol/
- pgvector: https://github.com/pgvector/pgvector
- S3 Versioning: https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html
- LangGraph graph/checkpoint concepts: https://langchain-ai.github.io/langgraph/

---

## 23. Review History

| Revision | Status | Notes |
|---|---|---|
| v0.1 | Superseded Candidate | Round 1：Architecture MODIFY 2/5/2；Security MODIFY 3/9/3；Delivery MODIFY 3/10/1 |
| v0.2 | Superseded Candidate | Round 1 adjudicated；Round 2：Architecture MODIFY 0/3/0、Security MODIFY 1/5/2、Delivery MODIFY 0/3/2 |
| v0.3 | Superseded Candidate | Round 2 adjudicated；closure retest：Architecture MODIFY 0/4/0、Security MODIFY 1/2/0、Delivery MODIFY 0/2/0 |
| v0.4 | Superseded Candidate | First focused retest：Architecture MODIFY 0/1/0、Security MODIFY 0/2/0、Delivery MODIFY 0/2/0；residuals为Engineering graph-on GSR-only identity与D1 contract zero producer |
| v0.5 | Superseded Candidate | Final focused retest：Architecture PASS 0/0/0、Security PASS 0/0/0、Delivery PASS 0/0/0；六问三线全部CLOSED |
| v0.6 | Superseded Candidate | Status-only repin；independent fresh reader为MODIFY 0/1/0，唯一finding为反复引用但未定义的Decision Gate B |
| v0.7 | Superseded Candidate | 首次Gate B focused retest：Architecture MODIFY 0/4/0、Security MODIFY 0/2/0、Delivery MODIFY 0/2/0；发现self-digest、Proposal/Decision反向边、REWORK contract producer冲突和unclosed track namespace |
| v0.8 | Superseded Candidate | 曾把未来Gate B过度展开为DigestSubject/envelope与artifact DAG；经first-principles复核撤回，不作为当前architecture baseline |
| v0.9 | Candidate | Gate B收敛为architecture-level investment rule；保留predecessor/owner/outcome/named-track/WBS边界，将exact record/CAS协议后置到获选track PRD；pending final fresh-reader |
| v1.0 | Approved Baseline | Independent fresh-reader PASS 12/12、P0/P1/P2=0/0/0；Decision Owner批准总体方案并将React/PostgreSQL/S3-compatible/Kubernetes提升为implementation baseline，旧21–36 pd撤回，授权按vertical slices开发 |

Review reports、adjudication、closure evidence 和 superseded findings 将保存在 `ontology-product-group/reviews/`。
