# Ontology Studio Product-Domain PRD v0.1

Document ID：`ontology-studio-prd/0.1`  
状态：Revised Candidate；Pending Fresh-reader Closure and R-01 Decision；not implementation authority  
日期：2026-08-19  
Decision Owner：Muyu  
Accountable Product Owner：Studio Domain Owner（V0 前落实人名）  
规范性父级：`01_product_group_strategy.md` v1.0、`02_shared_product_contract.md` v0.1 Approved/Frozen  
当前冻结 Profile：`synthetic-trusted-flow/core@1`（ADT synthetic reference tracer）  
待决 Profile revision：`synthetic-trusted-flow/core@1.1` Revision Pack R-01（E-01 `CONCEPT_NOT_BOUND` + E-02 `SELECT_REFERENCE`）  
共同产品附件：`stage1-demo-delivery-companion/0.1`；file digest `sha-256:800d15d41fb2ad9143eac14d0f13a9297f18afe6bf704e1bce4e8b466e4a8b74`  
评审裁决：`reviews/product-prds-round-2-adjudication.md`

## 0. 如何阅读

本 PRD 定义 Ontology Studio 作为独立 Product Domain 的用户问题、任务、产品行为和 Stage 1 验收。它不重复 Shared Product Contract 的 digest/schema 细节，也不决定最终 SKU、仓库、部署数量或技术框架。

发生冲突时，优先级为：Shared Product Contract > Synthetic Profile > 本 PRD > 后续技术设计。本文中的界面名称是产品任务分区，不等于必须建设五个独立页面。

`05_stage1_demo_delivery_companion.md` 只定义两产品共用的 demo promise、最小表面、RACI 和 delivery evidence；它不是第三个产品或 runtime authority。

本文生命周期固定为 `Draft → Revised Candidate → Reviewed Candidate → Approved/Frozen → Superseded`。当前为 Revised Candidate；Reviewed Candidate 表示独立 closure review 已通过，仍不等于 implementation authority；只有 Decision Owner 对两份 PRD 与 exact Companion revision/digest 的原子批准才形成 Approved/Frozen。

### 0.1 Product at a glance

| Question | Stage 1 answer |
|---|---|
| Primary user/job | Transcriber 安全表达业务材料边界；Operator 建立可追溯 Candidate；Reviewer 解决 Gap；Approver 发布 exact semantics |
| Product input | approved ClearedInput；Reference Truth Owner 已冻结的 exact ReferenceManifest；human Decisions；valid typed SCR |
| Visible outcome | persisted Trace/Gap/Decision、Semantic Approval/GSR receipt、safe Change Inbox disposition |
| Formal handoff | Studio 唯一正式下游语义输出是 immutable environment-independent GSR |
| Fail closed | raw/unapproved input、wrong selector、missing trace slot、unresolved release gap、wrong approval subject、invalid SCR chain |
| Must never happen | Studio 选择业务真相、读取 Agent facts 作 truth、把 draft/评论交给 Agent、把 ACCEPTED feedback 当 confirmed Ontology |
| Stage 1 promise | 用 constructed-synthetic ADT 证明一条 safe intake → human decision → GSR → safe triage 链；不证明 HKEX truth 或 production workflow |

## 1. Product Decision

Ontology Studio 是企业语义建设与治理控制面，不是 Analytic Agent 的“配置页”。它解决的问题是：在原始材料不能离开客户安全区、输入只能人工安全转写、定义可能缺失或冲突的条件下，把可用知识转成有来源、有人工 Decision、有明确边界、可验证且可版本化发布的 `GovernedSemanticRelease`（GSR）。

Studio Domain Owner 对 V0 产品结果负责，但不选择 reference truth。Reference Truth Owner 按冻结 Profile 选择并冻结 exact reference；Studio 只消费由此形成的 ReferenceManifest。Stage 1 feedback 只到安全人工分诊，不完成 ontology 自动更新闭环。

当前 Frozen `core@1` 只描述选择顺序与角色，没有 `SELECT_REFERENCE` action、proposal/AuthorityDecision 或 final manifest binding。本文要求的授权选择是 R-01/E-02 的 `core@1.1` candidate；在其获批并通过 Profile/Annex/vector review 前，不得实现或声称 conformant selection command，V0 conformance 保持 blocked。

Stage 1 只证明一条 ADT synthetic vertical tracer：

```text
ClearedInput
→ blind Candidate + complete Trace
→ Gap / Conflict + human Decision
→ immutable GSR PublishSubject
→ exact Semantic Approval PASS
→ PUBLISH AuthorityDecision
→ immutable GSR
→ safe UNKNOWN_CONCEPT SCR triage
```

