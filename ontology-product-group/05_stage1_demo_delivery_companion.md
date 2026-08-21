# Stage 1 Demo & Delivery Companion v0.1

Document ID：`stage1-demo-delivery-companion/0.1`  
状态：Revised Candidate；Pending Fresh-reader Closure；not approval authority  
日期：2026-08-19  
Decision Owner：Muyu  
Accountable Owner：Product & Delivery DRI  
适用产品：Ontology Studio + Ontology Analytic Agent  
当前冻结基线：`synthetic-trusted-flow/core@1`  
待决 Profile revision：`synthetic-trusted-flow/core@1.1` Revision Pack R-01（E-01 `CONCEPT_NOT_BOUND` + E-02 `SELECT_REFERENCE`）  
当前阻断：R-01 未批准/实现/独立验证前，V0 reference-selection conformance、V4 conformance、Delivery Readiness PASS 与 external demo GO 均禁止。

## 0. 文档性质与优先级

这是一份两产品共同引用的 Stage 1 产品演示与交付附件。它用于冻结客户价值叙事、最小产品表面、slice accountability、proxy tests 和 external-demo readiness evidence。

它不是第三个产品、Shared Kernel 合同、runtime authority、技术方案或部署设计。发生冲突时：Shared Product Contract > Synthetic Profile > 两份 Product-Domain PRD > 本附件。它不能降低 V0 + V1–V5 的唯一 external demo gate。

本文生命周期固定为 `Draft → Revised Candidate → Reviewed Candidate → Approved/Frozen → Superseded`。当前仅为 Revised Candidate；只有 Decision Owner 对两份 PRD 与本附件 exact revision/digest 的原子批准记录，才能使三者一起成为 Approved/Frozen。Product & Delivery DRI 维护内容并对交付结果负责，但不能自批或改变冻结边界。

## 1. Stage 1 Promise

### 1.1 Audience and decision enabled

Primary audience：评估是否值得继续投入 bounded client-specific discovery 的 HKEX/Deloitte business、analytics、data 和 governance stakeholders。

Stage 1 只支持以下决定：

> 这条 constructed-synthetic evidence 是否足以支持进入一个真实客户场景的受控 discovery 与 PoC 设计？

Stage 1 不支持采购、production deployment、HKEX ADT business validation、production security approval 或 general ontology platform decision。

### 1.2 Hero flow

> **Revision blocker：** 下列 `REFUSED/CONCEPT_NOT_BOUND` 与 UNKNOWN_CONCEPT 链是 R-01/E-01 的 `core@1.1` candidate 行为，不受当前 `core@1` 支持；E-01 未批准且新 Profile/Annex/vectors 未独立通过前，V4 与 external demo 必须保持 NO-GO。Reference selection 同时依赖 R-01/E-02。

```text
safe synthetic intake
→ one visible Missing/Gap + human Decision
→ exact Semantic Approval + GSR receipt
→ Q3/Q4 ADT fact and comparison
→ leading-segment contribution + non-causal decomposition
→ safe evidence and byte-identical replay
→ one CLARIFY and one REFUSED boundary example
→ one REFUSED/CONCEPT_NOT_BOUND feedback submission
→ safe UNKNOWN_CONCEPT SCR triage
```

Presenter 必须明确：“driver/为什么”在本 Stage 只表示按获批规则计算的 contribution/decomposition，不表示因果推断。

### 1.3 Claim ceiling

以下 limitation 必须邻接 primary scenario/result identity，并在 main view、replay、export 和 runbook 中无需 hover/展开即可看到：

> Constructed-synthetic reference case; simulated/local roles and controls; not HKEX business validation; not production-ready.

不得把 SCR `ACCEPTED` 描述为自动学习、Ontology 已更新或新能力已生效。没有新的人工 Decision、GSR、VRS 和 Activation，同一问题保持原 boundary outcome。

