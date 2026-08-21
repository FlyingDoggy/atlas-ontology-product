# Shared Product Contract v0.1

状态：Approved/Frozen  
日期：2026-08-18  
批准记录：Muyu 于 2026-08-19 指示继续进入下一阶段，批准 v0.1 Reviewed Candidate 转为 Approved/Frozen  
父级基线：`01_product_group_strategy.md` v1.0 Approved Baseline  
Decision Owner：Muyu  
主要消费者：Ontology Studio、Ontology Analytic Agent、Shared Contracts & Kernel

## 0. 如何阅读这套合同

本文件只冻结两个产品之间长期稳定的产品级合同：对象、authority、状态、信息流与失败结果。它不要求产品经理理解 digest byte、文件锁或 JSON Schema。

配套文件的优先级为：

1. 本文件：Core Product Contract，最高优先级；
2. `shared-contract/01_synthetic_trusted_flow_core.md`：Stage 1 ADT PoC 支持范围；
3. `shared-contract/02_technical_conformance_annex.md` 与 checked-in fixtures：工程实现和测试依据。

下层文件不得放宽上层不变量。实现技术可以替换，但对用户和另一个 Product Domain 呈现的结果不能因此改变。

Strategy 中的 `RuntimeSnapshotCandidate` 是 build/verification 阶段的概念简称；本合同进一步明确：它不是两个 Product Domain 之间的公开权威对象。Strategy 中的 “Ready VRS” 是某一时刻的 eligibility 结果；它不是 VRS 内永久有效的字段。

## 1. Executive Contract

```text
ClearedInput
      ↓
Ontology Studio
  Candidate → Decision → Semantic Approval
      ↓ publishes
GovernedSemanticRelease (GSR：环境无关、不可变)
      ↓ exact reference
Shared Contracts & Kernel
  Runtime payload → four environment verifications → SEALED VRS
      ↓ scoped Activation + point-in-time Eligibility
Ontology Analytic Agent
  Answer / Clarify / Refuse / Failed Precondition / Failed Execution + durable Evidence
      ↓ optional disclosure-cleared, typed feedback
SemanticChangeRequest → Ontology Studio triage
```

永久不变量：

1. Studio 的唯一正式下游语义发布物是环境无关、不可变的 GSR。
2. Agent 不读取 Studio draft、review comment、原始治理附件或裸 GSR；它只解析已密封、已激活且当次 eligibility 为 ALLOW 的 VRS 授权视图。
3. GSR、VRS、Activation、Revocation、Execution 和 SCR 各有独立 identity、owner 与 lifecycle。
4. 五类 gate 不可互相代替；一个全局 `PASS`、一个模型判断或一个管理员角色不能代替它们。
5. VRS 只证明 payload 与精确五份 PASS verification 已被密封；可否执行是随 authority、policy、activation、expiry 和 revocation 变化的动态结论。
6. Activation 与 Revocation 是 append-only authority records；被 revoke 的 exact digest 永不复活，rollback 只能指向另一份仍合格的 VRS。
7. Governance、Runtime Service 与 User Evidence 使用确定性 allowlist projection；projection 可以隐藏、脱敏或按批准规则格式化，但不能暗中改写业务含义。
8. 答案在证据、最终 eligibility 与 release commit 耐久化前不得释放；LLM 不能绕过该边界。
9. SCR 是最小披露、强类型、不可信的 proposed input；它不能自动成为 Ontology Candidate、Claim 或业务真相。
10. HKEX 原始材料默认不离开其安全区；离线 PoC 只接受被批准的 ClearedInput，不由模型补齐 Missing、Withheld 或 Unconfirmed 内容。

## 2. Contract Scope

### 2.1 本合同冻结

- 两个 Product Domain 的正式输入、输出、命令和失败结果；
- 公共对象的不可变含义、authority 与引用关系；
- GSR publish、VRS seal、Activation、Eligibility、Execution、Revocation 与 SCR 的顺序；
- 五类 gate 及其 accountable authority；
- privileged action 必须经过 AuthorityDecision；
- digest identity、version、scope 和 compatibility 的产品语义；
- 三种 projection 和禁止的信息流；
- CAS activation、不可逆 revocation、result-release barrier；
- evidence 和 safe change feedback 的最低承诺；
- Stage profile 能缩小支持范围但不能伪装支持的原则。