Studio 的唯一正式下游语义产出是 GSR。Candidate、draft、review comment、未批准附件和未确认假设都不是 Agent 输入。

## 2. Problem Statement

企业的需求、指标、流程、数据模型、数据字典和已有 SQL 通常分散在不同人员与文档中。对 HKEX PoC 而言，问题更严格：原始业务材料不能离开安全区，Deloitte HK 只能按要求人工转写解释性内容；缺失信息也不能由模型补齐。

当前资产已经能展示 Ontology 对象、编辑少量指标/映射、运行校验并发布一个本地 package，但尚未形成以下产品能力：

- 获批输入与普通文件之间的明确边界；
- 从 ClearedInput 独立重建 Candidate 的 blind workflow；
- 每个发布语义到输入与 Decision 的完整 Trace；
- Gap、Conflict、Missing、Withheld 与人工 Decision 的持久生命周期；
- exact-subject Semantic Approval 与授权发布；
- 环境无关的 GSR，而不是把 package、数据、control 和 runtime 混成一个快照；
- 安全、可行动但不自动成为真相的 Agent feedback inbox。

没有这些能力，现有 demo 可以解释想法，却不能证明“企业知识如何被治理后供应用消费”。

## 3. Goals and Non-goals

### 3.1 Goals

1. 让安全转写输入以明确身份、分类、用途、审批和 locator 进入 Studio。
2. 让 Ontology Operator 只从选定 ClearedInput 构建 Candidate，并留下完整 Trace。
3. 让业务 Reviewer 能看懂并解决具体 Gap/Conflict，而不必编辑 RDF、OWL、SHACL 或内部 schema。
4. 让语义发布只发生在 exact PublishSubject 的 Semantic Approval 与 PUBLISH AuthorityDecision 均有效之后。
5. 让下游只获得环境无关、不可变且可寻址的 GSR。
6. 让受治理的 UNKNOWN_CONCEPT feedback 可被安全分诊，但不能自动改变 Ontology。
7. 为第二个真实场景保留可比较的 intake effort、gap 类型和 core-change evidence 结构，但不在 Stage 1 声称已验证泛化。

### 3.2 Non-goals

- 通用自动文档抽取器或“一键生成 Ontology”；
- 要 Deloitte/HK 或业务 Reviewer 填写内部 ontology schema；
- 完整图谱编辑器、任意 RDF/OWL authoring UI 或企业知识图谱平台；
- 多人并发工作流、生产电子签名、IAM、PKI、DLP 或 WORM audit；
- 企业 Data Catalog、MDM、Semantic Layer 或 Knowledge Center 替代；
- 在 Studio 内执行普通业务事实查询；
- 从 Agent telemetry 或 SCR 自动创建 confirmed object、Claim 或 GSR；
- 证明 HKEX 业务定义正确或客户已确认；
- 决定最终商业 SKU、顶层导航或独立 deployment。

## 4. Users and Jobs-to-be-Done

| User / role | Primary job | Product outcome |
|---|---|---|
| Deloitte Transcriber / Coordinator | 按允许范围转写需求、过程、指标逻辑和材料边界 | 可登记的 input proposal、明确 Missing/Withheld |
| Disclosure & Policy Approver | 决定某份转写/附件可否及如何进入 ontology workflow | ClearedInput approval 或安全拒绝 |
| Reference Truth Owner | 按预登记标准选择并冻结 exact reference case | 唯一 selected ReferenceManifest；不能由 Studio Owner 代替 |
| Ontology Operator | 只从 ClearedInput 编译 Candidate，暴露来源、缺口和冲突 | Candidate、Trace、Gap/Conflict queue |
| Domain Approver | 确认定义、范围、公式、时间、单位、例外与 Decision | exact Semantic Approval PASS/FAIL |
| Release & Activation Manager | 校验 publish prerequisites 并提交不可变语义版本 | PUBLISH AuthorityDecision、GSR |
| Data / Runtime / Control reviewers | 读取 GSR requirements，为后续 environment verification 做准备 | 只读、最小授权的 Governance Projection |
| Studio Domain Owner | 管理范围、质量、backlog 和失败责任 | 可验收的 Studio product outcome |

Stage 1 允许模拟部分角色，但所有角色切换必须形成不同的 principal/AuthorityDecision 记录。Reference Truth Owner 与 Independent Control Reviewer 必须是不同自然人；Fixture Author 不得兼任 Control Reviewer。

## 5. Current Baseline and Reuse Boundary

