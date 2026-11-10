# Ontology Analytic Agent Product-Domain PRD v0.1

Document ID：`ontology-analytic-agent-prd/0.1`
状态：Revised Candidate；Pending Fresh-reader Closure and R-01 Decision；not implementation authority
日期：2026-08-19
Decision Owner：Muyu
Accountable Product Owner：Agent Domain Owner（V1 前落实人名）
规范性父级：`01_product_group_strategy.md` v1.0、`02_shared_product_contract.md` v0.1 Approved/Frozen
当前冻结 Profile：`synthetic-trusted-flow/core@1`（ADT synthetic reference tracer）
待决 Profile revision：`synthetic-trusted-flow/core@1.1` Revision Pack R-01（E-01 `CONCEPT_NOT_BOUND` + E-02 `SELECT_REFERENCE`）
共同产品附件：`stage1-demo-delivery-companion/0.1`；file digest `sha-256:800d15d41fb2ad9143eac14d0f13a9297f18afe6bf704e1bce4e8b466e4a8b74`
评审裁决：`reviews/product-prds-round-2-adjudication.md`

## 0. 如何阅读

本 PRD 定义 Ontology Analytic Agent 作为独立 Product Domain 的用户问题、运行边界、产品行为和 Stage 1 验收。它不重复 Shared Product Contract 的 canonical bytes、digest、ledger 或 schema 细节，也不决定最终模型、数据库、前端框架、容器或 K8s 拓扑。

发生冲突时，优先级为：Shared Product Contract > Synthetic Profile > 本 PRD > 后续技术设计。本文中的能力模块是产品责任分区，不等于必须建设同数量的微服务或页面。

`05_stage1_demo_delivery_companion.md` 只定义两产品共用的 demo promise、最小表面、RACI 和 delivery evidence；它不是第三个产品或 runtime authority。

本文生命周期固定为 `Draft → Revised Candidate → Reviewed Candidate → Approved/Frozen → Superseded`。当前为 Revised Candidate；Reviewed Candidate 表示独立 closure review 已通过，仍不等于 implementation authority；只有 Decision Owner 对两份 PRD 与 exact Companion revision/digest 的原子批准才形成 Approved/Frozen。

### 0.1 Product at a glance

| Question | Stage 1 answer |
|---|---|
| Primary user/job | Release Manager 准备/激活受治理 runtime；Analyst 提问；Business User 阅读结论；Auditor重放 exact evidence |
| Product input | exact authorized GSR/environment refs for release operations；trusted request context；activated SEALED VRS |
| Visible outcome | stable lifecycle receipt；五种 typed analytic outcome；safe evidence/replay；safe feedback acknowledgement |
| Formal handoff | committed User Evidence Projection/ExecutionEvidence；typed UNKNOWN_CONCEPT SCR to Studio |
| Fail closed | wrong/no activation、ineligible dependencies/context、unsupported semantics、policy denial、execution/release/evidence failure、invalid feedback chain |
| Must never happen | 读 Studio draft/bare GSR、caller自报权限、模型写 authoritative SQL/数字、latest/legacy fallback、commit前泄露 analytic bytes、feedback自动改Ontology |
| Stage 1 promise | 用 constructed-synthetic ADT 证明 exact runtime release → governed answer/evidence → revoke → safe triage；不证明 customer truth 或 production platform |

## 1. Product Decision

Ontology Analytic Agent 是受治理的分析运行面，不是“会读取知识图谱的聊天机器人”。它的核心职责是：在确切的语义版本、数据身份、环境 binding、policy、runtime capability 和 activation 均可验证时，把自然语言分析意图约束成确定性执行，形成 typed Facts/Claims，并且只在最终资格复核、证据持久化和 release commit 成功后释放答案。

Agent Product Domain 还承担 Release & Activation Manager 的最小 Runtime Release Operations 产品任务：从 exact GSR/environment refs 观察 verification、显式选择五份 PASS、请求 seal/activate/revoke 并得到 stable result。Agent Domain Owner 对用户任务结果负责，但不拥有 semantic truth、gate verdict 或 privileged command authority。

Stage 1 只证明一条 ADT synthetic vertical tracer：

```text
trusted user context + analytic question
→ exact scoped Activation
→ SEALED VRS + PRE_QUERY Eligibility ALLOW
→ closed-world semantic boundary
→ governed plan + deterministic query
→ typed Facts + typed Claims
→ allowlisted User Evidence Projection
→ RESULT_RELEASE Eligibility ALLOW
→ durable Evidence + ResultReleaseCommit
→ committed answer bytes
```

Agent 只消费已密封、已激活且当次 eligibility 为 ALLOW 的 VRS。它不读取 Studio draft、ClearedInput、review comment、裸 GSR 或 mutable `latest` pointer，也不修改 Ontology。

## 2. Problem Statement

传统分析 Agent 很容易把三件不同的事混在一起：理解问题、生成查询、组织答案。当企业定义、物理数据、权限、版本和证据要求复杂时，“模型给出了一个像样答案”并不等于答案正确、获准、可解释或可追责。

当前 ADT PoC 资产已经具备确定性指标计算、SQL compiler、DuckDB execution、部分 typed claim 和基础 execution history，但仍缺少以下产品能力：

- 只解析 exact activated VRS，而不是本地 `latest` package；
- 在触达 Query Engine 前区分 Answer、Clarify、Refuse 和前置失败；
- 从可信 session/context 获取 principal、scope、purpose，而不是接受 request body 自报角色；
- 对 Activation、Revocation 和每次 execution 做动态 eligibility；
- 将所有数字、方向、排名和限制绑定为 direct typed Claims；
- 通过 closed-schema allowlist 输出证据，避免泄露 table、column、SQL、mapping ID、path 或 prompt；
- 在最终 eligibility、evidence durability 或 audit 失败时保证 answer bytes 为 0；
- 把安全反馈异步送回 Studio，同时不让反馈自动变成业务真相。

