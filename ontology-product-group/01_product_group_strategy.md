# Ontology Analytics Product Family 总体规划

状态：Approved Baseline
版本：1.0
日期：2026-08-18
Decision Owner：Muyu
批准记录：Muyu 于 2026-08-18 明确批准 v0.6 Reviewed Candidate，转为 v1.0 Baseline
主要读者：内部产品、解决方案、工程、External Review Team 协作团队

## 1. Executive Decision

本方案按**一个产品组、两个独立 Product Domain、一个共享合同内核**规划。当前冻结的是两个独立产品域；最终商业产品/SKU 数量尚未决定：

```text
Ontology Analytics Product Family
├── Product Domain A：Ontology Studio / Semantic Build & Governance
├── Product Domain B：Ontology Analytic Agent / Governed Analytics
└── Shared Semantic Contracts & Kernel（共同底座，不是第三个用户产品）
```

这里的“独立”现在冻结的是：

- 不同的主要用户和 Jobs-to-be-Done；
- 不同的对象、写权限、状态机和失败责任；
- 独立的 Product-Domain PRD、backlog、体验边界和发布节奏；
- 可分别授权和测试的 control plane 与 runtime plane；
- 只能通过正式、版本化合同交换信息。

现在**不冻结**两个商业 SKU、两套顶层 UI、两个品牌、两个采购路径、两个代码仓库或两个 K8s Deployment。它们需要真实角色、第二场景和客户 operating/buying owner 的证据。

Ontology Studio 不是 Agent 内部的“配置页”。即使 PoC 使用一个导航壳、同一仓库或单进程，它仍拥有独立的治理对象生命周期和发布责任。

## 2. 产品组使命与成功定义

### 2.1 客户问题

企业通常同时存在两类断裂：

1. 需求、指标、流程、数据模型、字典和 SQL 分散在不同人员与材料中，缺少一份可确认、可计算、可版本化的业务语义合同；
2. 分析工具即使能生成 SQL，也无法证明使用了哪个定义、范围、映射、政策、运行组件和数据版本。

产品组使命：

> 把受限业务知识建设为可治理的语义发布物，再把它装配成可验证的运行快照，使每个分析答案受已批准语义约束、可解释、可追溯。

### 2.2 North-star outcome

North-star 使用一对指标，而不是对象数量或聊天次数：

1. `Time to First Trusted Scenario`：从第一份 cleared input 正式登记，到预先登记的 must-answer suite 全部达到可信门禁；
2. `Trusted Scenario Completion Rate`：所有进入 intake 的场景中，在约定周期内完成上述门禁的比例。

计时必须同时报告：

- wall-clock elapsed time；
- 我方 active person-hours；
- External Reviewer active effort；
- client confirmation wait；
- scope change、paused、failed、unsupported、clarify 和 refuse 的固定分母。

“第一个容易问题答对”可以作为运行里程碑，但不能单独结束 North-star 计时。

## 3. 两个 Product Domain 的边界

| 维度 | Ontology Studio | Ontology Analytic Agent |
|---|---|---|
| 主要用户 | External Reviewer Transcriber/Coordinator、Ontology Operator、Domain/Data Reviewer、Approver | Analyst、Business User、Executive、Auditor、Application Consumer |
| 主要任务 | Intake、Compile、Review、Resolve、Validate、Approve、Publish、Change | Ask、Clarify、Plan、Execute、Explain、Trace、Refuse |
| 核心对象 | Source Record、Candidate、Gap、Decision、Semantic Release | Runtime Snapshot、Plan、Fact、Claim、Execution、Answer |
| 写权限 | 写 draft 和 decision；按授权发布语义 | 只写 interaction、execution 和 feedback；不写 Ontology |
| 典型频率 | 低频、审慎、多人确认 | 高频、面向业务使用 |
| 失败结果 | 阻止发布，要求补材料或确认 | 在访问数据前澄清/拒绝，或停止并给出失败证据 |
| 发布节奏 | 业务语义和审批驱动 | 应用/runtime 独立发布，只消费兼容 Snapshot |
| 信任边界 | Governance control plane | Governed analytics runtime plane |

不能合并的永久不变量：

- Agent 不读取 Studio draft、原始治理附件或 reviewer comment；
- Agent 不直接修改 Metric、Mapping、Policy、Population 或 Ontology；
- Runtime identity 没有 semantic publish 权限；
- Studio identity 不因此获得事实数据的通配查询权限；
- 运行反馈不能自动升级为业务真相。

## 4. Product Domain A：Ontology Studio

### 4.1 Mission

把不完整、受限、需要人工转写和多轮确认的业务知识，转化为有来源、有 Decision、有独立验证和签署的 `GovernedSemanticRelease`。

### 4.2 当前 customer intake 前提

当前 PoC 不假设任何 customer 原始业务材料可以离开其安全环境。当前设计假设 External Review Team 可以按模板完成安全转写，但该能力和周转时间尚未通过真实往返验证：

- External Review Team 按简单模板人工转写需求、业务过程、分析流程、多条期望输出和指标逻辑；
- 数据模型、metadata/data dictionary、枚举、sample 结构和现有 SQL，只能以明确获准的安全重写、脱敏描述或客户区 locator 进入流程；
- 原始文档、原始数据、原始 SQL 和未获批准的 sample 不进入我方离线 PoC；
- 无法转写或无法确认的内容必须标为 `Missing / Withheld / Unconfirmed`，不能由模型补齐；
- 将来若获准在客户区直接读取文件，那是另一种 in-zone operating mode，不是当前方案的默认假设。