### 2.2 本合同不冻结

- REST、GraphQL、event bus 或文件交换的具体 endpoint；
- Pydantic、JSON Schema、RDF、数据库表或目录布局；
- Registry、IAM、KMS、PKI、DLP、WORM audit 或 policy engine 产品；
- K8s、ARM64 image、Service Account、Network Policy 与 secret mechanism；
- HA、SLA、retention、legal hold、灾备和多区域部署；
- 最终 UI 数量、SKU、品牌、采购方式或代码仓库数量；
- 通用 ontology compiler、完整 Knowledge Center、Catalog/MDM 联邦。

### 2.3 Normative language

- `MUST / 必须`：conformance 必需；违反即不符合本合同。
- `MUST NOT / 禁止`：任何 Profile 均不得违反。
- `SHOULD / 应`：除非有获批 Decision 记录，否则必须遵守。
- `MAY / 可以`：实现可选。

## 3. Product and Authority Boundary

### 3.1 Ontology Studio owns

- ClearedInput intake、Candidate、Trace、Gap、Conflict 与 Decision workflow；
- 业务语义、定义、公式、粒度、时间、population、unit、exception 与 binding/policy/capability requirements；
- Semantic Approval outcome 与 GSR publish；
- SCR 的安全 triage 与后续 Candidate proposal。

Studio 不拥有目标环境的 data identity、runtime build、最终 activation head 或单次 Agent 用户权限。它不能因发布 GSR 而获得事实数据通配访问。

### 3.2 Ontology Analytic Agent owns

- 可信 request context 下的 intent binding、approved planning 与 deterministic execution；
- Answer、Clarify、Refuse、Failed outcome；
- typed Facts、Claims、User Evidence Projection 与 Execution Evidence；
- 在披露允许时提交 typed SCR。

Agent 不能修改 Ontology、签 gate、seal、activate、revoke 或把 telemetry 当作业务真相。

### 3.3 Shared Contracts & Kernel owns

- contract schema/profile、identity 与 compatibility validation；
- runtime payload assembly、verification records 与 VRS seal；
- AuthorityDecision、PolicyDecision、Activation/Revocation resolution、Eligibility 与 release commit；
- projection enforcement、evidence integrity 与 safe outbox boundary。

它是两个产品的合同/代码底座，不是第三个面向用户的 Product Domain。

## 4. Public Cross-Product Objects

| Object | Producer / authority | Consumer | 不可变含义 |
|---|---|---|---|
| `ClearedInput` | Transcriber；Disclosure & Policy Approver 放行 | Studio | 某份输入在声明的 classification、scope 和 allowed use 下可进入 ontology workflow |
| `GovernedSemanticRelease` | Studio / Release authority；Semantic Approval 已存在 | Shared Kernel | 某一环境无关语义及其 lineage/requirements 已获批并发布 |
| `VerifiedRuntimeSnapshot` | Snapshot sealer | Agent resolver | 某个确切 runtime payload 与精确五份 PASS verification refs 已被密封；仅证明 `SEALED` |
| `ActivationRecord` | Release & Activation Manager | Resolver | exact scope/channel 中一次 append-only ACTIVATE/DEACTIVATE 决定 |
| `RevocationRecord` | Authorized revoke authority | Resolver / release boundary | 对 exact target 的不可逆安全处置 |
| `ExecutionEvidenceEnvelope` | Deterministic Agent runtime | User / authorized auditor | 某次 outcome 使用的 snapshot、data、policy、plan、claims、projection 与 release decision |
| `SemanticChangeRequest` | Controlled Agent-to-Studio channel | Studio triage | 经披露批准、typed、不可自动发布的 proposed feedback |

任何 `latest`、mutable status row、UI badge、文件路径或模型回答都不是上述对象的替代 authority。

## 5. Supporting Control Objects

这些对象是 Shared Kernel 的可审计合同对象，但不是普通 Agent 用户输入，也不要求两个 Product-Domain PRD 展开其存储细节：