没有这些能力，现有 demo 只能证明“ADT 算法可以运行”，不能证明“Agent 在企业知识与控制之上可信地工作”。

## 3. Goals and Non-goals

### 3.1 Goals

1. 对每个请求只解析 exact ChannelScope 下当前已激活、SEALED、未 revoke 且当次 eligible 的 VRS。
2. 在 Query Engine 前完成语义支持范围、必需参数和 policy boundary 判断。
3. 将获准请求编译为可审计的 governed plan，并通过确定性 operator 计算结果。
4. 让每个已显示数字、方向、排名和限制都有 direct typed Claim，并覆盖每个 preregistered required output。
5. 只输出 principal/purpose 对应的 allowlisted User Evidence Projection。
6. 把 Evidence + ResultReleaseCommit 作为答案可释放的硬门，而不是回答后的补录。
7. 支持 exact committed evidence replay，并清楚区分 replay 与重新查询历史数据。
8. 对未知概念形成可安全披露、可行动、可幂等送达的 typed SCR。
9. 让 Release Manager 可重复完成 exact GSR → verified/sealed/activated VRS → revoke 的最小产品任务，而不建设独立 portal。

### 3.2 Non-goals

- 让 LLM 自由生成 authoritative SQL、数值、排名或业务定义；
- 读取 Studio draft、原始需求文档、ClearedInput 或 review rationale；
- 把裸 GSR、OntologyPackage、SemVer 或 `latest` 当可执行 authority；
- Stage 1 支持开放式 BI、任意 ad-hoc SQL 或所有市场指标；
- Stage 1 支持 streaming、partial answer 或 token-by-token release；
- 支持历史 source data 重放、time travel 或通用数据虚拟化；
- 支持 VRS 以外的 component/GSR/attestation transitive revocation；
- 支持 `UNKNOWN_CONCEPT` 之外的 product feedback 或 incident lifecycle；
- 建设 production IAM、DLP、PKI、KMS、HA、SLA 或 enterprise audit platform；
- 证明 customer 业务定义正确、生产安全要求已满足或 PoC 已 production-ready；
- 决定最终商业 SKU、顶层 UI、repository 或 deployment 数量。
- 建设 production release portal 或完整 Studio/Agent operations workbench。

## 4. Users and Jobs-to-be-Done

| User / role | Primary job | Product outcome |
|---|---|---|
| Business Analyst | 用业务语言询问指标、趋势、分段和 computed contribution/decomposition | 有来源、有口径、有范围说明的答案，或明确 Clarify/Refuse |
| Business User / Executive | 快速获得可读结论并理解关键限制 | 不暴露技术内部信息的证据化摘要 |
| Evidence Reviewer / Auditor | 复核某个已交付答案用了什么已批准版本、数据和控制 | exact committed evidence projection 与稳定 handle |
| Application Consumer | 通过稳定 API 获取 typed outcome | closed outcome contract，而非解析自由文本异常 |
| Release & Activation Manager | 用 exact refs 准备 runtime、显式选择 attempts、请求 seal/activate/revoke | authoritative receipt 或 stable fail-closed result；Stage 1 可用 controlled CLI/API/internal view |
| Agent Domain Owner | 对运行行为、fail-closed、projection 和 release quality 负责 | 可验收的 governed runtime product |

Stage 1 中 authority、policy 和用户身份可由明确标注的 local/simulated registry 提供。它用于证明产品 workflow enforcement，不可描述为 customer production IAM 或真实职责分离。

## 5. Current Baseline and Reuse Policy

| Existing asset | Reuse | Required change before conformant claim |
|---|---|---|
| Deterministic ADT calculator / formula evaluator | 保留为 legacy shadow comparator / regression behavior baseline | 只证明 migration parity；不能产生 Control truth/PASS；只通过 RuntimePackageView 接收获准语义 |
| Intent planner and SQL compiler | 保留可验证步骤、参数化 SQL 和 allowlist | 输入改为 exact VRS runtime projection；禁止模型写 authoritative SQL |
| DuckDB / synthetic data fixture | 保留为 Stage 1 execution engine | 绑定 exact DataIdentity；不得据此声称目标数据库已兼容 |
| Typed response / claim fields | 迁移为 Facts/Claims 基础 | 覆盖所有数字、方向、排名和限制；不能只给泛化 explanation |
| `/analyze` and execution history | 保留 task flow 与 UI learning | 增加 trusted context、five outcomes、eligibility、release commit、safe projection |
| 33 automated tests + 33 validation checks | 全部保留 | 与 contract vectors、8-case suite、fault/mutation/leak tests 一起通过 |
| Static Ontology/Semantic/Chat console | 保留用户旅程和讲解资产 | 必须切到真实 governed API；浏览器内 mock state 不能作为 authority |
| `latest.json` package resolver | 仅作短期 shadow compare | governed route cutover 后不可作为 authority 或 fallback |

当前 `ontology.exchange_analytics.adt@1.2.0` 是 regression fixture，不是 conformant GSR/VRS。迁移不得重写已验证的 ADT 算法，也不得用 legacy package 绕过 Studio 的 blind Candidate/Decision/Semantic Approval 流程。

## 6. MVP Product Capabilities

### 6.1 Trusted Request and Snapshot Resolver