| Asset / behavior | Reuse | Gap before conformant Studio |
|---|---|---|
| 现有静态 Console 的 Ontology / Mapping / Validation 任务布局 | 复用任务模型和交互语言 | 内嵌事实、校验和发布逻辑不是 authority；无持久治理链 |
| Typed OntologyPackage 与 confirmed/proposed 状态 | 作为 migration/build source | 不能替代 ClearedInput、Candidate/Trace/Decision 或 GSR |
| 结构、来源、语义、binding、data、SHACL 检查 | 复用 deterministic checks | 必须重映射到冻结的五 gate 与 exact subjects |
| Immutable local package publication | 复用 canonicalization/immutability 经验 | 当前 package 混合 semantic/runtime/data/control；不是 GSR |
| RDF/JSON-LD、SHACL、SPARQL governance projection | 作为可选治理投影 | 不是用户输入格式，也不替代业务/Control gate |
| 双语标签与对象目录 | 可复用展示资产 | 语言切换不得改变 identity；Stage 1 不承诺完整本地化产品 |

现有 Package、oracle、fixture 和 runtime result 不能交给 blind Ontology Operator。它们只能在 Candidate/Decision/Semantic Approval 冻结之后进入隔离的 migration/runtime adapter。

## 6. Product Capability Modules

### 6.1 Intake Register

把外部提交变成可治理的 input proposal，并显示：input ID、classification、allowed use、已受控 safe artifact reference、opaque client-zone locator、limitations、提交人和审批状态。

Stage 1 ordinary Studio proposal boundary 只接受 closed metadata、opaque locator 和受控 proposal artifact ref；它不接受或 dereference raw document、raw data、raw SQL、sample、attachment body、resolvable content URL 或 unrestricted free text。Disclosure Approver 可在独立 restricted review boundary 审查人工安全转写；只有 exact ALLOW 后，allowlisted content projection 才能进入 Candidate workflow。不能提供的内容显式记录为 `Missing`、`Withheld` 或 `Unconfirmed`。

### 6.2 Candidate & Trace Workspace

Ontology Operator 从 Reference Truth Owner 已冻结的 selected ReferenceManifest 所引用的 ClearedInput 建立对象/关系/规则/指标/流程 Candidate。每个 candidate field 都能回到一个 ClearedInput locator 或一个明确的 Decision；无来源推断只能保持 proposed。

Operator 只获得 audience-specific `Operator Intake Projection`：包含语义构建所需陈述/locator，不包含 Control expected values、oracle、report target、Package、fixture 或 runtime result。若一个获批 source pack 无法把 semantic input 与 target/control content 安全分开，本轮不得声称 blind rebuild，而不是要求 Deloitte 重复转写。

在 Candidate 构建前，V0 预登记 versioned semantic validation profile，冻结 formula、grain/additivity、period/calendar、population/exclusions、dimensions/segments、unit/scale/rounding、limitations 和 release-impacting Missing/Withheld/Decision slots。Trace completeness 以该独立分母计算，不能从最终 Candidate 反推分母。

### 6.3 Gap, Conflict & Decision Queue

系统把问题写成具体、可回答的 Decision request，而不是笼统的“材料不足”。每项至少包含：问题、类型、受影响对象/字段、已知选项、来源差异、阻断范围、owner、Decision、依据、剩余假设和时间。

未解决且影响本 release 的项阻止 Semantic Approval。与 release 无关的项只有在 Domain Approver 明确记录“不影响当前 release 的范围 Decision”后才能留待后续。

### 6.4 Semantic Approval & Release Workspace

系统形成 immutable GSR PublishSubject，包含已批准语义、lineage/Decisions、binding/capability/policy/disclosure requirements 和 supersedes relationship。Domain Approver 只对 exact subject 作 PASS/FAIL；Release Manager 另行取得 PUBLISH AuthorityDecision 后才能提交 GSR。

GSR 不包含最终环境 binding、runtime build、active channel、DataIdentity 或事实数据快照。发布后不能原地修改；修正产生新 subject、新 version/digest 和显式 lineage。

### 6.5 Change Inbox

Stage 1 只接收完整通过 Shared Contract disclosure/enqueue chain、scope/expiry/ref 校验并绑定 committed boundary execution 的 `UNKNOWN_CONCEPT` SCR。任何链路/ref/payload 变动都必须在产生 inbox/work-item side effect 前失败，且不泄露对象是否存在。Reviewer 只能看到 allowlisted safe context、opaque refs 和 limitations，看不到 raw question、answer values、SQL、表列、prompt、path 或 unrestricted free text。

UI 状态 `TRIAGED → ACCEPTED / REJECTED / DUPLICATE / NEEDS_CONTEXT → CLOSED` 由 Studio 内部 append-only triage/disposition facts 派生；final SCR subject/digest 不修改。`ACCEPTED` 仅表示值得进入治理工作，不能自动生成 Candidate、GSR 或新 runtime capability。

