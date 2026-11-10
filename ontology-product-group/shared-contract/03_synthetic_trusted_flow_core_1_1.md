# Synthetic Trusted Flow Core — Stage 1 Profile 1.1

Profile ID：`synthetic-trusted-flow/core@1.1`
状态：Draft for independent conformance review；not implementation authority
日期：2026-08-19
Revision direction：R-01 `APPROVE_RECOMMENDED`；record `../reviews/r01-decision-record.md`；file digest `sha-256:33f7a7e0b2abfa3aae31d89af36d188c597bfe35707fe20fa9a157cdd3a0ea4a`
Frozen predecessor：`synthetic-trusted-flow/core@1`；不得原地修改；本 revision 只有在 exact Profile/Annex/vectors 独立通过并由 Decision Owner 另行冻结后才 supersede其用于 Stage 1 V0/V4
上位合同：`../02_shared_product_contract.md` v0.1 Approved/Frozen
Normative Annex candidate：`04_technical_conformance_annex_1_1.md`
Machine contract candidate：`fixtures/core-profile-conformance-manifest-1.1.json`
Pinned external-leaf candidate：`fixtures/external-leaf-manifest-1.1.json`
Fixed vectors / verifier / report：`fixtures/canonical-json-v1.0-core-1.1-vectors.json`、`fixtures/verify_vectors_core_1_1.py`、`fixtures/core-1.1-conformance-report.json`
场景：ADT synthetic reference tracer

## 1. Profile Purpose

本 Profile 把 Shared Product Contract 缩成一个可在现有 ADT PoC 上完成的、端到端可演示 vertical tracer：

```text
safe intake
→ governed reference selection + authoritative commit receipt
→ governed semantic publish
→ verified/sealed runtime snapshot
→ authorized activation
→ evidence-bound analysis
→ revoke prevents query/result release
→ safe UNKNOWN_CONCEPT feedback and human triage
```

它验证产品合同能否工作，不证明 customer 业务定义、生产安全、通用 ontology compiler 或 Knowledge Center 已经成立。

Core Contract 优先于本 Profile。本 Profile 未列出的类型、target、mode、version 或 workflow 一律 unsupported/fail closed，不得按“差不多”处理。

本 revision 只包含两个获批 delta：

1. E-02：把已存在的 Reference Truth Owner selection 变成 closed、acyclic、one-candidate-set-one-commit 的 `SELECT_REFERENCE` transaction；
2. E-01：把 known semantic area 中 zero binding 映射为 `REFUSED/CONCEPT_NOT_BOUND/query_count=0`，并允许安全、可选的 UNKNOWN_CONCEPT feedback side effect。

不变项：two Product Domains、five analytic outcomes、five runtime gates、`adt.tracer.v1.suite` 的 8-case/4+1+3 denominator、ADT arithmetic、constructed-synthetic claim ceiling、16–24 pd parent ROM 和 external-demo gate。新业务场景、SCR type、outcome、生产部署/IAM/K8s、full UI、generic compiler、Knowledge Center 与真实 customer 材料不属于本 revision。

## 2. Fixed Scope and Assumptions

| Dimension | Stage 1 value |
|---|---|
| tenant | `local-synthetic` |
| workspace | `adt-poc` |
| environment | `synthetic-reference` |
| activation channel | `active` |
| scenario | ADT only |
| user topology | one ordinary demo user；simulated control principals |
| transaction contract before freeze | fixed logical state-machine traces；不声称 registrar/file/fsync 已实现 |
| V0b implementation target | local, append-only, crash-detectable framed journal；one process / single writer；仍执行 expected-head/series CAS |
| compatibility | exact-match tuple only |
| data | synthetic/reference artifact only；no raw customer data |
| response | buffered；no streaming |
| replay | `evidence_only` |
| runtime | reuse current deterministic calculator/compiler where safe |

Profile 假设：无 production IAM、DB、HA、K8s、real Query Engine、real customer network、client-origin business material 或 second scenario。

## 3. Stage 1 Claim

默认 oracle class 为 `CONSTRUCTED_SYNTHETIC`，默认两人 control 模式：

- Person A：Reference Truth Owner + Fixture/Adapter Author；
- Person B：Independent Control Reviewer；
- Truth Owner 与 Reviewer 必须不同；Fixture Author 不能是 Reviewer。

在该配置下唯一允许的 claim 是：

> The deterministic flow conforms to a frozen, second-person-reviewed constructed-synthetic control set.

中文表述：

> 该 deterministic flow 符合一套预先冻结、由第二人复核的 constructed-synthetic control set。

禁止使用：`independent oracle`、`independently derived business truth`、`customer validated`、`customer correct`、`production ready` 或含义相同的表达。

如果能满足三人分离或 independently frozen authoritative source，必须产生新的 ControlManifest/oracle class/allowed-claims digest，不能只改 demo 文案。

## 4. Truth and Intake Entry Gate

任何 fixture、oracle、adapter 或 UI 数值调整之前，固定顺序为：

```text
register both ADT truth candidates
→ freeze verification criteria for each candidate
→ assign Truth Owner and Independent Control Reviewer
→ create an approved, non-Package/non-oracle ClearedInput for each selectable candidate
→ freeze one candidate-specific ControlManifest + oracle provenance for each candidate
→ freeze the one truth-neutral SuiteManifest shared by both current ADT candidates
→ freeze one ReferenceCandidate subject per candidate
→ freeze one two-member ReferenceCandidateSet + selection policy
→ Reference Truth Owner creates an immutable ReferenceSelectionProposal
→ evaluate action-exact ReferenceSelectionAuthorityDecision against the exact proposal
→ atomically commit one ReferenceManifest + authoritative CommitReceipt per exact selection key
→ designate the selected candidate tuple as the only downstream truth
→ only then author fixture/adapter
```