- 从可信 session/context 获取 tenant、workspace、environment、channel、principal、purpose、locale 和 request budget；
- 解析 exact committed ActivationRecord 与 exact SEALED VRS；
- 对 RESOLVE/PRE_QUERY 形成 point-in-time Authority/Policy/Eligibility evidence，对 EVIDENCE_READ 形成 exact evidence/projection、audience、purpose 的独立 point-in-time eligibility；
- 对 no activation、wrong scope、unknown profile、identity conflict、required attempt/authority/policy expired or stale、revoked target 或 current Eligibility DENY fail closed；VRS 自身保持同一 digest 和 `SEALED` fact；
- 永不自动 fallback 到 legacy、revoked digest、bare GSR 或 mutable latest。

### 6.2 Runtime Release Operations

- Release Manager 提交 exact authorized GSR 与 environment component refs，查看 derived verification progress 和 stable failure owner；
- 调用者显式提供 exact five PASS refs，不自动选择 `latest`；
- seal、activate、revoke 只在各自 authority/eligibility 条件通过后形成 authoritative receipt；
- Agent Domain Owner 对 product task/failure routing 负责；Studio owns GSR outcome，gate authorities owns verdicts，Release Manager owns commands，Shared Kernel owns mechanism；
- Stage 1 通过 controlled CLI/API/internal view 即可，不要求 customer-facing portal。

### 6.3 Semantic Boundary and Outcome Router

> `REFUSED + CONCEPT_NOT_BOUND` 是 R-01/E-01 的 `core@1.1` candidate behavior，当前 Frozen `core@1` 不支持。R-01 未获批且 new Profile/Annex/vectors 未独立通过前，相关 V4 path 必须 fail closed，不能被计为 conformant capability。

- 用 VRS 内的 executable semantic projection 判断概念、指标、参数、分段与支持范围；
- 已注册且受支持的操作缺少/歧义 user parameter 时返回 `CLARIFY`；
- 请求已理解但不获准或不支持时返回 `REFUSED`；known semantic area 中 zero concept binding 返回 `REFUSED + CONCEPT_NOT_BOUND`，Query Engine access = 0；
- contract/integrity/activation/eligibility 问题返回 `FAILED_PRECONDITION`；
- 在语义边界决定完成前不触达 Query Engine；
- boundary outcome 也留下最小 durable evidence，并证明 Query Engine access count = 0。

`UNKNOWN_CONCEPT` 是可选 feedback side effect，不是第六种 analytic outcome。`DISCLOSURE_BLOCKED`、disclosure DENY 或 outbox failure 只表示 SCR 没有创建，不能改写已持久化的 `REFUSED`。

### 6.4 Governed Plan and Deterministic Execution

- 把已支持的分析意图变成 typed analytic request 和可审计 plan；
- 只选择 ontology 允许的 metric、dimension、filter、time grain、operator 和 comparison；
- 由 deterministic compiler 生成 parameterized query；
- 执行前验证 binding、DataIdentity、query policy、resource budget 和 operator capability；
- 执行后核对 result shape、units、rounding、population 和 reconciliation controls；
- 使用 frozen ADT mutation profile证明 mapping、eligibility filter、calendar、join fanout、market、period、unsupported transformation、datetime fail-closed、duplicate fact grain 和 zero/missing trading-day denominator 不会静默产生错误 ANSWERED；
- 运行失败产生 `FAILED_EXECUTION`，不得把 partial result 包装为答案。

### 6.5 Facts, Claims and User Projection

- 将 query result 先转成 typed Facts，再由获准 rule/operator 形成 typed Claims；
- 所有显示数字、方向、排名和限制必须有 direct Claim；ControlManifest expected refs 预登记的 top-line、comparison、contribution/decomposition、ranking（如适用）和 limitation 也必须全部出现；
- `driver/为什么` 在 Stage 1 只可呈现 deterministic contribution/decomposition，不得生成未获准的 causal claim；
- User Evidence 使用 closed-schema allowlist，而不是 prompt redaction 或 denylist；
- 输出包含 safe claim refs、metric semantic ID、VRS safe identity、DataIdentity safe identity、policy/evidence ref 和 render identity；
- 不输出 SQL、params、raw rows、table、column、join、locator、mapping ID、prompt、path、stack、credential 或 governance comment；
- rounding、scale、suppression、locale 和 limitation 必须是确定性且进入 render evidence。

### 6.6 Evidence, Release and Replay

- Stage 1 不支持 streaming；有效 ResultReleaseCommit 前，analytic projection bytes 对用户不可达；
- release 前重新读取当前 activation head、revocation epoch、authority 和 policy；
- Activation、Revocation 与 ResultReleaseCommit 的并发结果必须符合 Core 唯一允许的 total-order outcomes；旧/revoked head 上未 commit execution 不得释放；
- 只有 durable commit 引用 exact `ANSWER_CANDIDATE` evidence 与 projection 后，外部 outcome 才是 `ANSWERED`；
- final decision、head reread、audit、persistence 或任一 required durability step 失败，analytic projection/partial bytes 必须为 0；safe failure/boundary envelope 可按 closed allowlist 返回；
- evidence replay 需要 current EVIDENCE_READ authority/policy/eligibility，只重放已保存的 exact committed sanitized bytes，不重新查询、rerender 当前或历史数据；VRS replacement/revoke 不销毁 separately authorized committed audit evidence。

### 6.7 Safe Feedback to Studio

- Stage 1 只支持由 `REFUSED + CONCEPT_NOT_BOUND` committed boundary execution 触发的 `UNKNOWN_CONCEPT`；
- 由安全上下文 projector 形成 closed ProposedSCRPayload，不复制 raw question；
- 经 disclosure decision、enqueue authority 和 durable asynchronous outbox 送达 Studio；
- 无法形成足够且合法的 safe context 时记录 feedback `NOT_CREATED / DISCLOSURE_BLOCKED`，不创建 SCR，也不改变 top-level `REFUSED`；
- outbox 故障不撤销或改写已 committed analytic outcome，但必须可重试、可观察、幂等且不重复；
- SCR disposition 不改变已完成 outcome，也不能自动修改 Ontology；没有新 GSR/VRS/Activation 时，重复问题保持原 outcome。