本规划中的 `Cleared Input` 指：由 Disclosure & Policy Approver 签署，带 input ID、classification、allowed use、opaque source locator、checksum、approved by/time 的转写或脱敏输入。`safe`、`cleared` 和 `approved safe attachment` 均以此定义为准，不能仅由提交人自称安全。

外部人员不需要填写 RDF、OWL、SHACL、Formula AST 或内部 Package schema。复杂结构化工作由我方 Ontology Operator 和工具完成。

### 4.3 Primary jobs

| 角色 | Primary job | 交接物 |
|---|---|---|
| External Reviewer Transcriber / Coordinator | 安全转写、说明边界、协调客户区确认 | Cleared Input、Question ID、状态 |
| Ontology Operator | 把输入人工编译为 Candidate，并暴露 Gap/Conflict | Candidate、Trace、Gap Queue |
| Domain Approver（业务 Domain Owner / Reviewer） | 确认定义、流程、例外、问题和预期边界 | Semantic Decision / Approval |
| Data Approver（Data Owner / Steward） | 确认 grain、binding、join、enum 和 data quality 含义 | Binding/Data Attestation |
| Disclosure & Policy Approver | 决定哪些内容可进入 runtime 和用户 evidence | Disclosure/Policy Attestation |
| Release & Activation Manager | 校验必需签署，发布不可变语义版本 | GovernedSemanticRelease |

具体人名是 Stage 1 implementation entry gate；本规划不虚构 customer 的组织安排。

### 4.4 MVP capability domains

当前 PoC 的 Studio 只承诺五个用户可见任务：

1. register cleared intake 与 source locator；
2. review input-to-candidate trace；
3. resolve 至少一个 Gap/Conflict 并记录 Decision；
4. 运行独立 gates 并发布 GovernedSemanticRelease；
5. triage 一条受治理 Semantic Change Request。

以下能力不是 Stage 1 MVP 承诺：通用自动抽取器、完整图谱编辑器、多人并发 workflow、企业 Data Catalog 替代、RDF 专用 UI、跨域 impact engine 和生产级电子签署。

### 4.5 Formal output：GovernedSemanticRelease

Studio 的正式下游产出是环境无关、不可变的 `GovernedSemanticRelease`，最低包含：

```text
semantic_release_id / semantic_version / schema_version / checksum
workspace identity
approved logical semantics
source and decision attestations
required capability constraints
binding and policy requirements（不是具体生产凭证）
disclosure classifications
compatibility contract
artifact inventory
```

它不包含某个运行环境的最终数据 binding、runtime build、active channel 或事实数据快照。Draft、Candidate、review comment 和未确认假设不能进入正式运行合同。

## 5. Product Domain B：Ontology Analytic Agent

### 5.1 Mission

让业务用户在已验证运行快照允许的范围内完成事实查询、比较、拆解和解释，并能说明每个答案使用了什么语义、运行组件、数据身份、政策决定和证据。

### 5.2 Primary jobs

| 角色 | Primary job |
|---|---|
| Analyst | 获得受治理事实、比较、排名、拆解和证据 |
| Business User | 用业务语言提问，并在歧义时得到具体澄清 |
| Executive | 获得简洁结论、关键驱动和可信边界 |
| Auditor / Reviewer | 查看授权范围内的定义、版本、Plan、Result 和 Decision identity |
| Application Consumer | 通过 API 消费同一受治理事实语义，但按 principal 获得不同披露投影 |

### 5.3 Activation input：VerifiedRuntimeSnapshot

Agent 不直接消费裸 `GovernedSemanticRelease`，只接受 activation pipeline 组装并验证的 `VerifiedRuntimeSnapshot`：

```text
snapshot_id / checksum
workspace / environment
exact semantic_release checksum
environment binding bundle
policy bundle
operator and runtime manifest
data identity / watermark
control evaluation
required attestation set
compatibility result
```

### 5.4 Per-execution input

每次执行还必须获得可信 principal、workspace、purpose/policy context、用户问题、执行预算，以及获准的 Query Engine / typed analytic tools。Snapshot 是激活输入；这些是单次请求输入，二者不能混为一个对象。

### 5.5 Core capabilities

1. Snapshot discovery、pinning 和 exact compatibility verification；
2. intent、metric、period、dimension 和 member resolution；
3. clarification、refusal 和 policy gate；
4. Atomic Query Contract 与 Governed Analysis Plan；
5. scenario adapter 和 deterministic operator/query execution；
6. result validation 与 reconciliation；
7. Typed Fact、Typed Claim 和 evidence-bound rendering；
8. execution history 与 evidence replay；
9. typed Semantic Change Request；
10. 明确的 Unsupported / Failed 结果。

没有可寻址历史数据快照时，只承诺 `evidence replay`，不承诺相同数据上的 `historical re-execution`。在新数据上重跑必须产生新 Execution，不能覆盖旧证据。

### 5.6 Non-goals

- 不读取或执行 Studio draft；
- 不让 LLM 自由决定数字、公式、SQL、population、join 或 policy；
- 不用固定 demo role 冒充生产 IAM；
- 不把无 Claim 的自然语言当成事实；
- 不承诺回答 Snapshot 未注册的任意问题；
- 不把 synthetic control 称为 customer 业务验证。

## 6. Shared Semantic Contracts & Kernel

当前共享层是两个 Product Domain 之间的最小合同和代码内核，不是第三个用户产品，也不预先声称是企业平台。

### 6.1 当前承诺范围

- Canonical IDs、namespace 和最小 typed schemas；
- Semantic Release、Runtime Snapshot、Activation、Revocation manifest；
- exact compatibility evaluator 与 integrity verification；
- attestation、Evidence、Execution 和 Change Request envelope；
- deterministic projection 与最小 audit event contract；
- Average Daily Turnover（ADT，平均每日成交额）adapter 接口，但不声称是通用 compiler。