| Object | 作用 |
|---|---|
| `RuntimeSnapshotPayloadManifest` | immutable 地引用 GSR、runtime semantic projection、binding、policy、runtime capability、data、control、suite、truth provenance 与 evaluator profile；不含 verification status |
| `VerificationAttempt` | 某一 gate 对 exact subject 的一次 PASS/FAIL 尝试；每次尝试新建，不原地改状态 |
| `AuthorityDecision` | 对 exact principal/context、action、scope、purpose、resource digest、policy 与 obligations 的 point-in-time ALLOW/DENY |
| `PolicyDecision` | Shared Kernel 内部、不可变的 policy-evaluation evidence；绑定 trusted context、purpose、exact resources、policy/input identity 与 ALLOW/DENY，由 Eligibility、Disclosure 或 Result Release checks 消费；它不授予 authority，也不能替代 AuthorityDecision、EligibilityDecision 或任一 gate |
| `ExecutionEligibilityDecision` | 在 ACTIVATE、PRE_QUERY、RESULT_RELEASE 等 phase 对 exact VRS/activation/policy/revocation 状态作 point-in-time ALLOW/DENY |
| `ResultReleaseCommit` | 将 exact execution evidence、sanitized projection、final eligibility、activation head 和 revocation epoch 耐久绑定；成功后才可释放 bytes |
| `RuntimePackageView` | Agent runtime 可读取的最小、只读 executable façade；治理附件与用户禁止字段不可达 |

Studio 可以显示由这些记录派生的 build/progress view，但该 view 不是 identity-bearing authority；Agent 不依赖它。

## 6. Identity, Scope and Version

### 6.1 DigestSubject and Envelope

每个 immutable object 必须区分：

- `DigestSubject`：真正被稳定寻址的 closed semantic fields、scope、schema/profile 与 dependency refs；
- `Envelope`：subject、subject digest、provenance、commit/authorization refs 与操作元数据；
- 如 Envelope 本身需要寻址，则使用不含自身 digest 的独立 EnvelopeDigestSubject。

自己的 digest、signature、后续 attestation、动态 eligibility、UI status 或提交后才产生的时间不得进入自己的 digest 前像。具体字段和 canonical bytes 由 Technical Annex 冻结。

### 6.2 Full references

执行或 privileged action 使用的 ref 必须至少绑定：object type、object ID 与 version/sequence、applicable tenant/workspace/environment scope、contract/schema/canonicalization profile、exact digest。

只传 ID、SemVer、opaque handle 或 `latest` 不足以证明 integrity 或 authorization。相同 scope/type/ID/version 出现不同 digest 是 integrity conflict，不能 last-write-wins。

### 6.3 Scope and channel

- Governance objects 至少绑定 tenant + workspace；
- runtime payload/VRS 绑定 tenant + workspace + environment；
- channel 属于 Activation 和 Eligibility，不属于可被多个 channel 独立激活的 VRS payload；
- lookup 先按 trusted scope 定位，再按 principal/purpose 授权；opaque ID 不是 authorization；
- cross-scope deny 不得泄露对象是否存在。

### 6.4 Compatibility and migration

- Stage profile 必须声明允许的 exact contract version、object schema、canonicalization 与 compatibility tuple；
- 未知或未迁移的 profile/version fail closed；不存在隐式 `latest contract`；
- 新版对象由 migration adapter 读取旧对象后产生新对象、新 digest 与 lineage，不原地升级；
- SemVer/name 不能代替 behavior、input/output、failure、policy obligation 与 suite compatibility；
- binding/runtime-only 变化不应伪装为 semantic version 变化。

## 7. Five Independent Gates

| Gate | Phase | 必须绑定的产品级闭包 | Accountable authority | Blocks |
|---|---|---|---|---|
| Semantic Approval | pre-publish | 完整 GSR publish subject：语义、lineage/decisions、binding/capability/policy/disclosure requirements 与 supersedes | Domain Approver | GSR publish |
| Binding & Data Validation | pre-seal verification | binding requirements、executable semantic projection、binding bundle、exact DataIdentity、validation profile 与 environment | Data Approver | VRS seal |
| Disclosure & Policy Clearance | pre-seal verification | disclosure/policy requirements、classification、runtime/user projection schema/transformer、policy、audience/purpose/environment | Disclosure & Policy Approver | VRS seal |
| Runtime Capability Compatibility | pre-seal verification | capability requirements、executable projection、provider/operator build、input/output/failure/options/policy obligations、compatibility/fidelity profile | Runtime Capability Owner | VRS seal |
| Control / Golden Evaluation | pre-seal verification | full runtime payload、reference/control/suite、oracle provenance、evaluator build/config 与 evaluation profile | Independent Control Reviewer | VRS seal |