## 7. End-to-End User Journeys

### Journey A0 — Prepare and activate an exact runtime

1. Release Manager receives exact authorized GSR and approved environment component refs；Studio draft/ClearedInput are not visible。
2. System derives verification progress；gate authorities independently produce PASS/FAIL。
3. Release Manager explicitly selects exact five PASS refs and requests seal/activate through a controlled surface。
4. System returns authoritative receipts or stable wrong-ref/failed-gate/unauthorized/CAS/ineligible outcomes；Agent Domain Owner owns product failure routing。
5. Later revoke uses the same exact-scope product path；there is no un-revoke or legacy fallback。

### Journey A — Supported ADT question

1. Analyst 在受信 session 中询问某个获准 period 的 ADT、趋势或分段。
2. Agent 解析当前 Activation、SEALED VRS 和 PRE_QUERY Eligibility。
3. Semantic boundary 将问题约束为 metric、period、population、segment、unit 和 rounding。
4. Planner/Compiler/Query Engine 走确定性路径，产生 Facts 和 direct Claims。
5. Projector 形成 safe answer/evidence；release phase 重新检查当前 head 和 revocation。
6. Evidence 与 ResultReleaseCommit durable 后，用户收到 `ANSWERED` 与 safe evidence handle。

### Journey B — Clarify or refuse before data access

1. 用户对已注册支持的 ADT 操作缺少必需 period；Boundary Router 返回 `CLARIFY/MISSING_PERIOD`，明确要补什么，Query Engine access count = 0。
2. 若 comparison/operator/concept 不在 frozen support，或 purpose/policy 不允许，返回 `REFUSED` 与 safe reason；不要求用户用 free text 补出新的业务定义。
3. known semantic area 中 well-formed term zero match 时固定为 `REFUSED/CONCEPT_NOT_BOUND`；可另行尝试安全 feedback，但 feedback 成败不改 outcome。

### Journey C — Evidence review and replay

1. 授权 Reviewer 通过 opaque evidence handle 请求查看已交付答案。
2. 系统对 exact evidence/projection、audience、purpose 做独立 EVIDENCE_READ authority/policy/eligibility 检查。
3. 返回该 audience/purpose 获准的 exact committed projection bytes/digest。
4. 当前数据、当前 VRS 或当前 renderer 改变都不会重算或 rerender 旧答案；重新分析是新 execution，source query count for replay = 0。

### Journey D — Revoke or activation change during execution

1. Execution 绑定开始时的 exact activation head。
2. 若 VRS revoke 或新 Activation 在 release commit 前先提交，final reread/eligibility 失败。
3. 系统保留内部失败证据，但对用户释放 answer bytes = 0。
4. 若 release commit 已先成功，该 exact committed projection 可发送/重放；后续 execution 受新状态约束。

### Journey E — Unknown concept feedback

1. Boundary Router 对 known semantic area 中 zero-match term 持久化 `REFUSED/CONCEPT_NOT_BOUND` boundary outcome，Query Engine access = 0。
2. 经允许的 term alias、semantic area、reason、safe detail ref 和 opaque interaction handle 形成 proposal。
3. disclosure 与 enqueue 均通过后，SCR 异步进入 Studio Change Inbox。
4. 用户的原问题、数值、SQL、physical binding 或 free text 不进入 SCR；Agent outcome 不等待 Studio 在线；`DISCLOSURE_BLOCKED`/outbox failure 只作为 feedback acknowledgement，绝不成为第六 outcome。

## 8. Functional Requirements and Acceptance

### 8.1 Resolver and Eligibility

| ID | Requirement | Acceptance |
|---|---|---|
| AGT-RES-01 | trusted context | principal、role、scope、purpose 只能来自 trusted registry/session；request body 自报不能授权 |
| AGT-RES-02 | exact activation | resolver 只接受 exact committed ActivationRecord、SEALED VRS 和 full scoped refs |
| AGT-RES-03 | dynamic eligibility | ACTIVATE、PRE_QUERY、RESULT_RELEASE、EVIDENCE_READ 分别产生所需 point-in-time decision；VRS 不保存永久 READY/EXPIRED |
| AGT-RES-04 | no latest/fallback | no VRS、revoked target、expired/stale required dependency/context、Eligibility DENY、wrong-scope、unknown profile、identity conflict 均 fail closed；VRS bytes/SEALED不变；legacy query call = 0 |
| AGT-RES-05 | activation consistency | execution 必须 pin exact activation head；切换后旧 head 的未 commit execution 不能释放 |

### 8.2 Runtime Release Operations

| ID | Requirement | Acceptance |
|---|---|---|
| AGT-ROP-01 | exact release input | Release Manager 只用 authorized GSR/environment refs；Studio draft/ClearedInput/评论不可见 |
| AGT-ROP-02 | explicit verification selection | derived progress 可查看，但 five PASS refs 必须由调用者显式选择；不选 latest |
| AGT-ROP-03 | stable lifecycle result | wrong/failed gate、payload mismatch、unauthorized command、CAS conflict、ineligible activation 均给 stable fail-closed result 与唯一 failure owner |
| AGT-ROP-04 | no authority transfer | Agent Domain Owner owns product outcome；GSR、gate、seal/activate/revoke authorities 仍按 frozen registry |
| AGT-ROP-05 | lightweight surface | Release Manager 可通过 controlled CLI/API/internal view 完成 exact GSR → seal → activate → revoke；不要求新 portal |