### 4.1 Required pre-registration

Public-style candidate 与 current synthetic candidate 必须分别登记，禁止混称。Stage 1 两者的 oracle class 都是 `CONSTRUCTED_SYNTHETIC`；public-style 只表示构造方式/展示风格，并以 `public-style-synthetic` limitation 明示，不能标成 `EXTERNAL_BUSINESS_REFERENCE`。Auxiliary negative candidate 与 selectable/demo inventory 隔离。每个 candidate 至少记录：

- source/provenance 与可核验性；
- ADT formula；
- period 与 trading-day definition；
- population、segment 与 exclusions；
- unit、decimal scale、rounding 与 display rule；
- expected comparisons/decompositions；
- Missing、Withheld、Unconfirmed 与 limitations。

每个可选 candidate 必须在 selection 前分别拥有 immutable、candidate-specific 的 ControlManifest 和 oracle provenance；其中包含该 candidate 的 formula/period/population/unit、expected values、comparisons、tolerance、source 与 limitations。二者不能共用一个含混的 expected-value set。

当前两套 ADT candidate 共享同一套 case/question 与 outcome-category 定义（4 Answered + 1 Clarify + 3 Refused），因此 selection 前只冻结一个 truth-neutral `adt.tracer.v1.suite`。Suite 不存 candidate-specific numeric expected values/tolerance；这些只存在各自的 ControlManifest。若未来 candidate 连 case、question 或 expected outcome category 都不同，则不得冒用该 shared suite，必须先形成获批 Decision/new suite digest，再继续 selection。

每个 selectable candidate 必须形成 immutable `ReferenceCandidate`，精确绑定其 `reference_case_id`、ClearedInput、ControlManifest、shared SuiteManifest、oracle provenance、verification criteria、limitations 与 frozen time。两个 candidate 再由一个 immutable `ReferenceCandidateSet` 绑定；Stage 1 set denominator 恰为 2，candidate IDs 必须不同，二者必须引用同一 exact truth-neutral SuiteManifest。Candidate/set 都是 pre-selection evidence，不含 selected 状态、AuthorityDecision 或 ReferenceManifest。

没有以下四元身份的 candidate 不可被选择：

```text
cleared_input_id
+ cleared_input_digest
+ opaque approved locator
+ input disclosure approval ref
```

若选择 current synthetic，必须从需求/指标描述重新形成 safe-intake workbook/document；Ontology Operator 禁止读取现有 Package、oracle、fixture 或 expected runtime result 来冒充构建输入。

### 4.2 One reference identity

唯一被 commit、可进入 GSR 的 ReferenceManifest `/2` 必须绑定：

```text
reference_case_id
+ cleared_input_ref/digest
+ control_manifest_ref/digest
+ suite_manifest_ref/digest
+ oracle_provenance_ref/digest
+ selection_proposal_ref/digest
+ selection_authority_decision_ref/digest
```

Selection transaction 固定为：

```text
ReferenceCandidateSet
→ ReferenceSelectionProposal(candidate_set_ref + selected_candidate_ref
  + selected_reference_case_id + nullable reselection_transition_ref)
→ ReferenceSelectionAuthorityDecision/1(ALLOW, action exactly SELECT_REFERENCE)
  on exact proposal digest
→ ReferenceManifest/2 exact-matches selected candidate tuple and binds proposal + decision
→ registrar durable linearization
→ ReferenceSelectionCommitReceipt/1 binds set/proposal/decision/manifest,
  checked authority epoch/policy, sequence/time/journal digest and prior receipt/transition
→ GSRPublish/2 binds both the exact manifest and exact receipt
```

`SELECT_REFERENCE` 只存在于 action-exact `reference-selection-authority-decision-subject/1`，不得塞入 predecessor generic `authority-decision-subject/1` 的 action registry。它只授权给 pinned trust manifest 中已命名的 Reference Truth Owner。Studio Domain Owner、Fixture/Adapter Author、Independent Control Reviewer、Ontology Operator、caller-supplied role/admin label均不得授予该 action。DENY、expired/wrong-scope/wrong-purpose/wrong-trust-epoch decision产生 zero committed ReferenceManifest/receipt side effect。

每个 exact candidate set 只能 commit 一个 final ReferenceManifest。Logical `selection_commit_key` 是 `(canonical GovernanceScopeV1 bytes, candidate_set_ref.subject_digest)`；同一 series 另以 `(canonical GovernanceScopeV1 bytes, candidate_set_ref.object_id)` 做 predecessor CAS。Exact retry 必须先于 current-authority re-evaluation识别，并在 read authorization 允许时返回历史 immutable receipt；新 command 必须在 recovered state 的同一 linearization lock 内重新校验 current authority/trust epoch后才能 durable append。同 set 的不同 proposal、selected candidate、decision ref或final digest返回 `REFERENCE_SELECTION_CONFLICT`，loser side effect=0。

Receipt 中三个摘要不是调用方声明：`selection_key_digest` 由 exact Governance scope + candidate-set subject digest 推导；`request_identity_digest` 由 exact set/proposal/selection-decision/final-manifest refs 推导；`journal_record_digest` 由 receipt 的 closed logical committed fields（排除自身 digest 与通用 subject base）推导。三者均使用独立 domain separator，并由 verifier 独立重算。Selection Authority 的 policy refs 必须恰为当前 CandidateSet 的 singular `selection_policy_ref`，receipt snapshot 也必须正向等于它；不能把另一个仍支持 `SELECT_REFERENCE` 的历史 policy 连同 digests 一起换入。任何字段、ref、authority epoch/policy snapshot、predecessor、transition、sequence 或 commit time 改变，都必须产生对应的新摘要。