## 7. Core User Journeys

### Journey A — Register safe input

1. 人工安全转写先在获准的 restricted review boundary 形成受控 artifact；ordinary Studio 不接收 raw HKEX bytes。
2. Transcriber 登记 closed metadata、opaque locator 和 safe artifact ref；Studio 验证必需 metadata，缺失内容不自动补齐。
3. Disclosure & Policy Approver 查看 exact proposal、classification、用途和限制。
4. ALLOW 后形成 ClearedInput 和 audience-specific projection；DENY 只保留最小获准 rejection/audit metadata，不产生可供 Candidate 使用的 input。

### Journey B — Blind build and review

1. Reference Truth Owner 按预登记标准提交 exact selection proposal；R-01/E-02 获批后，只有绑定该 proposal 的 `SELECT_REFERENCE` ALLOW AuthorityDecision 才可形成 ReferenceManifest；Studio Domain Owner 只发起/排期 V0，不拥有 selection command authority。当前 `core@1` 不支持该 command，必须 fail closed。
2. Studio 验证 selector、candidate、ClearedInput、Control/Suite/oracle refs 一致后，Ontology Operator 只获得 target-free Operator Intake Projection。
3. Operator 按预登记 semantic-slot denominator 建立 Candidate 和逐字段 Trace。
4. 系统产生 Gap/Conflict queue；至少一条 Missing/Withheld path fail closed，缺失 slot 不可从分母删除。
5. Reviewer 作出 Decision；所有 release dependency trace 达到 100%。

### Journey C — Approve and publish semantics

1. Studio 构建 immutable GSR PublishSubject。
2. Domain Approver 对 exact subject 出具 Semantic Approval PASS/FAIL。
3. Release Manager 对 exact publish action 获得 AuthorityDecision。
4. PASS + ALLOW 后提交 GSR；失败不修改旧 GSR。
5. 下游只能读取获准 projection，不读取 draft/candidate/comments。

### Journey D — Triage governed feedback

1. Agent durable outbox 提交 contract-valid、disclosure-cleared UNKNOWN_CONCEPT SCR。
2. Studio 在任何 visible side effect 前验证完整 inbound chain，并对 refs 与 SCR_TRIAGE action 重新授权；不信任请求自带解释。
3. Triager 在两分钟内选择 owner 与 disposition，或返回 NEEDS_CONTEXT。
4. 如 ACCEPTED，append 一个独立 disposition/work item；final SCR 不变，也不会直接修改 semantic truth。没有新 GSR/VRS/Activation 时，重复问题仍得到原 boundary outcome。

## 8. Functional Requirements

### 8.1 Intake and disclosure

| ID | Requirement | Stage 1 acceptance |
|---|---|---|
| STU-INT-01 | Studio 必须区分 input proposal 与 approved ClearedInput | 未获 AuthorityDecision 的 proposal 不能进入 Candidate build |
| STU-INT-02 | 必须保存 classification、allowed use、limitations、opaque locator、proposal/ClearedInput exact subject ref + `subject_digest` 与 approval identity；storage checksum 如有仅作 non-authority metadata | 任一 required field 缺失即 fail closed；storage checksum 不能替代 contract identity |
| STU-INT-03 | Missing / Withheld / Unconfirmed 必须是一等状态 | 模型或默认值不能把它们转成 confirmed |
| STU-INT-04 | Deloitte/外部输入不得要求 RDF、OWL、SHACL、AST 或内部 schema | 2 名 non-author proxy 用 blank common template 安全完成；internal schema input = 0；真实 Deloitte usability 标 Not Assessed |
| STU-INT-05 | 被拒或超范围内容不得进入 Candidate/runtime/public projection | cross-boundary canary/forbidden-field test 为 0 |
| STU-INT-06 | ordinary Stage 1 Studio proposal 不得摄入 raw/restricted bytes 或 unrestricted free text | nested/encoded canary 在 ordinary API、Candidate/model input、general logs/cache/search/export 命中 = 0；restricted review boundary 单独审计 |

### 8.2 Candidate, trace and decisions