Rules：

1. Semantic gate 允许发布 GSR；其余四 gate 只在未激活 verification mode 运行。Verification mode 使用专用获准 principal/data/path，不接普通业务流量。
2. Gate outcome 必须是独立、typed、exact-subject 的 VerificationAttempt；`WARN` 或另一 gate 的 PASS 不能替代。
3. Issuer 必须持有绑定 exact proposed action/subject 的 AuthorityDecision；caller-supplied role 无效。
4. Projection fidelity 是 deterministic conformance evidence，由 Disclosure 与 Runtime gate 消费，不新增第六个人工 gate。
5. Reuse 只允许 exact subject digest、scope、profile、limitations 和仍有效 authority context 完全一致；object name/version 相似不构成 reuse。
6. Payload 不含 verification refs；VRS seal subject 才绑定 payload 与精确五份 PASS refs，避免 circular digest。
7. 多份可用 PASS attempt 并存时，sealer 必须由调用者明确给出五份 exact refs，不可自动选 `latest`。

## 8. Lifecycle and Ordering

### 8.1 Publish and seal

```text
ClearedInput → Candidate + Trace + recorded Decisions
→ GSR Publish Subject
→ SemanticApproval PASS + PUBLISH AuthorityDecision
→ immutable GSR
→ immutable RuntimeSnapshotPayloadManifest
→ four environment VerificationAttempts
→ SEAL AuthorityDecision
→ immutable VRS(seal_status=SEALED)
```

Build/verification progress 由 append-only attempts 派生。失败不会修改 payload；重试产生新 attempt。VRS 没有永久 `READY`、`REJECTED`、freshness 或 expiry state。

### 8.2 Activate

```text
resolve current scope/channel head H
→ build Activation intent(expected_head=H, expected_epoch)
→ ACTIVATE EligibilityDecision + AuthorityDecision
→ atomic compare-and-append
→ committed ActivationRecord or CONFLICT
```

同一 expected head 的并发命令最多一个成功。`highest sequence wins`、先改 pointer 后补 audit、或以 `latest.json` 为 authority 均不符合合同。Committed ActivationRecord 自身是 authoritative lifecycle audit fact；secondary index/cache 失败不能留下未审计的 active state。

### 8.3 Execute and release

```text
trusted request context
→ resolve Activation + SEALED VRS
→ PRE_QUERY EligibilityDecision
→ governed plan / deterministic query / typed facts / typed claims
→ allowlisted UserEvidenceProjection
→ final policy + revocation check
→ RESULT_RELEASE EligibilityDecision
→ durable Evidence + ResultReleaseCommit
→ release only the committed projection bytes
```

Activation append、Revocation append 与 ResultReleaseCommit 在同一 exact `ChannelScope` authority-order domain 中排序；ResultReleaseCommit 是某次 execution 的最终 release 线性化点：

- revoke 先提交：commit 失败，answer bytes 为 0；
- 新 Activation 先提交：仍绑定旧 activation head 的 in-flight execution 在 final reread 时 commit 失败，answer bytes 为 0；
- release commit 先提交：该 exact projection 已获准，可发送/重放；后续执行与 commit 被 revoke 阻止；
- release commit 先于新 Activation 提交：该 exact committed projection 可发送；新 Activation 只影响后续尚未 commit 的 execution；
- evidence、audit、final decision 或 durability 失败：不得释放 answer bytes；
- 合同不虚构“未来 revoke 可收回用户已收到的内容”。

Stage profile 可以禁止 streaming 并用 private buffer 实现。若未来支持 streaming，必须先定义等价的分段 release contract，不能绕过本不变量。

### 8.4 Upstream feedback

已完成 outcome 不依赖 Studio 在线；SCR 使用 durable asynchronous outbox。Outbox 故障不得撤销已经 committed 的答案，但必须可重试、可观察且不能产生重复 request。

## 9. Authority and Policy