Selection/gate chronology 是 contract fact：`candidate_set.frozen_at <= selection_authority.issued_at <= reference_manifest.frozen_at <= receipt.committed_at <= semantic_content.built_at <= semantic_gate_evaluation.issued_at`，且 receipt commit 不晚于其余 gate evaluation。Binding/Data 与 Control gate 还要求 `data_identity.frozen_at <= gate_evaluation.issued_at`。GSRPublish 的 `semantic_schema_ref` 必须等于所引用 SemanticContentManifest 的 schema ref；后签的摘要不能为先签的 PASS 补造前提。

合法重选不能只改 set version/time。它必须创建新的 CandidateSet digest，并由 `ReferenceReselectionTransition/1` 绑定 immediately prior set/manifest/receipt、closed change reason 和至少一个 materially changed component；Proposal `/1` 必须在 Truth Owner 授权前绑定该 transition。Current 与 immediately-prior 两代都必须独立通过 member selection、case ID、selected tuple、authority、policy、receipt derivation 与 chronology 校验，不能把历史链当成不透明指针。Version/time-only、stale predecessor 与 sibling fork分别稳定拒绝；Manifest ID/version不能绕过。Final manifest不反向引用 receipt，因此无 digest cycle；receipt可引用 prior receipt。AuthorityDecision 已存在不等于 final manifest已提交。

冻结前 conformance 只证明固定、独立 expected 的 logical traces：invalid-first、exact retry before/after expiry、both conflict orders、authority expires while waiting、legal/new series、material-only successor、version/time-only、fork/stale predecessor，以及 `BEFORE_APPEND`、`MID_FRAME`、`AFTER_WRITE_PRE_SYNC`、`AFTER_SYNC_PRE_RESPONSE` 与 restart。真实 registrar、workers、file lock、framing、sync 与 fault injection 是 accepted S0 rebaseline 后的 V0b DoD，不得冒充 freeze 前 evidence。

只有 verified CommitReceipt 存在后才允许 Fixture/Adapter Author 构造 synthetic details。任何 constituent 改变产生新 ReferenceManifest digest。`GSRPublish/2` 同时直接绑定 singular selected manifest与receipt；其 typed `SemanticContentManifest/1` 也绑定同一 manifest。`decision_refs` 继续只承载已记录的 semantic Decisions，不得被 selection AuthorityDecision 代替。所有 GSR、payload、control、suite、oracle、evidence 与 demo label 必须正向等于同一 committed selected tuple；cross-artifact difference 必须为 0。

Selection 不修改或重算被选中的 ControlManifest/oracle provenance；它只把该 candidate 的 exact refs 指定为唯一 `control_manifest_ref` / `oracle_provenance_ref`。未选 candidate 的 artifacts 只保留为 selection audit evidence，禁止进入 selected GSR、runtime payload、Control gate、active API 或 demo truth。这样“选择前冻结、选择后唯一”同时成立。

### 4.3 Blind Ontology Operator

Ontology Operator 在 Candidate 冻结前：

- 只读取 selected ClearedInput；
- 不读取现有 Package、oracle、fixture、target values 或 runtime expected output；
- 留下输入清单和访问记录；
- 从 ClearedInput 形成 persisted Candidate、Trace、Gap、Conflict 与 Decision proposal。

这里的 independent 指 input isolation，不自动要求第三个自然人。若 operator 读到了禁止输入，该 run 不满足 tracer 的 intake claim，必须重建或降级说明。

## 5. Supported Product Flow

```text
Step 0  Truth/intake preregistration → action-exact SELECT_REFERENCE ALLOW
        → one-shot ReferenceManifest/2 + CommitReceipt/1
Step 1  Blind Candidate + complete trace + recorded Decisions
Step 2  SemanticContentManifest + GSR PublishSubject/2(manifest + receipt)
        → SemanticApproval PASS → immutable GSR
Step 3  Build immutable RuntimeSnapshotPayloadManifest
Step 4  Run four environment gates in non-business verification mode
Step 5  Select exact five PASS VerificationAttempts → seal VRS
Step 6  ACTIVATE eligibility + local AuthorityDecision + CAS ActivationRecord
Step 7  Normal Agent API runs the same frozen suite；每个 case 内部均执行 Step 8
Step 8  Per-execution: PRE_QUERY eligibility → deterministic analysis → RESULT_RELEASE commit
Step 9  VRS revoke proves no new query/no losing in-flight release
Step 10 UNKNOWN_CONCEPT boundary → disclosed safe SCR → Studio triage
```

Pre-activation verification 与 active Agent API 使用同一唯一 suite：`adt.tracer.v1.suite`。它由现有 8 cases 重编并冻结，不另建第二套 Golden truth：

- 4 `ANSWERED`；
- 1 `CLARIFY`；
- 3 `REFUSED`。

Case/question、expected outcome category 或 denominator 变化必须产生新 suite digest；candidate-specific numeric expected value、tolerance 或 comparison 变化必须产生新的 candidate ControlManifest digest。两者任一变化都会产生新 ReferenceManifest digest。

## 6. Supported Contract Surface

### 6.1 Objects and commands

Stage 1 必须实现：