| ID | Requirement | Stage 1 acceptance |
|---|---|---|
| STU-BLD-00 | 只有 Reference Truth Owner 的 exact selection proposal + `SELECT_REFERENCE` ALLOW + final ReferenceManifest 可启动 selected Candidate build；该 action 是 R-01/E-02 `core@1.1` candidate，当前 `core@1` 必须拒绝 | Studio-owner/Fixture Author/Reviewer/caller-supplied-role selector DENY；proposal/decision/ref mutation与 cross-candidate ClearedInput/Control/Suite/oracle substitution 在 build 前失败 |
| STU-BLD-01 | 每个发布所依赖的语义字段必须绑定 ClearedInput 或 Decision | selected ADT answer-dependency trace completeness = 100% |
| STU-BLD-02 | Candidate 必须与 confirmed object、GSR 分离 | proposed/needs-decision object 无法进入 publish subject |
| STU-BLD-03 | Blind Operator 的实际输入清单必须可审计 | Package/oracle/fixture/expected output 引用数 = 0 |
| STU-BLD-04 | 系统必须产生具体 Gap/Conflict，而不是静默选值 | 至少一个 genuine ambiguity 由 Decision 解除 |
| STU-BLD-05 | Decision 必须记录 owner、依据、影响对象与 residual assumption | 删除/改动 Decision 使 publish subject digest 或 validation 失效 |
| STU-BLD-06 | runtime output 不得反向生成 expected value 或 confirmed semantics | target-import / post-run relabel tests 全部拒绝 |
| STU-BLD-07 | trace denominator 必须在 Candidate 前由 versioned semantic validation profile 冻结，Operator projection 必须排除 target/control content | 删除/重标 slot 改变 bound digest 并阻止 approval；target-value canary 在 Operator session/export/log/trace 命中 = 0 |

### 8.3 Approval and GSR publish

| ID | Requirement | Stage 1 acceptance |
|---|---|---|
| STU-REL-01 | Semantic Approval 必须绑定 exact immutable PublishSubject | wrong-subject/replayed approval 阻止 publish |
| STU-REL-02 | PUBLISH 必须有独立 AuthorityDecision | caller role/管理员身份不能代替 decision |
| STU-REL-03 | GSR 必须环境无关、immutable、exact-subject-digest-addressed | 不含 binding bundle、DataIdentity、runtime build 或 channel；storage/file checksum 不能替代 contract subject digest |
| STU-REL-04 | 同 identity/version 的不同 digest 必须冲突 | 不允许 last-write-wins；旧 GSR 保留 |
| STU-REL-05 | GSR 与获准下游 projection 必须排除 draft、comments、原附件和 unrestricted physical schema；Studio 不负责 environment RuntimePackageView | runtime reachability 中治理附件/评论/target content = 0；GSR 仍只含 environment-independent semantics/requirements |

### 8.4 SCR triage

| ID | Requirement | Stage 1 acceptance |
|---|---|---|
| STU-CHG-01 | Stage 1 只接受完整 contract-valid 的 UNKNOWN_CONCEPT final SCR；其他类型或 incomplete chain fail closed | unsupported/invalid type、payload/ref/authority mutation 均产生 zero inbox/work-item side effect |
| STU-CHG-02 | Studio 必须在 side effect 前验证 exact disclosure/enqueue chain，重新授权 refs 和 SCR_TRIAGE，并显示 limitations | expired/wrong-scope/wrong-audience/uncommitted execution 无 existence leak、无 partial item |
| STU-CHG-03 | safe context 必须足够分诊；不足时上游不创建 SCR | 5/5 non-constant fixtures 可在两分钟内正确 owner + disposition；DISCLOSURE_BLOCKED 只表示 feedback not-created，不是 analytic outcome |
| STU-CHG-04 | ACCEPTED 不能自动成为 Candidate、Claim、truth 或 publish | auto-transition tests 全部失败 |
| STU-CHG-05 | 同 scope + payload 的重试必须幂等 | same key/same digest 返回原 request；different digest conflict |
| STU-CHG-06 | triage 状态必须由 append-only disposition facts 派生 | triage 前后 final SCR bytes/digest 不变；每次 disposition 有 actor/time/authority/audit ref |

### 8.5 Product state, access and audit

| ID | Requirement | Stage 1 acceptance |
|---|---|---|
| STU-OPS-01 | 浏览器/进程刷新后关键治理状态不丢 | Candidate、Decision、PublishSubject/GSR、SCR 可恢复 |
| STU-OPS-02 | 每个 inherited Stage 1 privileged action 必须映射 product outcome owner、authority、committed fact 和 failure owner | S0 action/outcome matrix 分母完整；audit completeness = 100% |
| STU-OPS-03 | Governance Projection 必须按 role/purpose allowlist | cross-role forbidden fields = 0 |
| STU-OPS-04 | UI 不得把 build progress、badge 或 latest 当 authority | authority 始终解析 exact ref/digest |
| STU-OPS-05 | 所有 Stage 1 页面/报告必须邻接显示 synthetic、simulated role、non-HKEX/non-production limitation | main view、replay、export、runbook 无需展开即可见；claim-label coverage = 100% |

## 9. User Stories