Principal/role 字符串是证据标签，不是授权。以下 action 至少需要 point-in-time AuthorityDecision：approve/publish、attest、seal、activate/deactivate、revoke、snapshot resolve、query、result release、privileged evidence read/project、SCR disclosure/enqueue/triage。

AuthorityDecision 必须绑定 trusted session/principal context、role/trust epoch、scope、purpose、action、exact proposed resource/subject digest、policy digests、obligations、ALLOW/DENY、issued/expiry。角色和 scope 不能从 request body、CLI flag 或对象自身声明中获得。

最终 permission 使用 deny-overrides：

```text
Trusted identity/authority
AND workspace/purpose authorization
AND Ontology policy
AND Query Engine data policy
AND disclosure policy
```

任一 `DENY`、`UNKNOWN`、expired、wrong-scope 或 stale context 必须 fail closed。Stage 1 可用明确标为 simulated/local 的 deterministic registry；它不构成 production IAM、MFA 或 non-repudiation 证明。

## 10. Projection and Information Flow

| Field group | Governance Projection | Runtime Service Projection | User Evidence Projection |
|---|---:|---:|---:|
| Approved semantic IDs/definitions | authorized full | executable subset | disclosed subset |
| ClearedInput/source/Decision refs | authorized full | opaque approved refs only | safe lineage/decision identity only |
| Draft/reviewer comment/conflict detail | role-gated | never | never |
| Binding table/column/join/locator | separately authorized | minimal compiler/query subset | never |
| SQL/params/raw rows/credentials | execution-review only | Query Engine boundary only | never |
| Policy implementation/rule detail | authorized | required inputs | safe outcome/reason only |
| Facts/Claims | reviewable | typed full form | principal-specific allowlist |
| Gate/evidence | authorized full | exact required refs | safe summary/opaque handle |

Rules：

1. Projection 是 closed-schema allowlist serializer，不是 prompt redaction 或事后 denylist。
2. 每个可投影字段必须有 classification、audience 和 purpose；UNKNOWN 阻止 publish/seal/project。
3. RuntimePackageView 只包含 deterministic runtime 必需字段；ClearedInput、原文、review comment、governance rationale、unrestricted physical schema、SQL、credential、outbox content 不可达。
4. User Evidence 永不暴露 SQL、params、table、column、join、locator、raw row、internal mapping ID、prompt、path、stack 或 governance comment。
5. 已批准的 rounding、scale、label、locale 或 suppression 必须显式、确定性并进入 render evidence。不同 policy 可以 suppress/coarsen，不得假装为同一未变输出。
6. 当前 PoC ordinary evidence-audit 已被复现实测泄露物理表列和 mapping ID；在 typed allowlist 与真实 API canary tests 通过前，不得称用户证据符合合同。

## 11. Revocation and Rollback

永久 Core 规则：

1. Revocation target 是 full scoped ref；scope-local record revoke 与 content-digest-all-scopes 是不同 action 和 authority。
2. Revocation append-only、不可逆，不存在 `UNREVOKE`。
3. 多个 applicable records 采用 strictest enforcement；新记录不能削弱旧记录。
4. Transitive applicability 只沿 sealed payload/VRS 中冻结的 dependency graph 计算，不依赖 mutable alias/search。
5. Revocation append 与 scope epoch 增加是同一 atomic action。
6. PRE_QUERY 与 RESULT_RELEASE 是不同 enforcement boundary。
7. `BLOCK_ALL_ACCESS` 也不能销毁事故/audit 证据；另行授权的 incident access 必须明确。
8. Recovery 产生 corrected artifact/new digest/new activation；rollback 只激活另一份未 revoke、compatible、eligible 的 VRS。

Profile 可以只支持部分 target/enforcement，但未支持值必须明确拒绝，不能忽略或降级。任何被支持为 revocable 的 target，一经 revoke 就不得通过 alias、pin、cache、retry 或 rollback 复活。

## 12. Evidence and Outcome Contract

### 12.1 Outcome classes