## 2. Minimum Demonstrable Product Surface

所有任务必须使用真实持久状态和获准 command path，refresh 后保留；不得靠浏览器 mock 或直接编辑 authoritative files 伪造完成。Presenter assistance 允许，production-grade workflow UI 不要求。

| # | User task | Minimum Stage 1 surface | Slice | Acceptance |
|---|---|---|---|---|
| 1 | Register/open synthetic cleared intake | controlled CLI/API/internal form；显示 metadata、safe artifact ref、Missing/Withheld/Unconfirmed | V0 | raw/restricted content 不进入 ordinary Studio/Candidate/model/log；receipt persistent |
| 2 | Inspect Candidate Trace/Gap and record one Decision | existing shell thin live view or generated governed artifact view + controlled decision command | V0 | trace denominator/Gap/Decision来自 persisted state；refresh retained |
| 3 | Approve exact semantic subject and publish GSR | controlled CLI/API/internal operator view；显示 Semantic PASS、PUBLISH receipt、GSR identity | V0/V1 | wrong subject/principal fails；无 direct file edit |
| 4 | Ask ADT question and inspect/replay safe evidence | live governed Agent API + existing console shell | V3 | committed answer/evidence；exact authorized replay；no physical leakage |
| 5 | Open and triage one UNKNOWN_CONCEPT SCR | live minimal Change Inbox/internal view | V4 | 仅在 R-01/E-01 获批并形成独立验证的 exact Profile/Annex/vectors 后执行；complete valid chain；persisted append-only disposition；no auto truth |

Backstage but repeatable evidence may use controlled CLI/API/internal artifact view：truth preregistration/selection、blind access proof、four environment gates、exact five-ref seal、activate/revoke、failure/mutation/recovery suite 和 readiness checklist。

若 S0 证明现有 shell/API 不是 shallow adapter，Product & Delivery DRI 必须重估 full Stage 1 baseline，由 Decision Owner 接受或拒绝；两者必须形成不同记录。不得用截图、mock 或删减 truth/release/projection gates 来维持 `16–24 pd`。

## 3. Runtime Release Operations — Product Task

Runtime Release Operations 属于 Agent Product Domain 的 operator job；它不把 truth、gate verdict、seal/activation command authority 转给 Agent Domain Owner。

Release & Activation Manager 必须能通过 controlled CLI/API/internal view：

1. 接收 exact authorized GSR 与 environment component refs；
2. 查看 derived verification progress 和 stable failure owner；
3. 显式选择 exact five PASS attempts，不自动选择 latest；
4. 请求 seal、activate、revoke；
5. 获取 authoritative receipt 或 stable fail-closed result。

Studio Domain Owner 仍拥有 GSR product outcome；gate authorities仍分别拥有 PASS/FAIL；Release & Activation Manager 持有 privileged command authority；Shared Contract Owner 实现合同 substrate；Agent Domain Owner 对这个 operator task 的产品结果负责。

## 4. Canonical Slice Accountability

“Accountable for slice DoD”不等于 command/gate authority，也不允许自批。每个角色必须在相应 slice 开始前落实人名。

| Slice | Single accountable role | Retained authorities / contributors |
|---|---|---|
| S0 | Shared Contract Owner / implementation DRI | Product & Delivery DRI编制重估；Decision Owner接受/拒绝重基线；Studio/Agent owners提供field/surface map |
| V0 | Studio Domain Owner | Reference Truth Owner selects；Operator blind-builds；Domain/Disclosure authorities decide；Control Reviewer保持独立 |
| V1 | Agent Domain Owner | Studio owns exact GSR sub-outcome；five gate authorities、sealer、Release Manager保留各自authority |
| V2 | Agent Domain Owner | Release & Activation Manager commands；Shared Contract Owner提供authority/ordering substrate |
| V3 | Agent Domain Owner | governed API/console/evidence contributors；Disclosure/Policy boundary不变 |
| V4 | Studio Domain Owner | Agent Domain Owner负责safe boundary/outbox contribution；Disclosure/Enqueue/Triage authorities distinct |
| V5 | Product & Delivery DRI | Studio/Agent/Shared owners关闭各自DoD；DRI独自拥有external demo GO/no-go |