### 8.3 Boundary and Planning

| ID | Requirement | Acceptance |
|---|---|---|
| AGT-BND-01 | closed semantic support | metric/dimension/operator/parameter 必须在 executable projection 中；未知项不由模型猜测 |
| AGT-BND-02 | clarify | 只有 registered supported operation 的 user parameter 缺少/歧义才返回 `CLARIFY`；safe actionable prompt，query access = 0 |
| AGT-BND-03 | refuse | policy/frozen support boundary 返回 `REFUSED`；zero semantic match 固定 `CONCEPT_NOT_BOUND`；query access = 0，reason 不泄露内部规则 |
| AGT-BND-04 | stable failures | contract/integrity/activation/eligibility 为 `FAILED_PRECONDITION`；获准执行后的 query/reconcile/evidence failure 为 `FAILED_EXECUTION`；各至少一条 positive fixture |
| AGT-BND-05 | no sixth outcome | DISCLOSURE_BLOCKED/outbox state 只能是 feedback acknowledgement，不替代五种 top-level analytic outcome |
| AGT-PLN-01 | governed plan | plan 只引用获准 semantic IDs、bindings、operators 与参数；全部可审计 |
| AGT-PLN-02 | deterministic query | authoritative SQL/number/rank 由 deterministic compiler/operator 产生，不由 LLM 自由生成 |
| AGT-PLN-03 | result validation | shape、unit、population、rounding、reconciliation 不通过时不得形成 Answer Candidate |
| AGT-PLN-04 | bounded ADT mutations | frozen profile 覆盖现有7项、datetime fail-closed、duplicate fact grain、zero/missing trading-day denominator；kill = 100%，不扩成 generic compiler suite |

### 8.4 Claims and Projection

| ID | Requirement | Acceptance |
|---|---|---|
| AGT-EVD-01 | typed Facts/Claims | 8-case suite 中所有 answer facts 与 claims 可验证且双路径一致 |
| AGT-EVD-02 | direct claim coverage | 所有显示数字、方向、排名和限制 direct Claim coverage = 100% |
| AGT-EVD-02A | required-output completeness | Control expected refs 预登记的 top-line/comparison/contribution-decomposition/ranking/limitation 全部出现；completeness = 100%，不能删难项提高 coverage |
| AGT-EVD-03 | allowlisted projection | forbidden key 和 value token、secret canary 命中均为 0 |
| AGT-EVD-04 | evidence usefulness | 每个 ANSWERED 至少有 safe claim refs、metric ID、VRS、DataIdentity、policy/evidence、render identity |
| AGT-EVD-05 | no semantic rewrite | suppression/coarsening/rounding 显式进入 evidence；projection 不暗改业务含义 |
| AGT-EVD-06 | staged answer | 未被有效 ResultReleaseCommit 引用的 `ANSWER_CANDIDATE` 对外不可见为 `ANSWERED` |
| AGT-EVD-07 | no causal overclaim | Stage 1 driver 只映射获准 contribution/decomposition Claim；任何 unbound causal/factual clause 阻止 render/release |

### 8.5 Release, History and Feedback

| ID | Requirement | Acceptance |
|---|---|---|
| AGT-REL-01 | final reread | release 使用当前 head、VRS、revocation epoch、authority 和 policy，而非 execution 起点缓存 |
| AGT-REL-02 | durable release barrier | evidence、projection、final eligibility、audit 与 required commit durable 前 analytic projection bytes = 0；safe closed failure envelope 可非空 |
| AGT-REL-03 | deterministic concurrency outcome | Activation、Revocation、ResultReleaseCommit 并发只能产生 Core 允许的有序结果；superseded/revoked head 的未 commit execution 不能释放 |
| AGT-REL-04 | no partial/streaming | Stage 1 不支持 streaming；失败不输出 partial analytic answer/token |
| AGT-HIS-01 | exact replay | EVIDENCE_READ 对 exact evidence/projection、audience、purpose 做 current eligibility；获准 replay bytes/digest 与原 committed projection完全一致 |
| AGT-HIS-02 | replay distinction | 旧 evidence replay 不查询 source、不 rerender；新数据分析产生新 execution/evidence |
| AGT-CHG-01 | one typed request | 仅 `REFUSED/CONCEPT_NOT_BOUND` boundary 可进入 Stage 1 UNKNOWN_CONCEPT SCR；其他类型/conditions 稳定拒绝 |
| AGT-CHG-02 | safe payload | raw question/hash、values、SQL、physical binding、prompt、path、free text 泄露 = 0 |
| AGT-CHG-03 | disclosure + enqueue | complete valid chain 才能 enqueue；payload/ref mutation、wrong scope、expired decision、wrong audience 均阻止，Studio visible side effect = 0 |
| AGT-CHG-04 | async/idempotent | analytic outcome 不依赖 Studio 在线；retry 不重复 SCR，feedback failure不改写 outcome |
| AGT-CHG-05 | no auto truth | SCR accepted/triaged 不改变 runtime answer、GSR 或 Ontology；无新 GSR/VRS 时重复问题 outcome 不变 |

### 8.6 Product Operations

| ID | Requirement | Acceptance |
|---|---|---|
| AGT-OPS-01 | persistence/recovery | refresh/restart 后 committed activation、revocation、evidence、release、outbox 状态不丢；authoritative state integrity-invalid/unavailable 时 fail closed、no silent repair/fallback |
| AGT-OPS-02 | readiness | governed route 无 eligible VRS 时 readiness 明确失败，不偷偷回退 legacy |
| AGT-OPS-03 | complete audit | S0 inherited action/outcome matrix 中每个 command 都有 product owner、authority、committed fact、conformance family 和 failure owner；audit completeness = 100% |
| AGT-OPS-04 | safe console | console 只调用真实 allowlisted governed API；browser mock 不能显示为 live evidence |
| AGT-OPS-05 | honest labels | main result、replay、export、runbook 邻接显示 constructed-synthetic/simulated/local/non-customer/non-production limitation；不依赖 hover/drawer |