| Outcome | Meaning | Query access | User result |
|---|---|---:|---|
| `CLARIFY` | 必需语义输入缺失或有歧义 | No | 明确缺少什么/需确认什么 |
| `REFUSED` | 请求已理解但被 policy 或支持范围禁止 | No，除非获批 aggregate policy check | safe reason |
| `FAILED_PRECONDITION` | contract、integrity、scope、compatibility、activation 或 eligibility 失败 | No | generic safe failure + correlation |
| `FAILED_EXECUTION` | 获准执行后发生 query/reconcile/evidence 失败 | May have started | 无 partial answer；safe failure |
| `ANSWERED` | gate、query、validation、Claims、projection 与 release commit 全部通过 | Yes | evidence-bound answer |

Clarify/Refuse 等 boundary outcome 也必须产生最小 durable ExecutionEvidenceEnvelope，并记录 Query Engine access count = 0。

### 12.2 Evidence minimum

每个已释放结果的 immutable ExecutionEvidence 必须绑定 exact GSR、VRS、Activation、phase-specific Eligibility、trusted principal/scope/purpose、Authority/Policy decision、DataIdentity、plan/query/operator build、Facts、Claims、User Evidence Projection bytes/digest、renderer/version、locale/timezone、unit/rounding profile与 replay level；为避免 digest cycle，ExecutionEvidence 不引用 ResultReleaseCommit，而是由 ResultReleaseCommit 反向绑定 exact evidence 与 projection。只有存在有效 commit 时，外部才可把 staged answer candidate 解释为 `ANSWERED`。

所有显示数字、方向、排名和限制必须由 direct typed Claims 支撑。Partial result 不能包装成完整答案。

`evidence replay` 重放已保存的 exact sanitized projection/evidence，不依赖当前 source data。历史 data re-execution 是一次新 execution，需要可寻址历史 data，并产生新 evidence；二者不得混称。

## 13. SemanticChangeRequest Contract

SCR 使用 two authorization phases、multi-object 且无 circular digest 的构造：

1. 建立 closed、typed `ProposedSCRPayload`；
2. disclosure evaluation 直接绑定 exact payload digest、safe-detail digest、source/destination scope、requester/receiving audience、purpose、classification、allowed fields、policy 与 expiry；`PayloadDisclosureDecision` 再绑定该 exact evaluation 与其 AuthorityDecision，因此传递性地固定全部 disclosure inputs；
3. 只有 disclosure ALLOW 后才建立不含 enqueue authority ref 的 `SCREnqueueProposal`；
4. `SCR_ENQUEUE` AuthorityDecision 绑定 exact EnqueueProposal digest；
5. final SCR 只引用 EnqueueProposal + AuthorityDecision，形成后进入 outbox；
6. payload 或 proposal 任何变化都会使原 decision 失效。

永久规则：

- 禁止 raw question、raw answer/value、SQL、table/column、attachment、prompt、stack、path、credential 或 unrestricted free text；
- 禁止可字典猜测的裸 question SHA-256；interaction handle 必须 opaque、随机或 purpose-bound keyed、scope-bound；
- boundary execution ref、observed GSR/VRS refs 必须是 full scoped refs；
- safe detail 是单独分类、allowlisted、可授权读取的 artifact；
- 无足够可披露上下文时返回 `DISCLOSURE_BLOCKED`，不创建无法处理的 backlog；
- idempotency key 只在相同 scope + proposed payload digest 下返回原 request；同 key/different payload 是 conflict；
- Studio 必须重新授权 refs，SCR 只能 triage；`ACCEPTED` 表示值得治理工作，不表示内容为真。

ProductFeedback、OperationalIncident/Telemetry 与 Revocation/Capability control 使用不同 schema/owner，不能借 SCR 自动进入 Ontology lifecycle。

## 14. Control Integrity and Claim Ceiling

每份 ControlManifest/Control attempt 必须声明 oracle class、source/provenance、source cutoff、expected-value author、fixture/application author、independent reviewer、truth 是否早于 fixture/runtime 冻结、derivation/recomputation evidence、allowed claims 与 limitations。

最低规则：Truth Owner 与 Independent Control Reviewer 必须是不同自然人；Fixture Author 不能是 Reviewer；runtime output 不能反向生成 expected value；fixture generator/runtime 不得 import frozen expected targets；suite denominator、expected status/value、tolerance 或 case 内容变化产生新 digest；不得 post-run 删除/重标失败；top-line totals、comparisons/decompositions、Answered/Clarify/Refuse 与 mutation behavior 都必须被 control 明确断言。