### 4.1 Inherited action/outcome traceability

完整 action 列表继承 Synthetic Profile，不在产品文档复制 schema。S0 必须为每个 supported action 形成一行 traceability：

```text
action
+ user/product outcome owner
+ command/gate authority
+ authoritative committed fact
+ inherited conformance family
+ fail-closed result
+ incident/failure owner
```

缺少任一行时，privileged-action audit completeness 不能报告 100%。Shared Kernel/platform team 不能作为用户产品 accountable owner。

## 5. Product Metrics Event Dictionary

两产品只使用 Product Strategy 定义的 Product-family North-star：

- `Time to First Trusted Scenario`：从第一份 ClearedInput 正式登记，到预登记 must-answer suite 全部达到可信门禁；
- `Trusted Scenario Completion Rate`：所有进入 intake 的场景，在约定周期内完成上述门禁的比例。

所有正式进入 intake 的 scenario 都留在固定分母，不得 post-run 删除或重标。共同 event schema 使用三个正交字段，避免把 intake condition、完成状态和失败原因混为一类：

| Axis | Closed values | Rule |
|---|---|---|
| `completion_state` | `TRUSTED_COMPLETED` / `NOT_COMPLETED` | 只有 must-answer suite 全部通过 trust gates 才是 `TRUSTED_COMPLETED`；它是 numerator 状态，不是父级 exclusion category |
| `strategy_reporting_category` | `SCOPE_CHANGE`、`PAUSED`、`FAILED`、`UNSUPPORTED`、`CLARIFY`、`REFUSE` | 精确保留 Strategy §2.2 的六项固定报告类别；对 `NOT_COMPLETED` 必填且只能一项；未知值 fail closed |
| `intake_condition_flags` | `MISSING`、`WITHHELD`、`UNCONFIRMED` | 可与前两轴共存，不是可从分母删除的类别；例如因 Withheld 暂停时记录 `NOT_COMPLETED + PAUSED + WITHHELD`，不得静默改成 completed/failed |

Scenario-level `CLARIFY` / `REFUSE` 是未完成原因；它们不等于 suite 内单个 expected analytic outcome。一个含预期 CLARIFY/REFUSED cases 且整套门禁全部通过的 scenario 仍可为 `TRUSTED_COMPLETED`。

Effort/wait 使用同一 closed duration schema：

| Field | Type / unit | Rule |
|---|---|---|
| `measurement_cutoff_at` | UTC millisecond timestamp | 未完成 scenario 的 wall-clock stop；不得早于 `intake_registered_at` |
| `internal_active_minutes` | non-negative safe integer / minute | 我方 active effort；required，explicit `0` 表示已记录为零，null/missing不等于零 |
| `deloitte_active_minutes` | non-negative safe integer / minute | Deloitte active effort；required，规则同上 |
| `client_confirmation_wait_minutes` | non-negative safe integer / minute | client confirmation wait；required，规则同上 |

`duration_unit` 固定为 `MINUTE`；其他值、负数、missing/null 均 fail closed。每个 scenario 的 wall-clock elapsed = `intake_registered_at` 到 `trusted_at`（已完成）或 `measurement_cutoff_at`（未完成）的 calendar minutes。Product-family effort/wait 对固定分母逐项求和；person-hours/hours 只由 exact minutes ÷ 60 派生，以 decimal scale 2、HALF_UP 显示，不得反向覆盖 minutes。`Time to First Trusted Scenario` 从分母中最早 intake 到最早 trusted stop；尚无 trusted scenario 时 duration 为 null并明确 `NOT_YET_TRUSTED`，不能填零。