- ClearedInput、typed OracleProvenance、ReferenceCandidate、ReferenceCandidateSet、ReferenceSelectionProposal、optional ReferenceReselectionTransition、ReferenceManifest/2、internal ReferenceSelectionCommitReceipt、SemanticContentManifest、GSR PublishSubject/2、GSR、RuntimeSnapshotPayloadManifest；
- five exact VerificationAttempts；
- VRS with `seal_status=SEALED` only；
- local AuthorityDecision + immutable internal PolicyDecision evidence；
- ActivationRecord / RevocationRecord；
- phase-specific ExecutionEligibilityDecision；
- ConceptResolutionEvidence、ExecutionEvidenceEnvelope/2、UserEvidenceProjection、ResultReleaseCommit；
- ProposedSCRPayload/2、PayloadDisclosureDecision、SCREnqueueProposal、UNKNOWN_CONCEPT SCR；
- RuntimePackageView façade。

Generic AuthorityDecision 支持 commands：APPROVE_CLEARED_INPUT、PUBLISH、ATTEST、SEAL、ACTIVATE、REVOKE_VRS、RESOLVE/PRE_QUERY、RESULT_RELEASE、EVIDENCE_READ、SCR_DISCLOSE、SCR_ENQUEUE、SCR_TRIAGE。`SELECT_REFERENCE` 只由独立 action-exact selection authority schema 表达。`DEACTIVATE` 是 Core 的永久 command，但本 Profile 不实现；要停止使用当前 VRS，Stage 1 通过 revoke 或激活另一份 eligible VRS 完成。

### 6.2 Local authority

Stage 1 contract evidence 使用 packet-pinned、closed `external-leaf-manifest/1`，区分 TrustedSession、PrincipalRegistry、Principal、RoleAssignment、StaticPolicy、Build/Schema、Evidence、SafeHandle 等 terminal variants；generic artifact auto-success 为 0。V0b 使用 read-only local registry adapter + deterministic evaluator。Trusted principal/session context 来自本地受控入口，不接受 request body/CLI role flag 自报。

每个 privileged action 的 AuthorityDecision 必须绑定 exact principal/trust epoch、scope、purpose、action、resource digest、policy refs、obligations 与 expiry。所有 UI/audit 明示 `simulated/local authority`；不得称 production IAM。

`SELECT_REFERENCE` 的 exact protected resource 是 immutable ReferenceSelectionProposal；scope=`GovernanceScopeV1`，purpose=`ontology-build`。Selection authority不得直接绑定 final ReferenceManifest，以保持无循环；final manifest反向引用 proposal + decision，receipt再引用 manifest。

### 6.3 VRS and eligibility

- VRS 只持久化 `SEALED`；
- ACTIVATE、PRE_QUERY、RESULT_RELEASE 各自新建 point-in-time EligibilityDecision；
- ACTIVATE 的 intent `requested_at` 必须不晚于其 EligibilityDecision `evaluated_at`，后者必须不晚于 ActivationRecord `committed_at` 且仍在 validity window 内；
- PRE_QUERY、RESULT_RELEASE、EVIDENCE_READ 的 `evaluated_at` 必须不早于其 exact `activation_head_ref.committed_at`，且该 activation record 的 ACTIVATE intent 必须指向同一 VRS；预先计算的 policy decision 不能替代已提交的 activation；
- decision 绑定 exact VRS/payload/attestation set、activation head、authority/policy、revocation epoch 与 reason；
- Governance、Runtime、Channel scopes 形成同一 tenant/workspace 下的前缀层级；任一 full-ref 的双方在共同出现的 tenant/workspace/environment/channel 坐标上必须相等，禁止跨坐标拼接一条表面可解析的链；
- VRS 可以保持 SEALED 而因 expiry/revoke/policy 变为 ineligible；
- UI 只能显示 “eligible at T under decision D”，不得显示 timeless READY authority。

本 revision 的 integrated active-trace evidence 还要求 authoritative side effects 为 exact-set：一个 active ActivationRecord、零 committed RevocationRecord、两个按 ChannelScope journal 顺序提交的 ResultReleaseCommit（ANSWERED 与安全 REFUSED projection）以及一个 UNKNOWN_CONCEPT SCR。额外 sibling/fork/duplicate record 即使自身 schema-valid，也不能被忽略后继续宣称该 trace 通过。

### 6.4 Activation

固定 scope/channel 使用 single-writer compare-and-append：

- command 带 expected head/epoch 与 opaque idempotency key；
- 本 integrated initial-activation trace 的 verified empty ledger 要求 `expected_head_ref=null`、`expected_activation_epoch=0`、record `sequence=1` / `activation_epoch=1` / `previous_record_ref=null`；
- current head 不等于 expected head → `CONFLICT`，不 append；
- same idempotency key + same command digest → 返回原 record；
- same key + different command digest → `IDEMPOTENCY_CONFLICT`；
- append 与 durable journal sync 成功后才报告 success；
- committed record 自身是 authoritative lifecycle audit fact；`latest` 只能是可重建 cache。

Future-dated activation 不支持；`effective_at` 只允许 now-equivalent value。

### 6.5 Revocation

Stage 1 仅支持：

| Dimension | Supported value |
|---|---|
| target | exact scoped VRS digest |
| enforcement | `BLOCK_NEW_AND_RESULT_RELEASE` |
| lookup | synchronous local journal, no cache |
| check points | PRE_QUERY and inside RESULT_RELEASE commit |
| recovery | new corrected VRS + new Activation |

Component/GSR/attestation target、content-global target、other enforcement、cache TTL 与 distributed propagation 均返回 unsupported/fail closed。

Activation append、VRS revoke 与 ResultReleaseCommit 在同一 exact ChannelScope local order/lock domain 排序：revoke first → no bytes；new activation first → an in-flight execution pinned to the old activation head cannot commit；release commit first → exact committed projection may be sent，later revoke/activation affects only uncommitted work。不存在 UNREVOKE，revoked VRS 不能作为 rollback/fallback target。