两人配置中 Truth Owner 可兼任 Fixture Author，但只能声称“independently reviewed constructed-synthetic workflow/runtime conformance”。称 independent oracle 至少需要三人分离，或 independently frozen authoritative source + independent verifier。没有 HKEX-authorized source/owner 时，任何配置均不能声称 HKEX business validation。

## 15. Failure and Fail-Closed Rules

至少以下情况在 Query Engine 前拒绝：draft/raw GSR、wrong scope/environment、unknown profile、digest mismatch、missing/failed/wrong-subject gate、expired/revoked authority/attempt、incompatible capability、inactive VRS、revoked target、stale/corrupt authority ledger、policy deny/unknown、missing DataIdentity。

至少以下情况在 result release 前拒绝：revocation/policy/authority 状态变化、evidence/claim/projection 不完整、partial query、projection classification unknown、release commit/durability failure。

错误对普通用户只返回 safe outcome、reason family 与 correlation ID；SQL、locator、stack、path、policy internals 和 object existence detail 不得越权披露。

## 16. Current PoC Migration Boundary

必须保留：strict typed models 和 extra-field fail closed；current OntologyPackage 作为 migration/build source；immutable version artifacts 与 integrity inventory；VerifiedSnapshot 的 indivisible-handle 思路和 request-time re-verification；AQC、Plan、DuckDB deterministic calculation；typed Fact/Claim/Evidence；33 automated tests、33 validation checks 与唯一 8-case suite 的 regression value。

必须替换或包裹：

- compound OntologyPackage/manifest → GSR + payload + exact component refs；
- runtime 直接读 full OntologyPackage → RuntimePackageView façade；
- single validation PASS → five exact VerificationAttempts；
- stateful candidate/READY → immutable payload/SEALED VRS + dynamic Eligibility；
- `latest.json` authority → append-only CAS Activation ledger；
- no revoke → supported-profile Revocation + two enforcement checks；
- render then persist → Evidence + ResultReleaseCommit barrier；
- hand-coded evidence denylist → typed allowlist projection；
- arbitrary/no feedback → safe typed SCR + disclosure-bound outbox。

现有 `ontology.exchange_analytics.adt@1.2.0` 继续作为 regression fixture，不得在缺少 migration artifacts 和 contract tests 时重标为 conformant GSR/VRS。Calculator、SQL compiler 或 formula evaluator 不因合同迁移而重写。

## 17. Profiles, Product PRDs and Entry Gate

Stage 1 的 fixed scope、local authority、VRS-only revoke、UNKNOWN_CONCEPT、oracle limitation、8-case suite、vertical slices、ROM 与 out-of-scope 由 Synthetic Profile 冻结。

| PRD | 必读本合同内容 | Profile 内容 | 不要求理解 |
|---|---|---|---|
| Studio | ClearedInput、GSR、Semantic gate、gate outcomes、SCR trust/triage | ADT intake、one SCR、simulated role/claim limit | canonical bytes、query internals、ledger file format |
| Agent | VRS、Activation/Eligibility/Revocation、Projection、Evidence、outcomes | ADT runtime path、VRS revoke、8 cases | Studio build view、candidate internals、source governance comments |
| Shared Kernel design | 全部 Core | 全部 Profile | 无；同时必须读 Technical Annex |

只有本合同被 Decision Owner 置为 `Approved/Frozen` 后，Studio 与 Agent Product-Domain PRD 才正式启动。此前可以准备 research、reader path 与问题清单，但不能把尚未冻结的合同假设写成已批准需求。

## 18. Deferred and Rejected Alternatives

### 18.1 Deferred implementation, not relaxed behavior

Production IAM/PKI/KMS、enterprise policy engine、WORM audit；multiwriter/distributed registry、HA、cross-region；component/GSR/attestation transitive revoke implementation、三种 enforcement、cache freshness；streaming release protocol；UNKNOWN_CONCEPT 之外的 SCR variants；historical source re-execution；second business scenario、通用 compiler、Knowledge Center；target ARM64/K8s 与真实 Query Engine integration。

遇到 deferred value/type/profile 时必须 fail closed，不能静默假装支持。