共同 normative product-reporting fixture 是 `fixtures/product-family-metric-events-v0.1.json`（fixture ID `product-family-metric-events-v0.1`；file digest `sha-256:3fe4e5b36f8f7f019faaac17b7b7ff65e08a2a108960f05991bd7a04ae08676d`）。它只用于三方 calculator 一致性，不是 Core/runtime authority；任何变更必须产生新 fixture version/digest并由三方同时采用。

以下只能作为 subordinate milestones，不能结束 North-star：

- Time from Activated VRS to First Committed Answer；
- Time to First Safe SCR；
- Time to First Revoke Proof。

Closure test：Studio、Agent 和 Product-family calculator 使用同一 event log 与同一 versioned event fixture，start、stop、wall-clock、三项 minute totals/derived hours、completion state、denominator、六类 counts 与 intake flags 必须完全一致；fixture 至少覆盖 completed、clarify、refuse、withheld、failed、unsupported、paused 与 scope-change，duration含非零和显式零。未知类别/unit、missing/null/negative duration 必须 fail closed；缺少任一 frozen suite result 时 North-star 不完成。

## 6. Non-gameable Acceptance Inventories

不新增三个 Product Domain manifests；复用冻结 identity chain：

| Acceptance inventory | Existing binding | Minimum contents |
|---|---|---|
| Semantic-slot / trace denominator | preregistered versioned `semantic_validation_profile_ref` used by exact Semantic gate；source slots derived from selected cleared safe artifact + suite | formula、grain/additivity、period/calendar、population/exclusions、dimensions/segments、unit/scale/rounding、limitations、release-impacting Missing/Withheld/Decision |
| Required Answered outputs / Claims | ControlManifest `expected_result_refs` and limitations | top-line、comparison、contribution/decomposition、ranking where applicable、limitations；candidate-specific expected values/tolerance separate |
| Business cases and ADT mutations | SuiteManifest case refs + `mutation_profile_ref` | frozen 8-case denominator；current seven mutations + datetime fail-closed + duplicate fact grain + zero/missing trading-day denominator |
| UNKNOWN_CONCEPT triage protocol | versioned conformance fixture/protocol pinned by Delivery Readiness manifest | five non-constant actionable fixtures、blind labels、owner/disposition expectation、safe context、zero forbidden fields |
| Critical fault/release tests | versioned conformance inventory pinned by Delivery Readiness manifest | exact case IDs、fault points、expected outcome、query count、analytic bytes、safe-envelope expectation |

每份报告显示 numerator、denominator、case IDs 和 failures。删除、重标或修改 member 必须改变被绑定的 digest/version，并使该 run 的 readiness evidence 失效。

`Direct Claim coverage` 与 `Required-output completeness` 分报；两者目标均为 100%。共享 calculator/legacy path 只能证明 parity，不能提供 Control truth。

## 7. Proxy Intake Protocol

PRD approval冻结协议；V0 执行。真实 Deloitte usability 继续标记 `Not Assessed`，直到 Stage 2。

- Participants：至少 2 名未参与 ADT Package、safe sample 或 template authoring 的 business proxy；
- Inputs：blank common template + guidance + fictional explanatory material + optional safe metadata/SQL artifact refs；
- Required task：形成可登记 proposal，明确 Missing/Withheld/Unconfirmed，不填 RDF/OWL/SHACL/AST/internal schema；
- Hard pass：安全 metadata完整；猜测补齐=0；internal schema填写=0；blind Operator只用获准 projection 可形成 Candidate 和具体 Gap list；
- Recorded baseline：active time、guidance clarification、返工、无法理解字段、错误分类；
- No arbitrary SLO：Stage 1 不以 `120 minutes / 2 clarifications` 作通用 trust gate；Stage 2 根据真实 Deloitte evidence 设 target。

## 8. Demo Comprehension Protocol