### 6.6 Result release

Stage 1 禁止 streaming，使用 private response buffer：

```text
execute
→ typed facts/claims
→ exact allowlisted UserEvidenceProjection
→ stage + durably persist evidence
→ final eligibility/policy/revoke check under release lock
→ append + durably persist ResultReleaseCommit
→ send committed projection bytes
```

Evidence staging、final decision、journal append 或 durability 任一失败，answer bytes 必须为 0。Clarify/Refuse 也先持久化最小 envelope/release decision，并证明 Query Engine access count = 0。

## 7. RuntimePackageView and Projections

现有 OntologyPackage 只作为 migration/build source。Planner/compiler/calculator 的 conformant path 只接收 RuntimePackageView；calculator、SQL compiler 和 formula evaluator 不重写。

RuntimePackageView 可包含：

- approved executable metric/entity/relationship semantics；
- supported analysis patterns/operator contracts；
- compiler/query 所需且已批准的 binding handles；
- approved runtime policy inputs；
- exact capability/profile refs。

不可包含：ClearedInput/source text、draft、review comment、approval rationale、unrestricted physical schema、SQL、credential、outbox content。

User Evidence Projection 使用 typed allowlist DTO。普通 `/api/analyze` 与 `/api/executions/{id}` 中以下 key/value/token 命中必须为 0：

- table、column、join、source locator、internal mapping ID；
- SQL、params、raw row；
- file path、stack、prompt、comment、secret/canary。

不能通过清空 evidence 作弊。每个 ANSWERED response 至少包含 safe claim refs、metric semantic ID、VRS identity、safe DataIdentity、policy/evidence ref 与 render identity。

当前 ordinary evidence-audit 已复现 `trade_fact`、`executed_value_hkd_mn` 与 internal mapping IDs 泄露；该问题是 external demo 前 P0。

## 8. DataIdentity and Evidence Replay

Stage 1 DataIdentity 至少绑定：

- synthetic dataset/manifest ref and digest；
- schema digest、row count/partition identity；
- captured/frozen time；
- source/query-engine identity；
- applied transformation and policy scope；
- replay level `evidence_only`。

Execution evidence 至少绑定 GSR/VRS/Activation、Eligibility、DataIdentity、policy、plan/query/operator、Facts/Claims、exact sanitized projection bytes/digest、renderer build、locale/timezone、unit/rounding profile。为避免 digest cycle，evidence 不引用 ResultReleaseCommit；ResultReleaseCommit 反向绑定 exact evidence + projection。`ANSWER_CANDIDATE` 只有被有效 commit 引用后，外部 outcome 才是 `ANSWERED`。

Evidence replay 只重放已保存的 exact sanitized projection。它不重新查询 current/historical data，也不声称可复现一个已不存在的 source state。

## 9. UNKNOWN_CONCEPT SCR

Stage 1 只支持 `UNKNOWN_CONCEPT`。其他 request types 返回 `SCR_TYPE_UNSUPPORTED`，不得转成 free text。

唯一支持的 source boundary mapping 是：

```text
known semantic area
+ well-formed term
+ allowed alias resolution completed
+ zero semantic binding
→ immutable ConceptResolutionEvidence/1
  (known registry/profile + safe alias + resolver build + completed + binding_count=0
   + exact PRE_QUERY Eligibility ALLOW + PolicyDecision ALLOW + query access 0)
→ ExecutionEvidence/2
  (candidate_status=REFUSED + boundary_code=CONCEPT_NOT_BOUND
   + query_engine_access_count=0 + exact concept evidence ref)
→ ResultReleaseCommit/1 for the safe refusal projection
→ UnknownConceptPayload/2 binds both boundary execution and release commit
→ optional UNKNOWN_CONCEPT feedback side effect
```

`CONCEPT_NOT_BOUND` 不能用于 missing parameter、role/policy denial、contract/integrity/activation failure或execution failure。`MISSING_PERIOD → CLARIFY`；`UNSUPPORTED_PREDICTION/RAW_DETAIL_DENIED/ROLE_DENIED/CONCEPT_NOT_BOUND → REFUSED`；precondition/execution failures保持各自 top-level outcome。`DISCLOSURE_BLOCKED`、disclosure DENY或outbox failure只表示 SCR `NOT_CREATED`，不能改写已持久化的 `REFUSED`。现有 `adt.tracer.v1.suite` 仍只使用原四个 boundary codes，8-case/4+1+3 denominator不变；`CONCEPT_NOT_BOUND` 只出现在独立 V4 boundary/conformance fixtures。

Closed ProposedSCRPayload 可含：

- disclosure-cleared `safe_term_alias`；
- `semantic_area_code`、`reason_code`；
- safe scenario/context codes；
- `safe_detail_artifact_ref`；
- opaque scope-bound `interaction_handle`；
- full scoped boundary execution、boundary release commit、GSR/VRS refs；
- `requested_action_code`（REVIEW / CLARIFY_DEFINITION / ADD_ALIAS）。

PayloadDisclosureEvaluation 必须直接绑定 proposed payload digest、safe-detail digest、source/destination scope、requester、Studio audience/queue、purpose、classification、allowed fields、policy、obligations 与 expiry；PayloadDisclosureDecision 绑定该 exact evaluation 与其 AuthorityDecision，从而传递性地固定这些 inputs。批准后改 payload 必须拒绝 enqueue。