## 9. User Stories

1. 作为 Analyst，我希望用业务术语询问 ADT，而不用知道表名或 SQL。
2. 作为 Analyst，我希望缺少 period 时收到明确补充项，而不是一个猜出来的数字。
3. 作为 Business User，我希望答案显示口径、单位、范围和主要限制。
4. 作为 Executive，我希望结论简洁，但每个关键数字仍能追到 safe evidence。
5. 作为 Application Consumer，我希望五种 outcome 是稳定 typed contract，不依赖解析错误文案。
6. 作为 Evidence Reviewer，我希望看到 exact VRS、DataIdentity、policy 和 claim refs，而不看到越权物理 schema。
7. 作为 Evidence Reviewer，我希望重放原答案时得到完全相同的已提交 projection，而不是拿今天的数据重算。
8. 作为 Release Manager，我希望只有 exact SEALED、eligible VRS 可以被激活。
9. 作为 Release Manager，我希望 revoke 后新请求和未提交结果立即 fail closed。
10. 作为 Release Manager，我希望切换 VRS 时旧 activation 上未提交的 execution 不能漏出答案。
11. 作为 Agent Domain Owner，我希望没有 eligible VRS 时系统显式 unavailable，而不是走 legacy fallback。
12. 作为 Agent Domain Owner，我希望所有显示数字、方向、排名和限制都有 direct Claim。
13. 作为 Security Reviewer，我希望 request body 的 role/scope 永远不能提升权限。
14. 作为 Security Reviewer，我希望 persistence、audit 或 final check 失败时 answer bytes 为 0。
15. 作为 Product Owner，我希望 unsupported coverage 与 supported correctness 分开报告，不能删题提高正确率。
16. 作为 Studio Triager，我希望未知概念反馈无需查看 raw question 也能判断 owner 和 disposition。
17. 作为用户，我希望 feedback delivery 故障不撤销已成功答案，也不会造成重复 request。
18. 作为 Demo Presenter，我希望 UI 清楚展示语义版本、数据身份、执行证据和限制，而不是暴露内部实现。
19. 作为 Release Manager，我希望显式选择 exact five PASS refs 并得到稳定 receipt/failure，而不是让系统猜 latest。
20. 作为 Evidence Reviewer，我希望当前 EVIDENCE_READ authorization 通过后重放原 committed bytes，即使旧 VRS 已被替换或 revoke，也不重新查询数据。
21. 作为 Analyst，我希望“最大驱动”明确表示 computed contribution/decomposition，而不是 Agent 暗示因果关系。
22. 作为用户，我希望 UNKNOWN_CONCEPT feedback 失败时仍保持原 `REFUSED` outcome，而不是出现第六种状态。

## 10. Success Metrics

### 10.1 Product-family metric

- `Time to First Trusted Scenario`：完全引用 Product Strategy，从第一份 ClearedInput 正式登记，到预登记 must-answer suite 全部达到可信门禁；按 Companion closed schema 分报 wall-clock、`internal_active_minutes`、`external-reviewer_active_minutes` 与 `client_confirmation_wait_minutes`，并从 exact minutes统一派生 person-hours/hours。
- `Trusted Scenario Completion Rate`：完全引用 Product Strategy，以所有进入 intake 的场景为固定分母。`completion_state` 仅为 `TRUSTED_COMPLETED/NOT_COMPLETED`；未完成场景的 `strategy_reporting_category` 必须且只能为 `SCOPE_CHANGE/PAUSED/FAILED/UNSUPPORTED/CLARIFY/REFUSE` 之一；`MISSING/WITHHELD/UNCONFIRMED` 仅是正交的 `intake_condition_flags`，不能从分母删除或静默映射。

Activated VRS to First Committed Answer、First Safe SCR 和 First Revoke Proof 只作为 subordinate milestones，不能结束 North-star。Studio、Agent 与 Product-family calculator 必须对 Companion 定义的 `product-family-metric-events-v0.1` fixture 产生相同 start、stop、wall-clock、三项 effort/wait totals、completion state、denominator、六类 counts 与 intake flags；未知类别/unit或missing/null/negative duration fail closed。

### 10.2 Agent quality metrics

| Metric | Stage 1 target |
|---|---:|
| Frozen ADT suite | 8/8，4 ANSWERED + 1 CLARIFY + 3 REFUSED |
| Supported-answer correctness | 100% against the selected ControlManifest and its declared oracle provenance/limitations；default claim=`second-person-reviewed CONSTRUCTED_SYNTHETIC control conformance`；只有 exact manifest 满足父级三人分离或 authoritative-source 条件时才可采用父级允许的更高 claim wording |
| Pre-seal vs active API parity | outcome/Facts/Claims/projection diff = 0 |
| Direct Claim coverage | 100% of displayed numbers/directions/rankings/limitations |
| Required-output completeness | 100% of preregistered top-line/comparison/contribution-decomposition/ranking/limitations |
| Boundary data access | CLARIFY/REFUSED Query Engine access count = 0 |
| Projection leakage | forbidden keys/values/secret canary = 0 |
| Release fault leakage | analytic/partial bytes = 0 for every pre-commit fault/revoke/new-head case；safe closed failure envelope separately counted |
| Evidence completeness | required safe identities non-empty = 100% |
| Exact evidence replay | digest/bytes match = 100% |
| Revoked/fallback execution | 0 |
| UNKNOWN_CONCEPT fixtures | 5/5 actionable within two minutes; leakage = 0 |
| Five-outcome conformance | frozen 8 business cases + 1 FAILED_PRECONDITION + 1 FAILED_EXECUTION probe; closed safe envelope for all five |
| ADT mutation profile | current 7 + datetime fail-closed + duplicate fact grain + zero/missing denominator；100% kill |