RDF/JSON-LD 可以作为治理投影，SHACL 可以用于结构约束；OWL reasoning 和 SPARQL governance query 只在明确场景收益下采用。当前运行主合同仍以 typed JSON/YAML/schema 为主，不把 RDF、OWL、SPARQL、SHACL 四件套强行变成产品依赖。

### 6.2 后置能力

- 通用 Ontology compiler；
- 跨场景 Formula/operator SDK；
- 企业级 Registry、HA、PKI 和跨环境签名；
- 多 tenant/workspace 平台；
- Catalog、MDM、Semantic Layer 联邦；
- 完整 Knowledge Center。

只有第二个有实质差异的场景完成 core-change ledger 后，才能判断哪些能力真正值得平台化。

## 7. 两个 Product Domain 的正式合同

### 7.1 Downstream chain

```text
Cleared Input（External Reviewer安全转写/获批附件）
                         ↓
                Ontology Studio
                         ↓
              GovernedSemanticRelease
                         ↓
       Runtime Activation Pipeline / Shared Kernel
                         ↓
               VerifiedRuntimeSnapshot
                         ↓
              Ontology Analytic Agent
                         ↓
      Answer / Clarify / Refuse / Failed + Evidence
```

最低握手不再使用一个笼统的 `validation_status: PASS`：

```yaml
semantic_release:
  id: ontology.exchange_analytics.adt
  version: 1.0.0
  checksum: sha256:...
runtime_snapshot:
  id: snapshot.synthetic.adt.v1
  checksum: sha256:...
  workspace: poc
  environment: synthetic-reference
  semantic_release_checksum: sha256:...
  compatibility_mode: exact-match
  required_attestations:
    - semantic_approval
    - binding_data_validation
    - disclosure_policy_clearance
    - runtime_capability_compatibility
    - control_golden_evaluation
```

Stage 1 使用 exact-match compatibility；在第二场景前不建设推测性的通用 range resolver。

### 7.2 Five independent trust gates

五道 gate 不在同一个生命周期点执行。Semantic Approval 允许发布环境无关的 GovernedSemanticRelease；其余四道 gate 在**未激活的 RuntimeSnapshotCandidate verification mode**中执行。Verification mode 只能使用获准的测试 principal、数据和 Query Engine path，不能接收普通业务流量。

| Gate | Phase / attestation subject | 证明什么 | Accountable role |
|---|---|---|---|
| Semantic Approval | pre-publish；`semantic_content_checksum` | 转写完整度、定义、范围、时间、单位和例外已确认 | Domain Approver |
| Binding & Data Validation | pre-activation；`binding_bundle_checksum + data_identity` | grain、mapping、join、enum、data quality 和 control identity 已确认 | Data Approver |
| Disclosure & Policy Clearance | pre-activation；`projection_policy_checksum` | runtime/user 可见内容和政策组合已批准 | Disclosure & Policy Approver |
| Runtime Capability Compatibility | pre-activation；`snapshot_payload_checksum` | required operator、schema 和 failure semantics 兼容 | Runtime Capability Owner |
| Control / Golden Evaluation | pre-activation verification；`snapshot_payload_checksum + control_manifest_checksum + suite_checksum` | 预登记 control、4 Answered、1 Clarify、3 Refused 和 mutation suite 通过 | Independent Control Reviewer |

可执行顺序固定为：

```text
Cleared Input → Candidate / Decision
→ Semantic Approval
→ publish GovernedSemanticRelease
→ build unactivated RuntimeSnapshotCandidate
→ Binding/Data + Disclosure/Policy + Runtime Compatibility + Golden/Control verification
→ seal VerifiedRuntimeSnapshot as Ready
→ environment Activation
→ normal Agent traffic
```

`snapshot_payload_checksum` 是不含 gate attestation refs 的候选运行载荷 digest；五份 attestation 齐全后，最终 `VerifiedRuntimeSnapshot checksum` 再覆盖 payload 和 attestation set，避免自引用循环。任一必需 gate 缺失或失败，都不能 Ready 或 activation。

这里的 independent 首先指五份 attestation 具有独立 checksum、判定结果和失败语义。Stage 1 可由同一自然人切换 simulated principals 执行大部分 gate，但必须标记为 simulated separation of duties；Reference Truth Owner 与 Independent Control Reviewer 必须是不同自然人。这不等于企业 IAM 或真实多人审批。

### 7.3 Authorized projections

同一已批准对象按最小披露产生三种确定性视图；projection 只能隐藏或脱敏字段，不能改变 canonical ID、value、unit、period、population 或 decision identity：

| Projection | 消费者 | 允许内容 | 默认禁止 |
|---|---|---|---|
| Governance | Studio governance roles | source/decision、review、完整 attestation | 未授权 workspace 内容 |
| Runtime Service | Agent service / Query Engine | 执行必需的 semantics、binding、policy、capability | draft、原始附件、review comment |
| User Evidence | 当前 principal | 安全定义、Claim、版本、脱敏 lineage | 表列名、SQL、locator、未批准 policy reason |

具体 schema、ACL、DLP、sealed handle 和加密机制进入 Shared Product Contract / 技术方案，不在父级规划中写死。

### 7.4 Lifecycle

生命周期必须分开：

```text
DraftRevision: Draft → In Review → Validated → Approved / Rejected / Superseded
GovernedSemanticRelease: Published → Deprecated                 （内容不可变）
RuntimeSnapshotCandidate: Built → Verification
VerifiedRuntimeSnapshot: Ready → Quarantined / Retired
ActivationRecord: workspace + environment + channel → snapshot digest
RevocationRecord: append-only；revoked digest 永不重新激活
```