Disclosure ALLOW 后，系统建立不含 authority ref 的 SCREnqueueProposal（绑定 exact payload、disclosure decision、idempotency、limitations 与 requested enqueue time）；`SCR_ENQUEUE` AuthorityDecision 绑定该 proposal digest；final SCR 再引用 proposal + authority decision。任何一步都不得把 final SCR 自己放进自己的授权前像。

禁止 raw question/term、answer values、裸 SHA-256 question hash、SQL、table/column、prompt、stack、path、attachment 或 unrestricted free text。Safe alias/interaction/detail handle 必须解析到 pinned `SAFE_HANDLE` leaf，且其 facts 明示 `raw_value_present=false`。

无法合法形成足够上下文时返回 `DISCLOSURE_BLOCKED`，不创建 SCR。五个 frozen UNKNOWN_CONCEPT fixtures 必须在不看原问题的情况下，让授权 triager 在两分钟内正确选择 owner + disposition，5/5 actionable 且 leakage = 0。

Studio triage 只可：TRIAGED → ACCEPTED / REJECTED / DUPLICATE / NEEDS_CONTEXT → CLOSED。`ACCEPTED` 不能自动创建 confirmed object、Claim、GSR 或 publish action。

## 10. Required Roles and Entry Gate

| Role | Stage 1 requirement | Must be named before | Combination rule |
|---|---|---|---|
| Product & Delivery DRI | named | S0 | owns scope/ROM/demo outcome |
| Shared Contract Owner / implementation DRI | named | S0 | owns profile/schema/adapter/ledger realization |
| Studio Domain Owner | named | V0 | accountable for V0 truth/intake/blind rebuild work package；cannot claim customer confirmation |
| Agent Domain Owner | named | V1 | may also be Runtime Capability Owner |
| Ontology Operator | named | V0 | blind-input restriction mandatory |
| Reference Truth Owner | natural person A | V0 | sole `SELECT_REFERENCE` authority；must differ from Reviewer |
| Fixture & Adapter Author | named | V0 | cannot be Reviewer；may be Truth Owner with downgraded claim |
| Independent Control Reviewer | natural person B | V0 | cannot be Truth Owner or Fixture Author |
| Disclosure & Policy Approver | simulated allowed | V0 | signs ClearedInput；not production/customer approval |
| Domain Approver | simulated allowed | V0 | Semantic Approval；not customer validation |
| Data Approver | simulated allowed | V1 | Binding/Data gate |
| Runtime Capability Owner | simulated allowed | V1 | may be Agent Domain Owner |
| Release & Activation Manager | simulated allowed | V1 | explicit principal；owns publish/seal/activation/revoke run |

五类 gate 不要求五个自然人。除 truth/control minimum 外，同一自然人可以切换 simulated principals 来证明 workflow enforcement，但必须留下 distinct AuthorityDecisions/audit records，不能借角色名伪造生产职责分离。

Entry chain is normative：

```text
Core + Profile Approved/Frozen
+ Decision Owner accepts this Profile direction
├─ + named Shared Contract Owner/implementation DRI
│  + named Product & Delivery DRI
│  → S0 may start
└─ + all V0 roles named
   → V0a read-only preregistration/intake preparation may start

Product & Delivery DRI prepares S0 re-estimate
+ Decision Owner accepts the parent ROM rebaseline in a separate record
+ V0a complete
→ V0b registrar/build/fixture code may start

V0b DoD complete
+ every §10 role required by V1 named
→ V1 may start
```

后续 slice owner 必须在对应 slice 开始前 named。五类 gate 不要求五个自然人，但 simulated principal 和 AuthorityDecision 仍需 distinct、可审计。

## 11. Conformance and Exit Gates

### 11.1 Existing baseline preserved

- current 33 automated tests：33/33 green；
- current 33 validation checks：33/33 green；
- frozen predecessor conformance vectors：34 positive + 30 negative remain green；
- core@1.1 conformance evidence：42 product schemas + 1 conformance-only schema represented by 43 positive subjects + 52 focused/legacy parser negatives；659 exact field rules；33/33 cross-object rules each bind one passing assertion + one killed semantic mutation；1,800 field/schema mutations with accepted-invalid=0；102 fully resolved integrated subjects + 12 normal assertions；120 rehashed-DAG mutations across 10 categories；16 fixed logical transaction traces；
- ref closure：545 integrated full-ref occurrences = 254 checked product refs + 291 exact pinned external refs；156 closed external entries；generic artifact auto-success=0；critical unresolved=0；
- frozen `adt.tracer.v1.suite`：8/8 in pre-seal verification and active normal API；
- status、Facts、Claims 和 safe evidence identity 双路径一致；
- current deterministic arithmetic path 不因合同迁移改变。

### 11.2 Contract acceptance