1. As a Deloitte Transcriber, I want to submit a short safe transcription and explicitly mark what is withheld, so that I am not asked to recreate the original HKEX document.
2. As a Disclosure & Policy Approver, I want to approve the exact input proposal and allowed use, so that unapproved material cannot enter ontology work.
3. As an Ontology Operator, I want a stable locator for every usable statement, so that every candidate field has traceable provenance.
4. As an Ontology Operator, I want missing and conflicting definitions surfaced as concrete questions, so that I do not silently invent business meaning.
5. As a Domain Approver, I want business meaning separated from physical implementation, so that current SQL does not automatically override the approved definition.
6. As a Domain Approver, I want to see which released fields a Decision affects, so that I understand the consequence of approval or rejection.
7. As a Domain Approver, I want unresolved release-impacting issues to block approval, so that “mostly complete” is not published as trusted semantics.
8. As a Studio Domain Owner, I want blind-build evidence, so that a prebuilt Package cannot masquerade as successful intake automation.
9. As a Release Manager, I want Semantic Approval and publish authorization to be separate checks, so that a valid definition is not published by an unauthorized actor.
10. As a Release Manager, I want immutable releases and explicit supersession, so that active consumers remain reproducible.
11. As a Data Approver, I want GSR to carry binding requirements without production credentials or bindings, so that environment validation remains independently governed.
12. As a Runtime Capability Owner, I want required capabilities named in GSR, so that unsupported releases fail before activation.
13. As an Auditor, I want to trace a released semantic field to ClearedInput and Decisions, so that approval is evidence-backed.
14. As a Studio Triager, I want a safe UNKNOWN_CONCEPT description that is still actionable, so that I can route it without seeing the raw user question.
15. As a Studio Triager, I want insufficient safe context rejected, so that the backlog does not fill with opaque, unusable tickets.
16. As a Domain Approver, I want ACCEPTED feedback to remain proposed work, so that runtime feedback never becomes truth automatically.
17. As a Product & Delivery DRI, I want intake effort, waiting time, clarification loops and failure outcomes measured separately, so that Time to First Trusted Scenario is honest.
18. As a Reference Truth Owner, I want only my exact preregistered selection to establish the ReferenceManifest, so that delivery pressure cannot choose the easiest truth.
19. As an Ontology Operator, I want the same approved intake lineage projected without control targets, so that blind rebuild is real without asking Deloitte to transcribe twice.
20. As a future second-scenario discovery lead, I want the Strategy 2-semantic + 1-binding/execution evidence gate applied before any shared-core promotion.

## 10. Success Metrics

### 10.1 Product-family contribution

- `Time to First Trusted Scenario`：完全引用 Product Strategy，从第一份 ClearedInput 正式登记，到预登记 must-answer suite 全部达到可信门禁；按 Companion closed schema 分报 wall-clock、`internal_active_minutes`、`deloitte_active_minutes` 与 `client_confirmation_wait_minutes`，并从 exact minutes统一派生 person-hours/hours。
- `Trusted Scenario Completion Rate`：完全引用 Product Strategy，以所有进入 intake 的场景为固定分母。`completion_state` 仅为 `TRUSTED_COMPLETED/NOT_COMPLETED`；未完成场景的 `strategy_reporting_category` 必须且只能为 `SCOPE_CHANGE/PAUSED/FAILED/UNSUPPORTED/CLARIFY/REFUSE` 之一；`MISSING/WITHHELD/UNCONFIRMED` 仅是正交的 `intake_condition_flags`，不能从分母删除或静默映射。

First Committed Answer、First Safe SCR 和 First Revoke Proof 只可作为 subordinate milestones，不结束 North-star。Studio、Agent 与 Product-family calculator 必须对 Companion 定义的 `product-family-metric-events-v0.1` fixture 得出相同 start、stop、wall-clock、三项 effort/wait totals、completion state、denominator、六类 counts 与 intake flags；未知类别/unit或missing/null/negative duration fail closed。

### 10.2 Studio leading indicators

| Metric | Stage 1 target |
|---|---:|
| Preregistered semantic-slot trace completeness | 100%，并显示 numerator/denominator/case IDs |
| Release-impacting unresolved gaps at Semantic Approval | 0 |
| Missing/Withheld silently filled | 0 |
| Privileged transition audit completeness | 100% |
| Wrong-subject / stale approval mutation kill rate | 100% |
| UNKNOWN_CONCEPT actionable routing | 5/5 |
| Forbidden disclosure fields/canaries | 0 |
| Cross-artifact reference identity divergence | 0 |
| Blind Operator target/control canary | 0 |
| Invalid SCR-chain visible side effects | 0 |

对象数量、自动提取率和图中 triple 数不作为 Stage 1 成功指标。