Rollback 不是修改历史或复活被撤销 digest，而是经过新的 activation decision，指向另一份仍有效、兼容的 Snapshot。

### 7.5 Upstream channels

Agent 到治理侧不再只有一个笼统上行通道：

1. `Semantic Change Request`：唯一可能触发 Ontology Candidate 的入口；
2. `Product Feedback`：进入产品 backlog，不进入 semantic lifecycle；
3. `Operational Incident / Telemetry`：进入运行和事故流程；
4. Revocation / capability control message：属于 Shared Kernel 控制合同。

Semantic Change Request 必须是异步、强类型、最小披露和不可信输入；默认不携带原始问题、结果、SQL、附件或完整 execution。它经 Studio triage 后仍只是 proposed input，不能自动成为 Candidate Claim 或业务真相。

## 8. End-to-end service blueprint

### 8.1 新场景

1. External Reviewer 提交 cleared transcription，并将不能提供的信息标记为 Missing/Withheld；
2. Ontology Operator 从该输入人工编译 Candidate，不从预制 Package 冒充构建；
3. Studio 展示 input-to-candidate trace、Gap 和 Conflict；
4. External Reviewer 协调 Domain Approver / Data Approver 在客户区确认，记录 Decision 与 control boundary；
5. Domain Approver 出具 Semantic Approval；
6. Release & Activation Manager 发布 GovernedSemanticRelease；
7. activation pipeline 绑定 synthetic/target environment，构建未激活的 RuntimeSnapshotCandidate；
8. 在 verification mode 完成其余四道 gate，封装 Ready 的 VerifiedRuntimeSnapshot；
9. Release & Activation Manager 建立 environment Activation；
10. Agent 通过正常用户入口重跑冻结 suite，验证与 pre-activation 结果一致，并产生一条 Semantic Change Request；
11. 结果与所有等待、返工和失败进入产品度量。

### 8.2 语义变更

1. Studio 基于获准需求或 Semantic Change Request 创建 DraftRevision；
2. 展示定义、依赖、binding requirement、control 和下游 capability 影响；
3. 重新走受影响的 gates，发布新 SemanticRelease；
4. activation pipeline 生成新 Snapshot；
5. Agent 只有在兼容与 activation 通过后升级；旧 execution evidence 不被覆盖。

### 8.3 未知问题

1. Agent 在 semantic binding 阶段停止，原则上不访问数据；
2. 用户得到具体 Clarify / Unsupported；
3. 经 policy 和披露检查后，可创建最小化 Semantic Change Request；
4. Studio 判断它是别名、缺失知识、缺失数据、缺失 operator 还是明确不支持；
5. 只有新 Release 和新 Snapshot 通过后，Agent 才获得新能力。

## 9. Trust、Policy 与故障结果

永久产品不变量：

- 可信 principal、workspace、purpose、release/snapshot 和 data classification 都是 policy 输入；
- IAM、Ontology Policy 和底层 Query Engine Policy 冲突时采用 deny-overrides；
- 查询前和披露前分别执行 policy gate；
- revoked digest 在任何 latest、pin、cache 或 rollback 路径都不可执行；
- Registry/revocation 状态超过允许 freshness window 后，新执行按 policy fail closed；
- partial query result 不得渲染成完整答案；
- Studio/feedback channel 故障不应破坏已完成答案，Semantic Change Request 使用异步交付；
- 原始治理材料、draft 和未批准物理信息进入普通用户 prompt/API/log 的数量必须为 0。

Stage 1 可使用 simulated principals、内容寻址文件、projection allowlist、revoked-digest denylist 和 hash-chained event ledger 证明这些结果。企业 IAM、KMS/DLP、WORM audit、实时 revocation、retention/legal hold 和 K8s network policy 是后续目标环境能力。

## 10. Product metrics

### 10.1 Product-family metrics

- Time to First Trusted Scenario；
- Trusted Scenario Completion Rate；
- 每个场景的确认轮次、active effort 和 client wait；
- 第二场景的 Shared Kernel reuse 与 core-change ledger；
- Supported-answer correctness；
- Coverage、Clarification、Refusal、Unsupported 和 Failed 分报；
- business/data owner 接受 control boundary 和 must-answer suite 的比例。

### 10.2 Studio metrics

- 有明确 source/decision 质量等级的对象比例；
- unresolved P0 ambiguity 数量和存续时间；
- cleared intake 到 approved SemanticRelease 的 lead time；
- input-to-candidate trace completeness；
- 发布前门禁发现的问题类型；
- semantic deprecate/revoke rate；
- Semantic Change Request 到 Decision 的时间。

### 10.3 Agent metrics

- Supported-answer correctness；
- 数字、方向、排名和限制的直接 Claim coverage；
- Clarification / Refusal precision；
- evidence replay completeness；
- p50/p95 latency 与 query cost；
- disputed answer rate 和根因分类。

问题集、标签和分母必须在运行前冻结；已运行问题不能删除或事后改成 unsupported 来优化指标。

## 11. 当前资产、已验证能力与缺口