| Family | Minimum acceptance |
|---|---|
| Identity | pinned machine contract 是唯一 core@1.1 primitive/field/type/null/container/enum/scope/ref-target/compatibility source；42/42 product schemas + 1/1 conformance-only schema positive；每字段 remove + wrong-type、每 enum/ref mutation覆盖；accepted-invalid=0；old/new/mixed/relabel fail closed |
| Ref/trust closure | checked subject或exact pinned discriminated leaf二选一；generic shortcut=0；session/principal/registry/role/policy relationship、scope/epoch/time/action/purpose全部 join；forged/substituted root blocks |
| Truth/intake | two constructed-synthetic candidate tuples + one candidate set；Truth Owner-only action-exact selection；manifest+receipt；same-set one-shot与same-series material-only successor；16/16 logical traces；one committed reference identity across downstream artifacts；blind trace completeness 100%；at least one Missing/Withheld fail closed and one ambiguity resolved by Decision |
| Gates | five gates的 omit/FAIL/expire/wrong-authority/resource/scope/epoch/limitation各自阻断；ATTEST DENY阻断；reuse matches matrix；explicit attempt-target revoke 不属于 Stage 1 |
| Seal | payload has no attempts；VRS binds exact payload + exact five PASS refs；no durable READY |
| Authority | caller-supplied principal/role/scope never grants action；privileged actions all bind valid decisions |
| Activation | stale head/idempotency conflict/fork/gap/corrupt tail fail closed；same-head race exactly one successor |
| Revocation | pre-query revoke → Query Engine call 0；revoke-before-release → answer bytes 0；no un-revoke/rollback |
| Release | evidence/audit/fsync/final-decision fault → answer bytes 0；only committed bytes replayable |
| Projection | forbidden key/value/secret canary leakage 0；safe evidence required fields non-empty |
| Runtime | 8 cases dual-path parity；all numeric/direction/ranking/limitation direct Claim coverage 100% |
| SCR | immutable ConceptResolutionEvidence → ExecutionEvidence/2 → ResultReleaseCommit → Payload/2 exact chain；`REFUSED/CONCEPT_NOT_BOUND/query_count=0`；5/5 actionable；payload-bound disclosure；idempotent；unreleased/contradictory/role-policy-denied source产生 zero SCR；forbidden-field leakage 0；feedback failure不改outcome；no auto truth |
| Audit/recovery | publish/seal/activate/revoke/execute/release/SCR/triage complete；chain/tail mutation detected；refresh retains state |
| Claim wording | oracle class/limitations visible；no customer validation or production claim |

Correctness reporting 必须分报：supported-answer correctness、coverage、Clarify、Refuse、unsupported/failed、Claim coverage、mutation kill rate、projection leakage。不得通过删除 frozen cases 改善指标。

## 12. Delivery Slices and ROM

### V0 — Truth/intake and blind rebuild（3–5 pd；V0a/V0b combined）

Owner：Studio Domain Owner。Required participants：Ontology Operator、Reference Truth Owner、Fixture & Adapter Author、Independent Control Reviewer、Domain Approver、Disclosure & Policy Approver。

输出：

- two ADT truth candidates separately registered with verification criteria；
- one approved non-Package/non-oracle ClearedInput per selectable candidate；
- candidate-specific ControlManifest/oracle provenance plus one shared truth-neutral SuiteManifest；
- two immutable ReferenceCandidate subjects + one two-member ReferenceCandidateSet；
- V0a（freeze 后可与 S0 并行）：read-only preregistration、ClearedInput preparation、two-candidate/control/suite preparation；不得创建被称为 authoritative registrar behavior，不得让 Fixture Author看到 selected control target；
- V0b（仅在 S0 rebaseline 被 Decision Owner 接受后）：Shared Contract implementation DRI 实现 local registrar/read-only trust adapter/framed journal；Reference Truth Owner exact proposal + action-exact `SELECT_REFERENCE` ALLOW + one-shot ReferenceManifest/receipt；100 real same-key worker trials与 fault-injected write/sync/restart evidence；
- blind Operator produces persisted Candidate、100% answer-dependency Trace、Gap/Conflict and recorded Decision；
- at least one Missing/Withheld path fails closed and one genuine ambiguity is resolved；
- produces immutable GSR PublishSubject and exact-subject Semantic Approval PASS，ready for V1 publication；
- only after verified CommitReceipt，Fixture/Adapter Author may construct/adapt runtime fixture。

V0 includes internal product/engineering effort for the synthetic ADT truth gate and second-person review。It excludes client/External Reviewer waiting and any real customer truth validation。

### S0 — Change-map / safety spike（1–2 pd）

输出：

- planner/compiler/calculator/validator/publisher 的 OntologyPackage field-access map；
- RuntimePackageView field partition 与 adapter seam；
- 所有 response serialization path 和 current leak reproduction；
- Stage 1 subject/gate/ledger transaction map；machine-contract/toolchain/reuse seam；不把 logical trace伪称为 file-journal implementation；
- 33/33 automated tests + 33/33 validation checks green；
- Product & Delivery DRI 编制 full Stage 1 重估；Decision Owner 在独立记录中接受或拒绝重基线。

### V1 — Governed shadow publish → same ADT answer（3–4 pd）

GSR 必须来自完整的 blind ClearedInput → Candidate/Trace → Decision → Semantic Approval 流程。Legacy Package 只能在隔离的 runtime migration adapter 中作为 payload/RuntimePackageView 的 shadow build source，禁止直接生成或替代 Candidate、Decision、Semantic Approval 或 GSR。V1 取得 PUBLISH AuthorityDecision 并发布 GSR，随后产生 payload 与四份新的 environment VerificationAttempts；它们连同 V0 已冻结的 exact Semantic Approval attempt 组成唯一 five-ref seal set，再密封 SEALED VRS。RuntimePackageView 驱动 existing calculator；legacy resolver 仍 active，仅做 shadow compare。

DoD：V0 GSR PublishSubject/Reference identity is the only semantic input；8/8 parity；gate subject mutation；runtime view 无 governance attachment；33/33 automated tests + 33/33 validation checks green。

### V2 — Authorized activate → analyze → revoke → no release（3–4 pd）

Local AuthorityDecision、CAS Activation/Revocation journal、dynamic Eligibility、pre-query/release checks、Evidence + ResultReleaseCommit。

DoD：unauthorized/wrong-scope/wrong-head fail；same-head race one winner；revoke/persist fault tests；outcome envelope 可查。

### V3 — Internal safe evidence API and console integration（2–3 pd）