Correctness、coverage、Clarify、Refuse、failed、Claim coverage、mutation kill rate 和 leakage 必须分别报告。不能通过删除 frozen cases 或把不支持问题都 Refuse 来改善“正确率”。

吞吐量、token 数、生成文本长度、三元组数量和 UI 点击数不是 Stage 1 trust success metric。

## 11. Stage 1 Scope and Exit

### 11.1 Must ship

- V1：authorized GSR → runtime payload → four environment verifications + semantic attempt → exact five-ref SEALED VRS；legacy path 只做 shadow parity，不能提供 Control truth；
- V2：minimum Runtime Release Operations、Authority、Activation/Revocation、dynamic Eligibility、Evidence 与 ResultReleaseCommit；
- V3：真实 allowlisted governed API 与 internal console integration；
- V4：`REFUSED/CONCEPT_NOT_BOUND` → disclosure → durable outbox → Studio triage；Erratum E-01 未获批前 V4 conformance blocked；
- V5：resolver/console cutover、critical fault/mutation/recovery、revoked fallback 关闭。
- `05_stage1_demo_delivery_companion.md` 定义的 lightweight persisted tasks、slice RACI、Demo Promise、proxy/comprehension protocol 与 exact readiness evidence。

Agent 依赖 V0 产出的 exact GSR PublishSubject/Semantic Approval 和 V1 的 authorized GSR，不得从 legacy package 自建语义真相。

### 11.2 Exit criteria

1. frozen `adt.tracer.v1.suite` 在 pre-seal verification 与 normal governed API 两条路径 8/8 一致；
2. exact five PASS refs 才能 seal，且 Agent 只解析 SEALED + activated + eligible VRS；
3. no-VRS、current ineligible、expired/stale dependency/context、revoked target、wrong-scope、identity-conflict 时 query/fallback 为 0；VRS bytes/digest/SEALED不变；
4. 五种外部 outcome 与 query-access/release 语义正确；separate FAILED_PRECONDITION/FAILED_EXECUTION probes、all-five safe envelopes、no sixth outcome 全部通过；
5. direct Claim coverage 与 required-output completeness 均为 100%；driver 只呈现 non-causal contribution/decomposition；
6. user projection forbidden key/value/secret leakage = 0，safe evidence 非空；
7. activation/revoke/release 并发、authority-state integrity failure、required durability failure、refresh/recovery 均按 Core fail closed，analytic/partial bytes = 0；
8. EVIDENCE_READ current eligibility、exact byte replay、zero query/rerender、5/5 SCR、invalid SCR zero side effect、visible labels 和 cross-artifact identity 全部通过；
9. frozen ADT mutation profile 100% kill；shared-calculator defect 可以保持 parity，但必须使 selected reviewed Control fail/seal blocked；
10. 33/33 automated tests、33/33 validation checks 与 current `core@1` 34+30 vectors 保持通过；R-01 获批后使用新 Profile/vector counts；
11. external demo 唯一充分门要求 V0 + V1–V5、governed resolver/console cutover、critical inventory、0 leak、0 premature analytic bytes、exact Delivery Readiness manifest、3/3 comprehension 与 Product & Delivery DRI GO。

上述工作包含于 Synthetic Profile 的 full Stage 1 `16–24 person-days`，不是 Agent PRD 的额外估算。S0 后由 Product & Delivery DRI 重估。

## 12. Testing Decisions

- Boundary tests：4 Answered、1 Clarify、3 Refused frozen cases；Clarify/Refuse query access = 0。
- Outcome tests：另加 1 FAILED_PRECONDITION、1 FAILED_EXECUTION；五种 outcome 使用 closed safe envelope；分别计算 query calls、analytic bytes、safe envelope bytes。
- Resolver tests：no activation、wrong scope、unknown profile、expired/stale dependency or authority、revoked target、identity conflict、legacy fallback；VRS immutable SEALED。
- Gate/seal tests：five attempts exact selection、wrong subject、omitted/failed/expired attempt、payload mutation。
- Authority tests：caller-supplied principal/role/scope、stale trust epoch、wrong purpose、expired decision。
- Runtime Release Operations tests：fresh operator用 controlled surface完成 exact GSR → five-ref seal → activate → revoke；wrong/failed refs和command有stable result/owner。
- Release tests：revoke-before-commit、new-activation-before-commit、commit-first、persistence/audit/required-durability/final-check fault；只断言产品可观察结果，mechanism细节继承 Annex。
- Projection tests：key/value/token/secret canary；required safe evidence cannot be empty。
- Evidence tests：EVIDENCE_READ exact ref/audience/purpose/current eligibility、exact replay digest/bytes、zero query/rerender、new execution vs replay distinction。
- Claim tests：required output inventory recall、unbound factual/causal clause rejection、contribution/decomposition reconciliation。
- ADT mutation tests：冻结现有7项 + datetime fail-closed + duplicate fact key/grain + zero/missing trading-day denominator；100% kill，不声明通用 compiler。
- SCR tests：5 frozen non-constant fixtures、complete-chain mutation、wrong scope/audience/expiry、DISCLOSURE_BLOCKED as subordinate not-created reason、idempotency、outbox recovery/outcome independence。
- Regression：保留现有 deterministic calculator/compiler、33 tests、33 checks；legacy path只是shadow comparator，不能提供Control PASS；不得因新合同重写算法口径。
- Reader/task tests：Analyst 能解释 Clarify；Reviewer 能复述 evidence meaning；Demo Presenter 不把 synthetic oracle 说成 customer validation。