| 能力 | 当前证据 | 结论 |
|---|---|---|
| Intake | 中英文简单模板和 ADT filled reference | 可试填；尚未经历真实 External Reviewer 往返和独立 operator 编译 |
| Studio UI | `ontology-console` Studio/Semantic Layer 页面 | 静态内存 demo；刷新丢状态，无真实 intake/candidate/review/publish API |
| Semantic package | typed YAML/Pydantic、validation、RDF projection | ADT adapter 可用；不是跨场景通用 compiler |
| Runtime | immutable snapshot reference、AQC/Plan、DuckDB、Claim、API | ADT vertical slice 可运行 |
| Evaluation | 33 tests、33 validation checks、8 Golden Questions | 证明 constructed synthetic regression；不是 customer business validation |
| ADT reference | public-style workbook/console 与 backend synthetic oracle | 两套数字和交易日冲突；当前均不能称 canonical business truth |
| Security/IAM | logical policy、API sanitization、demo principal | 无企业 IAM、真实职责分离、multi-workspace 或正式 audit |
| ARM/K8s | macOS ARM64 本机通过 | Linux ARM64、container image 和 customer K8s 未验证 |

成熟度判断：Agent runtime 比 Studio 更接近可运行 vertical slice。下一轮实现价值不在继续堆 Agent 能力，而在补一条真实 `cleared intake → candidate/decision → SemanticRelease → RuntimeSnapshot → answer/change` 链。

### 11.1 当前 ADT candidate 与证据定位

下表路径均相对 workspace root：`<workspace>`。

| Candidate | 已知差异 | 当前用途 | Evidence locator |
|---|---|---|---|
| `adt.public.reference.candidate` | Workbook：Q3 65日、ADT 286,355.553846；Q4 61日、ADT 229,799.803279。Console 因分类值舍入，显示 286,355.569231 / 229,799.786885。 | 仅 illustrative public-style reference | `outputs/atlas_ontology_intake_20260818/customer_ADT_Filled_Example_v0.1.xlsx`；`ontology-console/app.js` |
| `adt.synthetic.v1` | Q3 63日、ADT 130,317.460317；Q4 61日、ADT 110,491.803279。 | 当前 backend regression baseline | `ontology-agent-poc/scenarios/adt/golden/oracle.json`；`ontology-agent-poc/scenarios/adt/ontology/package.yaml` |

两者不是舍入即可解释的同一真相。Console 还存在自己的计算/发布逻辑，Stage 1 必须改为消费统一 API/Snapshot，不再保留第二套事实引擎。

### 11.2 ADT truth pre-registration gate

在 Stage 1 修改 fixture、oracle 或 UI 前必须：

1. 登记 public-reference 与 current synthetic 两个候选，禁止混称；
2. 预先冻结来源可核验性、formula、period、trading days、population、segment、unit、rounding 和合法展示标准；
3. 任命不同的 `Reference Truth Owner` 与 `Independent Control Reviewer`；
4. 每个候选必须先形成一份非 Package/oracle 的 Cleared Input；没有 `cleared_input_id + cleared_input_checksum + locator + approval_attestation` 的候选不得被选中。若选择 current synthetic，必须从需求/指标描述重新制作 safe-intake workbook，而不是把 `package.yaml` 或 `oracle.json` 交给 Ontology Operator；
5. 在 runtime output 之前冻结 `control_manifest_checksum`、expected values、tolerance，以及唯一 `suite_id + suite_checksum`；
6. 生成 `reference_manifest_checksum = hash(reference_case_id + cleared_input_checksum + control_manifest_checksum + suite_checksum)`；
7. fixture/adapter author 只能在上述 manifest 冻结后构造 synthetic detail；control 不得从 fixture/runtime 反推；
8. workbook、source pack、Package、dataset、oracle、API 和 UI 统一引用同一个 `reference_case_id + reference_manifest_checksum`，并分别保留自身 artifact checksum；
9. 当前 backend oracle 在此之前只作为 regression baseline，public workbook/console 只作为 illustration。

当前 `questions.yaml` 中 8 个 case（4 Answered + 1 Clarify + 3 Refused）是迁移起点，不另建第二套并行 Golden truth。Stage 1 将其重编并冻结为唯一的 `adt.tracer.v1.suite`；任何内容变化都产生新 `suite_checksum`。

即使最后选择 public-source control，synthetic fixture 对齐它也只证明执行链符合冻结 control，不构成 customer 内部业务验证。

## 12. 现在能做与不能做

### 现在能做

- 冻结 Product Family、两个 Product Domain 和永久信任边界；
- 写 Shared Product Contract v0.1；
- 在 Shared Product Contract Approved/Frozen 后，分别正式编写 Studio 与 Agent Product-Domain PRD；当前可以先准备访谈问题和 backlog 草案，但不得提前冻结两份 PRD 的合同定义；
- 统一 ADT reference 的选择流程和跨工件 identity；
- 用人工 compilation 构建 synthetic、single-user、端到端 tracer；
- 用轻量机制验证五类 gate、projection、activation/revocation 和 change loop；
- 用 External Reviewer 的下一份安全转写做 bounded discovery 和 gap analysis。

### 现在还不能做或不能声称

- 不能确定 customer 最终场景、指标定义、binding、control result 或业务正确性；
- 不能证明 External Reviewer 的真实转写能在目标时限内完成；
- 不能证明跨场景通用 compiler 或 Shared Platform；
- 不能确定两个商业 SKU、最终 UI 入口或采购模式；
- 不能承诺生产 IAM、审计、数据权限、Linux ARM64/K8s 或 SLA；
- 不能设计完整企业 Knowledge Center 或与 Catalog/MDM 的最终分工；
- 不能把 synthetic/public reference demo 称为 customer 真实业务验证。

## 13. Roadmap and decision gates

### Stage 0 — Product contract baseline

顺序：

1. 批准本 Product Family Strategy；
2. 编写 `Shared Product Contract v0.1`；
3. 在共享合同冻结后，可并行编写 Studio 与 Agent Product-Domain PRD；
4. 将技术选择写入 ADR/technical design，而不是用五份水平文档阻塞 vertical slice。