Behind the contract feature flag，ordinary test user 通过真实 analyze/evidence API 获取 useful allowlisted evidence；console internal integration 使用该 API。V3 完成不构成 external demo permission，legacy resolver 仍可作为 non-governed authority until V5。

DoD：8 cases + evidence-audit forbidden tokens 0；safe evidence non-empty；snapshot/answer identity visible。

### V4 — UNKNOWN_CONCEPT → safe SCR → triage（2–3 pd）

Boundary envelope、safe detail、payload disclosure、outbox 与 human triage 全链。

DoD：5/5 actionable；payload mutation rejected；no safe context → DISCLOSURE_BLOCKED；leakage 0。

### V5 — Cutover, critical conformance and fallback（2–3 pd）

Contract resolver 成为 authority；critical mutation/fault suite 与 runbook 通过。

DoD：clean-state publish → seal → activate → analyze → evidence → revoke；8-case dual path diff 0；33/33 automated tests + 33/33 validation checks；critical fault/mutation suite 100%；contract resolver is governed-route authority；console cut to live allowlisted governed API；no eligible VRS 时 readiness fails；legacy fallback 不得运行 revoked digest。

### 12.1 Dependency DAG

```text
Core + Profile Approved/Frozen
  ├→ named S0 owners → S0 → DRI re-estimate → Decision Owner accept/reject
  └→ named V0 roles → V0a read-only preparation

S0 rebaseline accepted by Decision Owner + V0a complete
  → V0b registrar/build/fault evidence

V0b complete + all V1 roles named
  → V1 → V2 → V3 ─┐
              └→ V4 ─┴→ V5 → external demo go/no-go
```

V3 and V4 may run in parallel after V2 when separate owners are available；V5 depends on both。V3's console is internal/behind-flag；external governed-evidence demo is prohibited before V5。

### 12.2 Planning range

| Work | ROM |
|---|---:|
| V0 truth/intake/blind rebuild | 3–5 pd |
| S0 | 1–2 pd |
| V1–V5 | 12–17 pd |
| Contract mechanics subtotal（S0 + V1–V5） | **13–19 pd** |
| Full Stage 1（V0 + contract mechanics） | **16–24 person-days ROM** |

Range bridge：`13–19` 只覆盖 contract mechanics；`3–5` 覆盖 synthetic truth/intake/blind rebuild。按 low/low 与 high/high 配对形成父级唯一 full Stage 1 range `16–24`，不是再把 13–19 加到 16–24 上。置信度：spike 前 low；S0 后对 V0 和所有 mechanics slices 重新给 best/likely/worst，重新基线父级 16–24。

ROM 不含新的真实 customer fixture、External Reviewer 人工转写等待、真实网络/DB/IAM/K8s、第二场景、production UI、independent security assessment 或客户业务 truth review。

触发重估：RuntimePackageView/evidence DTO 不是 shallow adapter；console 不能复用；加入 multiwriter/DB/IAM；需要 component transitive revoke；新增 SCR type；换/新增 runtime adapter；重造 fixture；接真实环境/材料。

## 13. Explicit Out of Scope

1. customer 原始材料、真实业务正确性或生产适用性证明；
2. production IAM/SSO/MFA、KMS/PKI、真实职责分离；
3. multi-tenant/multi-workspace service、multiwriter/distributed ledger、HA；
4. component/GSR/attestation target or transitive revoke、three enforcement modes、cache freshness；
5. streaming result release；
6. UNKNOWN_CONCEPT 之外的 SCR 和 complete incident/product-feedback lifecycle；
7. arbitrary metric/SQL/operator、generic ontology compiler、second scenario；
8. historical data re-execution、production audit retention/legal hold；
9. full Studio authoring UI、External Reviewer portal、自动抽取真实文档；
10. real Query Engine/network、Linux ARM64/K8s delivery；
11. Knowledge Center 与 commercial packaging。

## 14. Rollout and Fallback

1. exact atomic freeze pins Core、Annex、machine contract、external-leaf manifest、vectors、generator/verifier、coverage report 与 compatibility hashes；
2. S0 freezes change/field/trust/transaction/leak maps、contract test-harness design and accepted rebaseline；these are not runtime data/control fixtures；
3. V0b verified receipt 之前，runtime fixture authoring保持 blocked；
4. behind `shared_contract_v01`, dual-publish legacy + shadow contract artifacts；
5. shadow-run frozen suite without changing user path；
6. activate contract resolver only after V1–V4 DoD；
7. run clean-state and physical fault/mutation suite；
8. cut console to live allowlisted API；
9. governed Agent API 在 inactive/ineligible/expired/policy-denied/no-VRS 时始终 fail closed，绝不自动 fallback；legacy serving 只可经独立显式 demo route/flag 使用，并明确标为 non-conformant synthetic demo；
10. revoked digest is never a fallback target；
11. remove legacy `latest` authority after conformance pass。

Go/no-go：

- Contract docs may become Reviewed Candidate only after Annex and fresh-reader pass；
- S0 begins only through the §10 named-owner/approval entry chain；
- V1 begins only after Product & Delivery DRI records the S0 re-estimate、Decision Owner accepts the rebaseline in a separate record、V0a/V0b complete and all V1 roles named；
- external governed-evidence demo requires V0 + V1–V5 DoD all PASS，contract resolver and live console governed route cut over，33/33 tests + 33/33 checks + frozen suite + critical fault/mutation suite PASS，physical-binding/secret leakage = 0，persist/revoke-before-commit answer bytes = 0，oracle limitation/claim label visible，and Product & Delivery DRI records GO；
- production/customer claims require separate evidence and are outside this profile。