### 18.2 Rejected

| Alternative | Decision reason |
|---|---|
| One compound Package/Snapshot truth | 混合 semantic、environment、data、policy 和 runtime authority |
| Agent reads Studio draft or bare GSR | 绕过 publish/seal/projection boundary |
| Public mutable RSC/build status as authority | 流程状态污染 immutable identity |
| Persistent VRS READY | eligibility 随时间/authority/revoke 变化 |
| SemVer/latest proves compatibility | 标签不能证明 behavior/failure/policy compatibility |
| Caller asserts role | evidence label 不是 authorization |
| Mutable activation pointer / highest-sequence-only | 允许 fork 或未审计切换 |
| Un-revoke old digest | 破坏 monotonic safety 和 incident evidence |
| Render before durable evidence | 可释放无证据或已禁止结果 |
| Raw/bare-hash/free-text SCR | 泄露、不可安全 triage、易 prompt/semantic injection |
| LLM signs gate or computes authoritative truth | 概率输出不能取代 authority/deterministic control |
| Prompt-only redaction | 不可证明字段边界；必须 typed allowlist |
| RDF/OWL/SPARQL mandatory runtime interchange | 当前 operational contract 优先；RDF 可作为 governance projection |

## 19. Approval and Freeze Criteria

本 Reviewed Candidate 只有在以下条件满足并由 Muyu 明确批准后才成为 `Approved/Frozen`：

- [x] architecture、correctness/security、delivery 完成两轮 critic review；
- [x] Round 2 主审裁决记录所有接受、修改、拒绝与延期；
- [x] 主合同与 Stage Profile、Technical Annex 分层且有明确 precedence；
- [x] public RSC、persistent READY、caller role、bare question hash 等 P0 已从合同移除；
- [x] five gate、AuthorityDecision、CAS activation、dynamic eligibility、revocation 和 release barrier 无 circular dependency；
- [x] oracle claim ceiling 与当前 API leak blocker 明确；
- [x] Technical Annex 的 fixed conformance vectors 和 object subjects 通过独立一致性检查（34 positive + 30 negative）；
- [x] fresh product reader 能准确复述 Studio/Agent inputs、outputs、commands、failures 和 PRD entry gate；
- [x] fresh technical reader 能准确复述 identity、gate closure、CAS、revoke/commit ordering 和 Stage 1 exclusions；
- [x] fresh delivery reader 能在无隐藏假设下排 S0/V0/V1–V5 与 external demo go/no-go；
- [x] Muyu 批准 Reviewed Candidate。

批准前本文件不得作为已冻结 implementation authority，也不得用来宣称当前 PoC conformant、production-ready 或 HKEX-validated。

## Appendix — Canonical glossary

| Term | Meaning |
|---|---|
| GSR | Studio 发布的环境无关、不可变业务语义 release |
| RuntimeSnapshotPayloadManifest | Shared Kernel 内部 immutable runtime component graph；不含 gate status |
| VerificationAttempt | 某一 gate 对 exact subject 的一次不可变 PASS/FAIL 记录 |
| VRS | 将 exact payload 与五份 PASS attempts 密封后的唯一 Agent-resolvable semantic/runtime artifact |
| SEALED | 密封事实；不等于永久可运行 |
| Eligibility | 某一 phase/time/context 下的 ALLOW/DENY；不能回写 VRS |
| Activation | exact scope/environment/channel 对某 VRS 的 append-only selection decision |
| Revocation | 对 exact target 的不可逆 safety record |
| PolicyDecision | Shared Kernel 内部 immutable policy-evaluation evidence；不是 public cross-product input/output，也不单独授权动作 |
| `ANSWER_CANDIDATE` | deterministic execution 后暂存并绑定 evidence/projection 的内部状态；只有有效 ResultReleaseCommit 后才派生为外部 `ANSWERED`，永远不是第六种用户 outcome |
| ResultReleaseCommit | evidence/projection/final eligibility 耐久后允许发送 exact bytes 的 commit |
| RuntimePackageView | governance-free、最小可执行、只读 runtime façade |
| SCR | 经披露批准的 typed proposed feedback；不是真相 |
| Evidence replay | 重放已保存的 exact sanitized evidence/projection，不是重新查询 source data |