退出条件：两个 PRD 对 Release/Snapshot、projection、gate、lifecycle 和 Change Request 没有不同解释。

Shared Product Contract 状态为 `Draft → Reviewed → Approved/Frozen`；只有 Decision Owner 将其置为 Approved/Frozen 后，两份 Product-Domain PRD 才正式启动。

### Stage 1 — ADT trusted-flow tracer

目标：把“手工 Package + 静态 console + 独立 runtime”改成一条真实用户可见的 synthetic chain。

最小闭环：

```text
Step 0: §11.2 truth pre-registration
→ cleared_input_id + cleared_input_checksum + locator + approval_attestation
→ control_manifest_checksum + suite_id + suite_checksum
→ select reference_case_id
→ calculate and freeze reference_manifest_checksum
→ independent Ontology Operator只读取该Cleared Input（禁止读取预制Package/oracle/fixture）
→ persisted candidate + trace
→ gap + decision
→ Semantic Approval → immutable GovernedSemanticRelease
→ unactivated RuntimeSnapshotCandidate
→ 4个pre-activation gates，含adt.tracer.v1.suite verification（4 Answered + 1 Clarify + 3 Refused）
→ seal Ready VerifiedRuntimeSnapshot → activation
→ 通过正常Agent API重跑同一8-case suite并核对一致性
→ typed Semantic Change Request visible and triaged in Studio
```

范围假设：单一 ADT、单环境、single-user、file/local persistence、simulated principals、无企业 IAM/DB/K8s。Stage 1 不依赖 customer/External Reviewer 响应；Domain Approver / Data Approver 由明确标为“非客户验证”的模拟角色执行。

初步工作量：`16–24 person-days ROM`，low-to-medium confidence，约 `±35%`；不是交付承诺。先用 1–2 person-days 完成 reuse/slice spike、DRI 和 interface，随后重估。

重估触发器：Console 不可复用；加入多人 workflow/DB/IAM；public source 无法独立核验；需要目标环境；引入新 operator/join/time semantics；需要企业 DLP。

Stage 1 exit gate：

- 所有工件引用同一 `reference_case_id + reference_manifest_checksum`；manifest 内的 `cleared_input_checksum`、`control_manifest_checksum` 和 `suite_checksum` 均可独立验证，跨工件引用差异为 0；
- 独立 operator 只从 Cleared Input 重建 Candidate，答案依赖链的 trace completeness 为 100%；
- 至少一个 Missing/Withheld fail closed，至少一个真实 ambiguity 经 Decision 解除；
- Semantic Approval 后才能发布 GovernedSemanticRelease；其余四道 gate 只在未激活 SnapshotCandidate verification mode 运行；五类 attestation 全部 PASS 后才可 Ready/activate；
- 删除或篡改任一 attestation 都阻止 Ready/activation；verification mode 不接收普通业务流量；
- subject-artifact mutation matrix 必须覆盖 `cleared_input_checksum`、`reference_manifest_checksum`、`semantic_content_checksum`、GovernedSemanticRelease checksum、`binding_bundle_checksum`、`projection_policy_checksum`、`snapshot_payload_checksum`、`control_manifest_checksum`、`suite_checksum` 和最终 VerifiedRuntimeSnapshot checksum；任一对象变化而其 attestation/引用未更新时，必须在 Query Engine 访问前失败；
- 现有 33 validation checks、33 automated tests 和唯一 `adt.tracer.v1.suite` 在 pre-activation 与 active Agent API 两条路径均全部通过，结果和 evidence identity 一致；
- 所有展示数字、方向、排名和限制的 direct Claim coverage 为 100%；
- revoked digest 的 Query Engine 访问次数为 0；projection 与 Change Request 的 secret-canary 泄漏数为 0；
- publish、activate、revoke、execute、change/triage 的 event completeness 为 100%；
- 浏览器刷新后 Candidate、Decision、Release、Activation 和 Change Request 状态不丢；
- UI、报告和 runbook 明示 synthetic reference、simulated roles、非 customer 业务验证。

### Stage 2 — External Review Team validation-scenario discovery and adapter

这是相对于 ADT synthetic reference 的首个 External Reviewer/customer discovery 场景。先做 3–5 天 bounded discovery，不在场景未知时给 25–50 人日假精度。Build readiness 至少需要：

- 明确场景、业务决策和 3–5 条优先问题；
- 至少一条 clarify/refuse；
- 关键指标的 scope、time、unit 和 exception；
- 安全转写的数据模型/字典/SQL逻辑，或明确 Missing/Withheld；
- 客户区内 control result 验证路径；
- named business/data owner。

若第二场景要作为泛化证据，它至少应在两个语义维度和一个 binding/execution 维度上与 ADT 不同；否则只能称相邻实例。完成后记录 shared-core diff，泛化结论仅限两个验证过的场景。

### Stage 3 — Target environment integration

目标：Linux ARM64/K8s、IAM、Query Engine、Registry、audit、secret、network policy 和受控发布链。只有环境发现完成后估算。

### Stage 4 — Productization and Knowledge Center decision

两个以上有实质差异的场景暴露稳定共享需求后，再决定：

- 独立 SKU / UI / deployment；
- Shared Kernel 是否升级为 Platform；
- Catalog/MDM/Semantic Layer 联邦；
- 跨域 Ontology 与 Knowledge Center；
- SLA、support model 和商业包装。

## 14. Ownership and implementation entry gates

以下是唯一的 canonical role registry。别名只能用于沟通，合同和 gate 使用 canonical name：