## 13. Dependencies and Product Interfaces

- Ontology Studio：发布 immutable GSR；接收 typed UNKNOWN_CONCEPT SCR；不在线参与普通答案。
- Shared Contracts & Kernel：组装/验证 runtime payload、五类 gate、seal、authority/policy、activation/revoke ordering、projection、evidence commit 和 outbox；不是第三个用户产品。
- Runtime Release Operations：Agent Domain Owner owns product task/failure routing；Release Manager owns commands；gate authorities own verdicts；Shared Kernel owns mechanism；Stage 1 不建独立 portal。
- Stage 1 Demo & Delivery Companion：冻结共同 demo promise、minimum surface、slice RACI 和 delivery checklist；不是 runtime authority。
- Query Engine / data platform：只接受获准 plan/query 和 binding；不把 physical schema 暴露给用户 projection。
- Data Approver / Control Reviewer / Runtime Capability Owner：分别对 binding/data、control 和 operator compatibility 形成 exact attempts。
- Reference Truth Owner：冻结 synthetic oracle 的 claim ceiling；Agent 不得扩大为真实 customer truth。
- Target Platform：ARM64 VM、Docker/K8s、目标数据库与企业 IAM 是后续技术/部署设计；Stage 1 先证明环境无关的产品合同和 local conformant path。

## 14. Risks and Controls

| Risk | Product control | Reopen condition |
|---|---|---|
| 聊天体验掩盖错误口径 | closed semantic boundary + deterministic plan + Claims | 新 operator 有独立 correctness suite |
| 模型越权写 SQL/数字 | LLM 只做意图/叙述；compiler/operator authority | 经正式 risk decision 的新 execution profile |
| Evidence 变成内部信息泄露通道 | typed allowlist + key/value canary tests | 新 audience/purpose profile 独立批准 |
| revoke 后仍由 cache/latest 回答 | exact activation/VRS + no fallback + final reread | distributed cache contract 定义并验证 |
| evidence 后补导致无证据答案 | commit 前 analytic bytes 不可达 + durable ResultReleaseCommit | 等价 streaming release contract 获批 |
| synthetic correctness 冒充业务验证 | oracle limitation + demo label + separate coverage report | 客户 Truth Owner 正式确认 |
| shared calculator parity 被当 correctness | legacy shadow comparator + selected reviewed Control defect injection | 新 evaluator evidence |
| ADT 逻辑硬编码成“通用 Agent” | RuntimePackageView + bounded ADT mutation profile + Strategy second-scenario gate | 两个差异场景验证稳定 core |
| Agent feedback 污染 Studio truth | typed SCR + disclosure + triage-only | 新 Semantic Change profile 与人工门 |
| 复杂治理拖慢演示 | vertical tracer、five outcomes、one revoke、one SCR | external demo gate 不降低 trust invariants |

## 15. Open Decisions — Not Blocking Stage 1

- Agent 长期 buyer、operating owner、商业包装与顶层 UI；
- 目标 LLM/provider、orchestration framework 与 model routing；
- 目标 Query Engine、数据库 dialect 与 production data identity；
- ARM64/K8s 的 image、registry、storage class、network policy 与 observability；
- production IAM/policy engine/audit/KMS；
- streaming、long-running job、human approval during execution；
- broader metric/operator coverage、second scenario 和 multi-domain composition；
- historical source replay、incident/product feedback 和 transitive revoke。
- accepted SCR → human Decision → new GSR/VRS → changed answer 的完整 co-work loop；
- detailed second-scenario core-change ledger；只有 Strategy 2 semantic + 1 binding/execution 差异证据满足后启动。

这些问题不能在只有 ADT synthetic evidence 时被提前冻结。技术设计可以列 adapter seam 与验证问题，但不得用尚未决定的组件反向改变本 PRD 的产品边界。

## 16. Approval Gate

本 Revised Candidate 只有在以下条件满足后才能成为 Reviewed Candidate：

- [ ] 与 Studio PRD 对 GSR、VRS、projection、gates、lifecycle、outcomes 和 SCR 的解释完全一致；
- [x] architecture、correctness/security、delivery 完成两轮 critic review并由主审裁决；
- [ ] 主审接受的 P0/P1 修订通过独立 closure retest；
- [ ] R-01 获批：E-01 有 contract-valid `CONCEPT_NOT_BOUND` decision，E-02 有 contract-valid reference-selection decision；随后 consolidated Profile/Annex/vectors 独立通过；
- [ ] `stage1-demo-delivery-companion/0.1` 的 exact digest `sha-256:800d15d41fb2ad9143eac14d0f13a9297f18afe6bf704e1bce4e8b466e4a8b74` 与本 PRD、Studio PRD 一起进入 `reviews/product-prds-approval-candidate-manifest.md`；其 product surface、RACI、metric dictionary、demo promise 与 readiness evidence 无 competing authority；
- [ ] fresh Agent product reader 能准确复述七个 MVP capabilities、五种 outcome、release barrier、Runtime Release Operations 和禁止项；

以上 closure checklist 全部通过后，Product & Delivery DRI 只可记录状态为 Reviewed Candidate；该记录不是审批或 implementation authority。唯一产生 Approved/Frozen authority 的动作，是 Decision Owner 对 final approval manifest 绑定的 exact Studio PRD、Agent PRD 与 Companion identities/digests 作一次原子批准；任一文档 digest 改变会使旧批准不适用于新 revision。批准前不得把本 PRD 描述为已冻结产品需求，也不得据此声称当前 `/analyze`、execution history 或 static console 已是 conformant Agent。