## 11. Stage 1 Scope and Acceptance

### 11.1 Must ship for the ADT tracer

- V0 truth/intake/blind rebuild 的完整产品路径；
- ClearedInput proposal/approval 与 Missing/Withheld failure；
- persisted Candidate、Trace、Gap/Conflict、Decision；
- immutable GSR PublishSubject、Semantic Approval 与 authorized GSR publish；
- GSR governance/runtime projection boundary；
- UNKNOWN_CONCEPT safe inbox 与 human triage；
- refresh/recovery、audit record 与 synthetic limitation labels；
- 与唯一 `reference_case_id + ReferenceManifest` 对齐。
- `05_stage1_demo_delivery_companion.md` 定义的 lightweight persisted tasks、proxy protocol、RACI 与 readiness evidence。

### 11.2 Stage 1 exit

1. 两个 ADT truth candidate 分别登记；每个 selectable candidate 有独立 ClearedInput、ControlManifest/oracle provenance；只有 R-01/E-02 获批后 Reference Truth Owner 的 exact proposal + `SELECT_REFERENCE` ALLOW 才可冻结唯一 ReferenceManifest；否则 V0 conformance blocked。
2. 选择唯一 reference 后，blind Operator 只读 target-free projection，按 preregistered semantic-slot denominator 形成 Candidate/Trace/Decision；Trace 100%，target/control canary 0。
3. 至少一个 Missing/Withheld path fail closed，至少一个 genuine ambiguity 有 Decision；2 名 non-author proxy 完成 common-template baseline，真实 Deloitte usability 仍为 Not Assessed。
4. V0 形成 PublishSubject + exact Semantic Approval；V1 取得 PUBLISH AuthorityDecision 后形成 immutable GSR。
5. 下游四个 environment gates 能从 GSR requirements 构造 exact subjects；Studio 不拥有其 PASS outcome。
6. 五个 UNKNOWN_CONCEPT fixtures 5/5 actionable、零 forbidden-field leakage；invalid/incomplete chain zero inbox side effect；ACCEPTED 不修改 SCR 或升级真相。
7. 现有 33 tests、33 validation checks 与 fixed contract vectors 全部保持 green。
8. V0/V3 都只是 internal evidence；只有 V0 + V1–V5、governed resolver/console cutover、critical tests、0 leak、0 premature analytic bytes、visible limitations、exact Delivery Readiness manifest 与 Product & Delivery DRI GO 才允许 external governed-evidence demo。

### 11.3 Delivery ownership

唯一 slice RACI 位于 `05_stage1_demo_delivery_companion.md`。Studio Domain Owner 对 V0 accountable；Agent Domain Owner 对 V1–V3 accountable；Studio Domain Owner 对 V4 end-to-end triage accountable；Product & Delivery DRI 对 V5/external GO accountable。Slice accountability 不转移 Reference Truth、gate 或 command authority。

Studio 的 slice contributions：V0 truth/intake/blind Candidate/Trace/Decision + Semantic PASS；V1 exact GSR sub-outcome；V4 Change Inbox/triage；V5 clean-state product confirmation。

上述工作包含于 Synthetic Profile 的 full Stage 1 `16–24 person-days`，不是额外估算。S0 后由 Product & Delivery DRI 重估。

## 12. Testing Decisions

- 测试外部行为和不可绕过的产品边界，不测试 UI 内部组件结构。
- Contract tests：ClearedInput/GSR/SCR exact refs、wrong selector/subject/scope、cross-candidate substitution、unknown profile、identity conflict；完整 SCR chain 细节继承 Annex conformance。
- Workflow tests：pre-approval ordinary-ingress canary、target-free Operator projection、Gap/Decision blocking、semantic approval/publish separation、derived triage lifecycle、refresh recovery。
- Mutation tests：删除/篡改 input、semantic-slot denominator、Decision、approval、PublishSubject、GSR 或 SCR-chain constituent 必须在 visible/downstream side effect 前失败。
- Projection tests：Governance/Runtime/User 三种视图的 forbidden keys、values 和 secret canary 为 0。
- Reader/task tests：2 名 non-author proxy 用 blank template 安全完成并记录 baseline；Reviewer 能解决 ambiguity；Triager 在两分钟内正确处理 5/5 non-constant fixtures。
- Regression：保留现有 33 automated tests、33 validation checks 与当前 `core@1` 的 34 positive + 30 negative contract vectors；R-01 若获批，必须生成并独立验证新的 Profile/vector counts，不能冒用旧计数。

## 13. Dependencies and Product Interfaces