| Canonical role | 可接受别名 | 核心责任 / gate | Stage 1 | 兼任规则 |
|---|---|---|---|---|
| Decision Owner | Muyu | 批准 Strategy 与 Shared Product Contract | 必需 | 不替代各执行 owner |
| Product & Delivery DRI | Delivery DRI | scope、依赖、节奏、ROM 和 demo outcome | 必需、落实人名 | 可兼任 Studio Domain Owner 或 Agent Domain Owner |
| Studio Domain Owner | Studio Product Owner / Studio DRI | intake、candidate、decision、semantic publish 产品责任 | 必需、落实人名 | 可执行模拟角色，不可冒充客户确认 |
| Agent Domain Owner | Agent Product Owner / Runtime DRI | snapshot、execution、claim、change loop 产品责任 | 必需、落实人名 | 可兼任 Runtime Capability Owner |
| Shared Contract Owner | Stage 1 Architecture Owner | schema、compatibility、projection、activation/revocation 合同 | 必需、落实人名 | 不得用“平台团队”代替个人责任 |
| Ontology Operator | Independent Intake Operator | 只从 Cleared Input 编译 Candidate、Trace、Gap 和 Decision proposal | 必需、落实人名 | Candidate 冻结前不得读取现有 Package、oracle、fixture 或 expected runtime result；优先由非现有 Package 作者担任 |
| Fixture & Adapter Author | Execution Fixture Author | 在 reference manifest 冻结后构造 synthetic detail 和 adapter | 必需、落实人名 | 不得兼任 Independent Control Reviewer；不得修改冻结 control |
| Domain Approver | Domain Owner / Semantic Approver | `Semantic Approval` gate | 必需、可模拟 | 生产高风险变更不得自批 |
| Data Approver | Data Owner / Data Steward | `Binding & Data Validation` gate | 必需、可模拟 | 生产高风险变更不得自批 |
| Disclosure & Policy Approver | Security / Disclosure Owner | `Disclosure & Policy Clearance` gate；签署 Cleared Input | 必需、可模拟 | 生产必须有真实授权 |
| Runtime Capability Owner | Runtime Owner | `Runtime Capability Compatibility` gate | 必需、可由 Agent Domain Owner 兼任 | 不能修改 semantic approval |
| Reference Truth Owner | Truth Owner | 选择并冻结 reference case | 必需、落实人名 | **不得**与 Independent Control Reviewer 为同一自然人 |
| Independent Control Reviewer | Control Reviewer | 独立重算；`Control / Golden Evaluation` gate | 必需、落实第二人 | 不得实现 fixture/oracle，也不得兼任 Truth Owner |
| Release & Activation Manager | Release Manager | 检查 gates、publish、activate、revoke | 必需、可模拟 | 生产高风险变更与 author/approver 分离 |
| External Reviewer Coordination Lead | External Reviewer Lead | 转写协调和客户区确认往返 | Stage 2 必需 | Stage 1 不依赖其响应 |
| Target Platform Owner | HK Platform Owner | ARM/K8s、IAM、Query Engine 和环境准入 | Stage 3 必需 | 当前不得伪造人选 |

Stage 1 中“可模拟”表示同一自然人可切换显式测试 principal，用来证明 workflow enforcement，不代表真实职责分离。除 Reference Truth Owner 与 Independent Control Reviewer 必须为不同自然人、Fixture & Adapter Author 不得兼任 Independent Control Reviewer 外，其他分离在 production scope 才强制。Ontology Operator 的“independent”最低含义是 blind rebuild：Candidate 冻结前没有 Package/oracle/fixture/expected runtime result 的读取路径，并留下访问与输入清单；它不自动要求新增第三位自然人。每个合同、gate、SLO 和事故类别仍只能有一个 accountable role。

## 15. 主要风险与控制

| 风险 | 当前控制 | 下一证据 | 决策角色 |
|---|---|---|---|
| 安全转写不足以构建场景 | 简单模板、Missing/Withheld、Gap/Decision流程 | 独立operator完成ADT，再由External Reviewer Coordination Lead协作真实场景 | Product & Delivery DRI |
| Studio变成复杂技术编辑器 | 五个MVP task，内部schema与外部输入分离 | proxy user task test | Studio Domain Owner |
| 两个PRD产生不同合同 | Shared Product Contract先行 | cross-PRD contract review | Shared Contract Owner |
| ADT双真相损害demo | truth pre-registration和唯一reference ID | cross-artifact consistency tests | Reference Truth Owner |
| “Trusted”被单一PASS伪造 | 五类独立attestation | missing/fail mutation tests | Release & Activation Manager |
| Coverage被误当Correctness | correctness/coverage/clarify/refuse分报 | frozen suite | Agent Domain Owner |
| Shared Kernel过度抽象 | 第二场景前只保留最小合同 | scenario core-change ledger | Shared Contract Owner |
| 目标ARM/K8s不兼容 | 当前仅标记Not Assessed | Linux ARM64 build + cluster smoke | Target Platform Owner |

## 16. 冻结决策、假设与否决方案

### 16.1 现在冻结

- 一个 Product Family、两个独立 Product Domains；
- 分别编写 Product-Domain PRD 和技术方案；
- Studio control plane 与 Agent runtime plane 的永久权限边界；
- `GovernedSemanticRelease → VerifiedRuntimeSnapshot → Activation`；
- 三种授权 projection 和五类独立 gate；
- Semantic Change Request 不直接写回 Ontology；
- revoked digest 不可重新激活；
- Shared 层当前只是 Contracts & Kernel；
- Knowledge Center 后置。

### 16.2 继续作为假设