V5 rehearsal 至少使用 3 名未参与材料编写的 proxy viewer。3/3 必须能准确回答：

1. Q4 相对 Q3 的变化是什么；
2. 哪个 segment 的 computed contribution 最大，且这不等于因果结论；
3. period、unit 与一个 limitation；
4. evidence 为什么可追到 exact semantic/runtime/data identity；
5. 为什么结果不是 HKEX validation 或 production approval；
6. 下一步只能是 bounded client discovery，而不是直接上线。

这个小样本只证明演示没有明显误导，不声称统计性 usability。

## 9. Stage 1 Delivery Readiness Manifest

该 manifest/checklist 是 versioned delivery evidence，不是 Core object、runtime authority 或新的 Product Domain。Governed route 的安全性只依赖冻结合同；external presentation permission 还需要此 checklist 的 DRI GO。

> **Hard NO-GO：** R-01 尚未被 Decision Owner 批准，或 exact `core@1.1` Profile、Annex 与 regenerated vectors 尚未独立验证时，本 manifest 必须返回 NO-GO。旧 `core@1` 的 34 positive + 30 negative vectors 不能证明 `SELECT_REFERENCE` 或 `CONCEPT_NOT_BOUND` conformance。

每次 GO 必须绑定同一 candidate：

- source revision/build and governed route；
- exact Core/Profile/Annex refs + subject/file digests；
- exact positive/negative vector-set refs + digest + actual counts；
- reference case + ReferenceManifest；
- GSR、VRS、Activation identities；
- Suite/Control/mutation/critical/SCR protocol identities and exact results；
- 33/33 automated tests、33/33 validation checks、contract vectors；
- zero projection leakage and zero premature analytic bytes；
- required-output/Claim completeness；
- visible limitation wording and surface checks；
- clean-state rehearsal + comprehension result；
- runbook version、Product & Delivery DRI、GO time。

任一 constituent 改变使旧 checklist 不适用于新 run。V0-only、V3-only、legacy resolver、browser mock、missing V4、missing V5 或 no-DRI-GO 均为 NO-GO。

## 10. Approval, Freeze and Supersession

本附件与两份 Product-Domain PRD 采用一个原子审批边界：

1. Decision Owner 只批准 `reviews/product-prds-approval-candidate-manifest.md` 中列出的 exact Studio PRD、Agent PRD 与 Companion identity/version/digest；
2. 三份文档任一未列入、digest 不符或仍有未满足的 Profile revision gate，审批必须失败；
3. Product & Delivery DRI 负责准备 candidate manifest、检查 RACI/metric/demo/readiness 一致性；Decision Owner 独立批准或拒绝；
4. 修改 product boundary、RACI、Demo Promise、claim ceiling、metric dictionary、readiness constituent 或 external-GO rule，必须生成新 version/digest，并使旧 approval record 与旧 Delivery Readiness evidence不再适用于新 revision；
5. 仅文字勘误若不改变上述语义，也必须产生新 digest，并由 approval record 明确接受该 exact digest；不得原地覆盖已冻结版本；
6. superseding revision 必须引用被替代 identity/digest，旧版本保留为 audit history，不能被 mutable `latest` 取代。

只有完成 fresh-reader closure、R-01 决策及其 conformance artifacts、并由 Decision Owner 原子批准后，本附件才可标记 `Approved/Frozen`。

## 11. Deferred Productization

- accepted SCR → human Decision → new GSR/VRS → changed answer 的完整 co-work loop；
- real Deloitte common-template SLO 与 in-zone dereference；
- detailed second-scenario core-change ledger，只有 Strategy 的 2 semantic + 1 binding/execution 差异条件满足后才启动；
- production Studio workbench、release portal、IAM/DLP/audit、target ARM64/K8s、Knowledge Center、SKU/UI/deployment packaging。

这些内容不能被演示语言暗示为 Stage 1 已完成。