- Shared Contracts & Kernel：提供 identity、AuthorityDecision、projection、GSR commit、safe outbox 和 conformance；它不是第三个用户产品。
- Ontology Analytic Agent：只消费 activated VRS；通过 typed SCR 提交反馈；不得读取 Studio draft。
- Reference Truth Owner / Control Reviewer：Truth Owner 独自选择并冻结 reference，Control Reviewer独立复核；Studio 只消费 ReferenceManifest，不从 runtime 反推 truth。
- Runtime Release Operations：属于 Agent Product Domain；Studio 只交付 exact GSR，不拥有 environment binding、four-gate verdict、seal 或 Activation。
- Stage 1 Demo & Delivery Companion：冻结共同 demo promise、minimum surface、slice RACI 和 delivery checklist；不是第三产品或 runtime authority。
- Deloitte HK：Stage 1 不依赖真实响应；Stage 2 才验证安全转写的真实可用性和周转时间。
- Target Platform：IAM、ARM64/K8s、企业 registry/audit 后置，不阻塞 Stage 1 产品路径。

## 14. Risks and Controls

| Risk | Product control | Reopen condition |
|---|---|---|
| Studio 变成复杂技术编辑器 | 五个 MVP tasks；外部人员不写 internal schema | 第二场景证明需要稳定的新 authoring job |
| 自动提取被误当正确 | Candidate/Trace/Decision；无来源不能 confirm | 独立 extraction evaluation 达到获批门槛 |
| 预制 Package 冒充 intake | blind Operator 与输入清单 | 经 Decision Owner 批准的另一验证方法 |
| 获批 source pack 暗含 target/control | audience-specific Operator Intake Projection + target canary | 无法安全分割时降级 blind claim |
| 待审 material 先进入 ordinary Studio/model/log | restricted review boundary + closed metadata/ref-only ordinary proposal | 新 in-zone intake Profile 获批 |
| SQL 覆盖业务定义 | business meaning / executable requirement / binding 分层 | 明确 Domain Decision |
| Studio 获得事实数据通配权 | 只持有治理 projection；Data gate 独立 | target security design 另批 |
| SCR 自动污染 truth | triage-only，ACCEPTED 不是 Candidate | 新 SCR Profile + 独立审批 |
| 一套 ADT 过度平台化 | second-scenario core-change ledger | 两个有实质差异场景形成稳定共性 |

## 15. Open Decisions — Not Blocking Stage 1

- Studio 长期 operating owner、buyer 与商业包装；
- 独立 UI 还是与 Agent 共用 shell/navigation；
- Deloitte 是否未来获得直接 portal 账号；
- production workflow、电子签名、retention 和 segregation of duties；
- RDF/SHACL 是否成为目标客户区的治理交换格式；
- 第二场景需要哪些稳定的批量编辑、impact analysis 或 catalog federation 能力。
- accepted SCR → human Decision → new GSR/VRS → changed answer 的完整 co-work loop；
- Strategy 2 semantic + 1 binding/execution 差异证据满足后，才定义 detailed core-change ledger。

这些问题不能在只有 ADT synthetic evidence 时被提前冻结。

## 16. Approval Gate

本 Revised Candidate 只有在以下条件满足后才能成为 Reviewed Candidate：

- [ ] 与 Agent PRD 对 GSR、VRS、projection、gates、lifecycle、outcomes 和 SCR 的解释完全一致；
- [x] architecture、correctness/security、delivery 完成两轮 critic review并由主审裁决；
- [ ] 主审接受的 P0/P1 修订通过独立 closure retest；
- [ ] R-01 获批：E-01 有 contract-valid `CONCEPT_NOT_BOUND` decision，E-02 有 contract-valid reference-selection decision；随后 consolidated Profile/Annex/vectors 独立通过；
- [ ] `stage1-demo-delivery-companion/0.1` 的 exact digest `sha-256:800d15d41fb2ad9143eac14d0f13a9297f18afe6bf704e1bce4e8b466e4a8b74` 与本 PRD、Agent PRD 一起进入 `reviews/product-prds-approval-candidate-manifest.md`；其 product surface、RACI、metric dictionary、demo promise 与 readiness evidence 无 competing authority；
- [ ] fresh Studio product reader 能准确复述五个 MVP tasks、正式 output 和禁止项；

以上 closure checklist 全部通过后，Product & Delivery DRI 只可记录状态为 Reviewed Candidate；该记录不是审批或 implementation authority。唯一产生 Approved/Frozen authority 的动作，是 Decision Owner 对 final approval manifest 绑定的 exact Studio PRD、Agent PRD 与 Companion identities/digests 作一次原子批准；任一文档 digest 改变会使旧批准不适用于新 revision。批准前不得把本 PRD 描述为已冻结产品需求，也不得据此声称现有 Console 已是 conformant Studio。