- 两个独立商业 SKU、顶层 UI、品牌、采购路径或 Deployment；
- Studio 的长期主要买方和 operating owner；
- Agent 独立入口还是嵌入 BI/门户；
- 企业 Registry、workflow、policy、audit 的具体技术；
- 第二场景所需 operator 和 shared-core 变化；
- 生产容量、SLA、成本和 support model；
- customer 真实职责分离和审批角色。

### 16.3 明确否决

- 单一混合权限的“Ontology + Chat”产品；
- 把 Studio 降成 Agent 内部配置模块；
- 把 Registry 现在包装成第三个商业产品；
- Agent 自动修正或发布 Ontology；
- 在第二场景前建设通用 compiler；
- 先建设完整 Knowledge Center；
- 用预制 Package 冒充 intake-to-release；
- 同时保留两套未标识的 ADT 真相；
- 没有数据 time travel 却承诺 historical re-execution。

## 17. Completion and next gate

本规划作为后续文档父级输入的条件：

- [x] 三个独立评审视角完成 Round 1；
- [x] 三方完成 Round 2 交叉质询并纠正自身主张；
- [x] 文档级 P0 已在 v0.6 关闭；
- [x] Product Domain、Release/Snapshot、projection、gate、lifecycle 和上行通道边界已明确；
- [x] 当前成熟度没有把静态 Studio demo、synthetic oracle 或本机 ARM 夸大为生产能力；
- [x] PoC、近期产品化和长期 Knowledge Center 已分开；
- [x] Fresh-reader test 8/8 可准确复述，P0=0；唯一 P1 owner 歧义已在 v0.6 关闭；
- [x] Decision Owner 已批准，v1.0 成为后续合同、PRD 和技术方案的父级 Baseline。

下一项不是直接写 Studio 技术方案，而是先形成简短的 `Shared Product Contract v0.1`，再开始两份 Product-Domain PRD。这样两个产品不会在最关键的上下游对象上各自发明一套定义。

## Appendix A — 本项目术语表

| Term | 本项目内定义 |
|---|---|
| ADT | Average Daily Turnover，平均每日成交额；本 PoC 的 reference scenario。 |
| Product Domain | 拥有独立用户任务、对象、权限、状态和 backlog 的产品边界；不自动等同商业 SKU。 |
| Cleared Input | 经 Disclosure & Policy Approver 签署、记录分类/用途/locator/checksum 的安全转写或附件。 |
| Candidate | 尚未确认、等待 review/decision 的结构化语义候选。 |
| Decision | 对 ambiguity、conflict 或 missing information 的明确人类裁决及其证据。 |
| Binding | 逻辑业务概念到物理数据表、字段、枚举、join 或 Query Engine contract 的映射。 |
| Control | 在实现运行结果前冻结、用于验收公式和输出边界的期望值或行为。 |
| Oracle | 保存 control expected result 的受版本管理工件；不因名称自动获得业务权威。 |
| Fixture | 为测试构造的合成明细数据；它符合 control 不等于 control 获得独立证明。 |
| Reference case / `reference_case_id` | 被选为 tracer 基线的唯一场景身份；其 manifest 固定 Cleared Input、control 和 suite 的版本关系。 |
| Truth pre-registration | 在 fixture/runtime 运行前先冻结来源、公式、expected values、tolerance、suite 和 reviewer 的过程。 |
| Control manifest | 保存 expected values、单位、期间、tolerance、来源与签署的版本化工件。 |
| Reference manifest checksum | 对 reference identity、Cleared Input、control manifest 和 suite checksums 的组合摘要；所有下游工件共同引用它。 |
| Golden suite | 运行前冻结、同时包含 Answered/Clarify/Refuse 预期的验收问题集；Stage 1 唯一 suite 为 `adt.tracer.v1.suite`。 |
| Ontology Operator | 将 Cleared Input 人工编译成 Candidate/Gap/Decision 的人；不同于执行公式的 deterministic runtime operator。 |
| RuntimeSnapshotCandidate | 尚未激活、只允许在 verification mode 中接受四道运行 gate 的候选快照载荷。 |
| Principal | 由可信身份系统提供的用户或服务身份。 |
| Purpose context | 本次访问的获准业务目的，作为 policy 输入。 |
| Attestation | 针对某个 checksum、由明确角色出具的独立 PASS/FAIL/签署记录。 |
| Projection | 从已批准对象按 audience 确定性隐藏/脱敏字段得到的视图，不改变语义值。 |
| GovernedSemanticRelease | Studio 发布的环境无关、不可变业务语义合同；可简称 Semantic Release。 |
| VerifiedRuntimeSnapshot | 精确引用 Semantic Release，并绑定环境、policy、runtime、data/control 后形成的可执行快照。 |
| Activation | 在特定 workspace/environment/channel 允许某个 Snapshot 被新执行使用的决定。 |
| Revocation | 针对 artifact digest 的不可逆禁止执行记录。 |
| AQC | Atomic Query Contract；Agent 交给确定性执行层的最小、受约束查询合同。 |
| Fact / Claim | Fact 是执行结果中的结构化事实；Claim 是可展示结论及其直接 evidence 绑定。 |
| Data identity / watermark | 标识本次执行所见数据状态的版本、快照或可审计时间点。 |
| Evidence replay | 重现当时保存的 Plan、Result、Claim 和 Evidence；不重新访问历史数据。 |
| Historical re-execution | 对同一历史数据状态重新执行；只有底层支持可寻址 time-travel data 时才可能。 |
| ROM | Rough Order of Magnitude，粗粒度范围估算，不是交付承诺。 |
| DRI | Directly Responsible Individual，某项工作唯一直接负责人。 |
| Core-change ledger | 第二场景接入时记录 shared kernel 新增、修改、复用和场景特例的清单。 |
