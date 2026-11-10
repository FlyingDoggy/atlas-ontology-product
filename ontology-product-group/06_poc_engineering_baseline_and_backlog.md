# Ontology Product Family — PoC 工程基线、差距与实施 Backlog v0.1

状态：Engineering Working Baseline
日期：2026-08-19
范围：ADT synthetic reference PoC；不是生产架构、customer 真实口径或 Knowledge Center 方案

## 1. 结论

当前工程不是“只有 PRD”，也不是“两套产品已经开发完成”。准确状态是：

- **Analytic Agent reference backend 已经可运行**：有 typed Ontology Package、33 项 validation checks、immutable snapshot、受限问题解析、参数化 SQL、DuckDB 计算、8 个 golden cases、claim/evidence、FastAPI、Dockerfile 和 ARM64 K8s 示例。
- **Ontology Studio 只有一个高完成度的浏览器模拟器**：页面能够编辑、校验、发布和分析，但所有状态、数据、校验、发布和计算都发生在浏览器内；它没有消费真实后端，也没有持久化 workspace。
- **Intake → Ontology Draft 仍未实现**：需求/流程、指标逻辑、数据模型、数据字典和现有 SQL 都只是文件；当前 `package.yaml` 是人工手写，无法证明 common template 能被稳定加工成 ontology candidate。
- **前端和后端存在两套业务真相**：Console 使用 `XHKG-CASH` 和一套 public-reference-style 数字；backend 使用 `SYNTH-CASH` 和完整的 constructed-synthetic ADT oracle。两者的 ADT、交易日数、板块和贡献率都不同，不能直接拼接。
- **当前 snapshot 还不是两个产品之间的便携合同**：publisher 把生产者源码/测试、OS/Python/dependency identity、数据集和 golden controls 一起绑定；Agent 又在消费端按本机环境重算。它目前只能在同一代码/镜像中自发自用，无法证明独立 Studio 发布、独立 Agent 消费。
- **ARM/K8s 仍是配置级准备，不是目标环境验证**：本机是 arm64，Docker client 与 manifest 已有；Docker daemon 未运行、kubectl 无 context，所以 Linux arm64 image 和 customer K8s 尚未 smoke test。

因此，第一条开发主线应当是：

> 以 backend 的 `ontology.exchange_analytics.adt@1.2.0` 为唯一 canonical ADT truth，先切出一个便携的 Studio Release Bundle 与 Agent Runtime Snapshot 边界；再让 Console 真实消费 API，并补最小 Studio Draft Workspace 和 ADT Intake Adapter，把现有转写材料确实变成可 review、validate、publish 的 draft。

当前不需要实现完整 GSR/VRS、五类 authority transaction、通用 ontology compiler、生产 IAM 或 Knowledge Center。PoC 只实现其最小产品含义：Studio 输出 portable `OntologyReleaseBundle`，Agent 基于该 release 和本地数据/adapter 形成 `BoundRuntimeSnapshot`；不引入复杂 authority state machine。

## 2. 现有资产与真实状态

| 资产 | 当前真正具备的能力 | 可复用结论 | 关键缺口 |
|---|---|---|---|
| `ontology-agent-poc` | 可执行 ADT adapter；package validation/publish；verified snapshot；planner/compiler/runtime/evidence；API/CLI | 作为 Agent backend 和 Shared Kernel 起点 | hard-coded ADT/package/role/path；没有 intake/draft workspace；没有真实 activation；UI 未接入 |
| `ontology-console` | 双语 Studio/Semantic/Chat 产品壳；交互、校验、发布、plan/SQL/evidence 展示；browser smoke test | 作为两个产品的共同 PoC shell 和 UX 资产 | 1,965 行单文件；无 API call；浏览器内复制了数据、校验、编译、执行和 oracle |
| `ontology-e2e-demo` | 六步解释型 journey，概念和话术完整 | 作为讲解脚本与 fallback | 单 HTML simulator，不是产品代码 |
| `ontology-demo` / `fm-agent-ontology.html` | 更早的离线讲解 | 只保留视觉/叙事参考 | 不再作为工程基线 |
| ADT intake files | 需求、流程、指标逻辑、数据模型、字典、SQL、安全输入说明齐全 | 作为 Intake Adapter 的固定输入 fixture | 没有代码消费；没有 source-to-candidate trace |
| `package.yaml` | 完整 typed ontology、mapping、analysis pattern、policy、source 和 decision | 作为 canonical expected candidate/output | 手工编写；无法由 intake 重建 |
| published `1.2.0` | immutable package、validation、capability、toolchain、dataset、control、RDF/SHACL artifacts | 作为当前单体 regression snapshot | 由镜像构建时预发布；producer/runtime identity混绑，不能直接作为跨产品 release |
| Docker/K8s | runtime image、non-root、read-only rootfs、liveness/readiness、arm64 selector | 作为部署起点 | 只启动 runtime app；不含 Console/Studio；image 未在 Linux arm64 实测；无集群 context |

## 3. 当前真实调用链

### 3.1 已实现的 backend 路径

```text
hand-authored package.yaml
  → load_package / Pydantic model
  → static + binding + data + RDF/SHACL validation
  → publish_package
  → immutable local snapshot + latest.json
  → load_verified_snapshot + integrity re-check
  → resolve_request
  → build_plan
  → ADT SQL compiler + DuckDB
  → facts → claims/evidence → sanitized API response
```

这条路径是真执行，不是网页动画。数字来自合成 CSV，经 DuckDB 和 deterministic operators 计算。

注意：`existing_adt.sql` 的注释称系统会 parse/reconcile SQL intent，但代码中没有 SQL parser 或 reconciliation 实现；当前 SQL 只是人工参考 evidence。

### 3.2 当前 Console 路径

```text
embedded INITIAL_CONTENT + SOURCE_FIXTURES + CONTROL_ORACLE
  → browser in-memory draft
  → JavaScript validation
  → browser deepFreeze publish
  → JavaScript regex intent parser
  → JavaScript physical plan/evaluator
  → browser evidence + answer
```

Console 没有 `fetch`、XHR、WebSocket 或其他 backend call。它当前展示的 snapshot、validation、SQL 和 evidence 都是页面内模拟结果。

### 3.3 尚不存在的路径

```text
requirements/process template
+ metric logic template
+ data model / dictionary / sample or enums
+ existing SQL
  → submission register
  → normalized candidate + provenance
  → gaps/conflicts
  → human review/decision
  → draft package
```

这正是 Ontology Studio PoC 最需要补的能力。

## 4. 两产品与 Shared Kernel 的工程映射

```text
┌──────────────────── Ontology Studio ────────────────────┐
│ Intake Bundle → Draft Workspace → Review → Validate     │
│                              → OntologyReleaseBundle     │
└──────────────────────────┬───────────────────────────────┘
                           │ portable exact version/checksum
                 ┌─────────▼─────────┐
                 │   Shared Kernel   │
                 │ contracts        │
                 │ release registry │
                 │ compatibility    │
                 └─────────┬─────────┘
                           │ release + local binding
┌──────────────────────────▼───────────────────────────────┐
│ Ontology Analytic Agent                                 │
│ BoundRuntimeSnapshot → plan → execute → claims/evidence │
└──────────────────────────────────────────────────────────┘
```

Shared Kernel 是代码与合同底座，不是第三个用户产品。PoC 可以把两个产品部署在一个 container/pod 或一个页面中，只要 API、状态和责任边界分开；产品独立不等于当前必须拆成微服务。

### 4.1 Ontology Studio

现有归属：

- `control_app` 的 validate/publish endpoints；
- `validation.py`、`data_validation.py`、`rdf_projection.py` 的发布门禁；
- Console 的 Ontology Studio、Semantic Layer 页面；
- intake template 和 ADT reference input。

缺失：

- submission 与附件登记；
- draft workspace/revision persistence；
- intake-to-candidate adapter；
- source-to-field/object trace；
- gap/conflict/decision queue；
- 从指定 draft validate/publish，而不是永远读取固定 `DEFAULT_PACKAGE_PATH`；
- Console 调用 control API。

### 4.2 Ontology Analytic Agent

现有归属：

- runtime FastAPI；
- `planning.py`、`sql_compiler.py`、`runtime.py`；
- 8-case evaluation、boundary outcomes、claims/evidence；
- Console 的 Chat/Plan/Evidence 页面。

缺失：

- Console 调用 runtime API；
- 显式 snapshot selection/activation 的 PoC 级接口；
- API unavailable、no snapshot 和 refused/clarify/failed 的完整 UI state；
- safe internal plan inspection 与 ordinary user evidence 的展示分层；
- second scenario 证明；
- 真实 Agent/LLM orchestration。ADT 闭集当前不需要 LLM 参与计算或 SQL。

### 4.3 Shared Kernel

现有归属：

- `models.py` 的 package/plan/response contracts；
- `publisher.py` 的 immutable snapshot 与完整性验证；
- common checks、canonical checksum、RDF/SHACL projection；
- filesystem registry 与 local JSON evidence store。

缺失或尚未稳定：

- 明确的 `ScenarioAdapter` boundary；
- Studio Draft 与 Published Snapshot 的独立 contract；
- configurable package/scenario/registry paths；
- browser/API DTO 契约与兼容测试；
- producer-side `OntologyReleaseBundle` 与 consumer-side `BoundRuntimeSnapshot` 的分离；
- golden/control certification 与普通 semantic publication 的分离；
- future object storage/query engine/IAM ports。当前不实现，只保留 seam。

## 5. ADT-specific 与可复用能力

| Cluster | 可复用部分 | ADT-specific 部分 |
|---|---|---|
| Package model | GovernedObject、Metric、Rule、Binding、Join、Policy、Question、Decision | 当前字段和能力集合由 ADT 需求塑形，第二场景前不能声称通用 |
| Validation | unique IDs、source/owner/ref closure、DAG、binding/schema/join、RDF/SHACL pattern | `validate_adt_capability`、ADT oracle、calendar/segment reconciliation |
| Publication | immutable version、artifact inventory、checksum、verified handle | local directory、source-tree toolchain pin、scenario-relative data/control |
| Planning | boundary-before-data、typed plan、registered pattern | regex intent/period parser、ADT intents、fixed market and roles |
| Compilation | identifier allowlist、parameterization、join/rule lowering、DuckDB context | `compile_turnover`、`compile_trading_days` 和 fixed formula family |
| Runtime/evidence | snapshot verify、facts→claims→answer、execution persistence | ADT comparison、segment contribution、calendar-first decomposition、answer templates |
| Console | Studio/Agent navigation、draft/publish UX、validation/evidence inspectors | embedded ADT data、duplicate evaluator、hard-coded oracle and answer text |

判断标准：只有第二个业务场景也复用、且不需要修改语义的部分，才升级为真正 common core。当前不要为了“通用”提前抽象万能 compiler。

### 5.1 当前 capability 可达性缺口

Package/capability manifest 声称支持六个 analysis intents，但自然语言 resolver 当前只能产生四个：`metric_fact`、`period_compare`、`turnover_driver`、`evidence_audit`。`segment_contribution` 与 `sequential_decomposition` 已发布、已校验，却没有独立可达的 request path。

这不影响现有组合型 driver question，但必须二选一：

- 要么给两种 pattern 增加明确问题和 runtime rendering；
- 要么从对外 capability manifest 中降为 internal sub-operation，避免“发布为可问、实际问不到”。

当前 8-case suite 的准确含义是 **4 个 ANSWERED + 1 个 CLARIFY + 3 个 REFUSED**，不是 8 个都返回业务数字的问题。

## 6. 最小跨产品发布合同

### 6.1 Studio 输出：`OntologyReleaseBundle`

只包含能够跨进程、跨镜像稳定消费的内容：

- exact Ontology Package；
- semantic/schema validation report；
- capability requirements，而不是某台机器的 capability implementation hash；
- RDF/JSON-LD/SHACL projection；
- source/provenance safe references；
- release identity、version、checksum、limitations。

不得包含：producer source tree/test hashes、producer OS/Python identity、Agent runtime build、事实数据集或 mandatory golden oracle。

### 6.2 Agent 形成：`BoundRuntimeSnapshot`

Agent 在本地环境把 release 绑定到：

- scenario adapter/version；
- compatible query engine/runtime；
- local DataIdentity/dataset；
- policy simulation；
- optional control/golden certification profile；
- runtime checksum 和 readiness result。

PoC 用 filesystem registry 和一个显式 active pointer 即可。发布与激活必须是两个动作；`latest.json` 不能同时扮演“最新发布”和“当前可执行 authority”。

### 6.3 Golden/control 的位置

ADT 有完整 constructed-synthetic oracle，应该继续作为 ADT certification profile。普通 External Reviewer 场景可能只有部分 expected result 或没有可导出的 golden data，因此：

- semantic release validation 不强制存在 golden directory；
- 可执行 demo readiness 可以要求一个明确的 certification profile；
- request path 不在每次分析时重跑整套 golden oracle，只验证已绑定 snapshot 的完整性和 readiness evidence。

## 7. Canonical ADT baseline 决策

第一条集成切片必须只保留一个业务真相：

- Canonical package：`ontology.exchange_analytics.adt@1.2.0`；
- Market：`SYNTH-CASH`；
- Q3/Q4 turnover：8,210,000 / 6,740,000 HKD mn；
- Trading days：63 / 61；
- ADT：130,317.4603 / 110,491.8033 HKD mn per trading day；
- Leading segment：Main Board；net-change contribution 81.6327%；
- Decomposition：calendar-first，residual 0，non-causal；
- Claim ceiling：constructed synthetic；not customer validated。

Console 当前的 `XHKG-CASH`、65/61 天、286,355.57/229,799.79 ADT 和 public-source wording 只能作为旧 presentation evidence；接入 backend 时必须删除或明确隔离，不能与 canonical sample 静默混用。

## 8. 第一条最小 vertical slice

### 8.1 用户旅程

```text
Open Console
→ Studio loads real ADT draft from control API
→ edit one approved field
→ save revision
→ validation becomes stale
→ run backend validation
→ publish immutable OntologyReleaseBundle
→ Agent binds it into a BoundRuntimeSnapshot and activates it for the PoC
→ Agent workspace resolves that exact active snapshot
→ run supported + clarify + refused questions
→ inspect backend plan, checksum and evidence
```

### 8.2 只做这些

Studio：

- 一个 fixed ADT workspace；
- 读取 package/draft；
- 编辑 metric definition、eligibility rule、allowed dimensions 和 amount mapping；
- save、validate、publish；
- 显示 revision、validation status、published version/checksum 和 blocking failures。

Agent：

- 读取真实 snapshot metadata；
- 提交问题到 `/api/analyze`；
- 展示当前切片已有的四种 PoC UI state：`ANSWERED / CLARIFY / REFUSED / FAILED`；
- 展示 safe plan/evidence、snapshot checksum、execution ID 和 SQL hash；
- API down/no ready snapshot 时显式 unavailable，绝不调用浏览器 evaluator fallback。

Shared Kernel：

- 保留当前 `OntologyPackage`；把现有 `VerifiedSnapshot` 收敛成 producer release 与 consumer runtime snapshot 两层；
- 增加最小 persisted DraftWorkspace；
- control endpoints 接受 workspace/draft identity；
- published release remains immutable；
- publish 与 activate 分开；PoC active pointer 清楚标注不是生产 authority。

### 8.3 本切片不做

- arbitrary entity/relation/formula/join CRUD；
- LLM 自动生成 authoritative ontology 或 SQL；
- full GSR/VRS/attestation/authority/revocation state machine；
- production IAM、Catalog、object storage、warehouse、audit/SLA；
- second scenario、Knowledge Center、real customer data；
- 对外暴露原始 SQL、parameters、rows 或文件路径。

## 9. 第一条切片验收标准

1. Browser normal path 不再调用 Console 内的 `validateContent`、`compilePhysicalPlan` 或 `executePhysicalPlan` 作为 authority。
2. Console 所有展示数字与 backend 8-case golden suite 来自同一 package/snapshot；不存在第二套 oracle。
3. 修改 amount mapping 为类型合法但业务含义错误的字段时，semantic release 可以形成，但 ADT runtime binding/certification 必须阻止 prepare/activate；Agent 继续消费旧 active snapshot。若 intake 已提供并批准 exact mapping assertion，则也可由 semantic gate 提前阻断。
4. 合法修改发布新 version/checksum；旧 snapshot bytes、answer 和 evidence 不变。
5. 固定 8-case suite（4 ANSWERED + 1 CLARIFY + 3 REFUSED）全部通过，覆盖 missing period、forecast、raw detail 和 role denial；unknown/unrelated intent 另作一个补充 boundary case。
6. Boundary outcome 在 DuckDB 前停止；API response 不含 raw rows、SQL text、params、filesystem path 或 internal error。
7. 每个 ANSWERED 页面至少展示 snapshot、execution、metric、plan/query hash、mapping/source 与 limitation evidence。
8. API unavailable/no snapshot 时页面显示 unavailable；browser mock fallback call count = 0。
9. Console browser integration smoke 覆盖真实 API，而不只是内存 simulator。
10. Docker image 在 Linux arm64 build/run；K8s pod 的 liveness/readiness 通过。若无目标集群，只能标记 local arm64 verified / target cluster unverified。
11. Studio 生成的 release 能由另一个 process、不同 runtime identity 的 Agent 消费；producer source/test/OS hash 不参与 portable release identity。
12. 无 golden directory 的 semantic-only fixture 可以发布 release；ADT certification profile 仍要求并通过完整 oracle。

## 10. 实施 Backlog

以下是单工程师口径的粗略 ROM，不含 External Reviewer/customer 等待时间。

| 顺序 | Work package | 主要产出 | DoD | ROM |
|---:|---|---|---|---:|
| E0 | Baseline and truth consolidation | 本文件；canonical ADT decision；前后端差异清单 | owner 接受唯一 baseline | 1–2 pd |
| E1 | Portable release/runtime split | `OntologyReleaseBundle`、`BoundRuntimeSnapshot`、filesystem registry、separate activate | 不同 producer/consumer runtime 可交换 release；semantic-only 与 ADT-certified profile 均通过 | 3–5 pd |
| E2 | Runtime Console API cutover | typed frontend client；真实 health/ready/ontology/snapshot/analyze/execution | supported/refused/unavailable 从 backend 展示；无 browser execution fallback | 2–3 pd |
| E3 | Minimal Draft Workspace | persisted draft/revision；GET/PATCH/save/validate/publish endpoints；workspace tests | 固定 ADT draft 可编辑、stale、validate、publish；旧 release/snapshot 不变 | 3–5 pd |
| E4 | ADT Intake Adapter | submission manifest；读取 v0.5 workbook 的两份转写 + model/dictionary/SQL attachments；candidate/provenance/gaps | 能从真实交付模板和 checked-in attachments 重建可 review candidate；SQL 首版只登记/checksum/人工对照，不假装已有通用 parser；不自动标 confirmed | 3–5 pd |
| E5 | Integrated Console journey | Studio + Agent 同一 shell，分别消费 control/runtime API；browser E2E | 从 intake/draft 到 answer/evidence 的正常与失败路径通过 | 2–4 pd |
| E6 | ARM64/K8s smoke and demo pack | multi-arch image；PoC composition deployment；runbook；fallback | Linux arm64 smoke；readiness；8-case run；目标集群状态准确标注 | 1–3 pd |

最小可演示主线约 **15–27 person-days**。如果 E4 暂时只做 fixed ADT fixture import，不做通用 Excel/SQL parser，可进一步收缩；第二场景后再决定 parser/common compiler 的抽象。

### 10.1 E1 当前实施状态（2026-08-19）

E1 已完成本地实现与功能验证：portable release、Agent-local prepare/certification、显式 activation、active-only runtime loading、data contract/location split、三套独立 API surface 和 container init/runtime split 均已落地。43 项 pytest 全绿，另有一次全新临时 registry 的 CLI black-box flow 验证 `release → prepare → activate → analyze` 成功。

E1 尚未包含 Linux ARM64 image build/run 或 customer 目标 K8s 实机验证；这些仍属于 E6。Filesystem lock/active pointer 是单环境 PoC mechanism，不称为生产 authority。完整接口和测试边界见 `07_candidate_1_portable_release_runtime_binding_rfc.md`。

### 10.2 E2 当前实施状态（2026-08-19）

E2 已完成本地实现与真实浏览器验证。Analysis Workspace 只调用 runtime 的 ready、active snapshot、ontology 和 analyze API；live request path 不再调用浏览器 resolver、policy、compiler、fixture 或 evaluator。旧 public-style ADT truth 已退出 Console，browser publish 不能修改 active runtime，backend unavailable 显式 fail closed。

当前 48 项 pytest 全绿，JavaScript syntax checks 全绿；真实 Console + backend browser smoke 覆盖 ANSWERED、CLARIFY、forecast refusal、raw-row policy denial与 unavailable，API calls=7、browser fallback calls=0、无浏览器 error。完整边界见 `08_candidate_2_console_api_cutover.md`。

E2 刻意没有把现有 browser Studio preview 宣称为真实 Studio。Persisted draft、intake adapter、control API 与 Studio UI cutover 仍属于 E3/E4/E5。

### 10.3 E3 / fixed E4 当前实施状态（2026-08-19）

E3 已完成：filesystem-backed DraftWorkspace、revision CAS、validation stale lifecycle、checksum-protected revision records、GET/PATCH/validate/publish control APIs 与 Console Studio cutover 已落地。Studio publish 只形成 portable release，不改变 Agent active pointer。

E4 已完成**固定 ADT adapter 的最小版本**：需求/流程与指标逻辑被确定性提取为四个可 review 字段；data model、data dictionary 和 SQL 只登记 locator/checksum/processing mode；四个字段带 source anchors，人工修改另以 `modified_fields` 标识；真实定义未确认与 SQL 未解析保留为 gap。它不是通用 Excel/Word/SQL parser。

当前 full regression 为 54 tests PASS。真实浏览器 integrated smoke 已覆盖 intake → save → validate → release，并确认新 release 不会静默激活；同页现有 active Agent 的 ANSWERED / CLARIFY / REFUSED / policy denial / unavailable 继续通过。完整设计与限制见 `09_candidate_3_studio_draft_intake_workspace.md`。

E5 已完成：shared Console 新增最小 Agent activation surface，通过独立 Agent control API 完成 `选择 exact release → prepare/bind → ADT certification + pre-activation 8-case → expected-current CAS activation → exact active post-activation 8-case → ordinary Chat`。prepare 失败不改变 active；stale expected snapshot 和 suite 中途 pointer switch 都按 conflict 拒绝。完整不变量与证据见 `10_e5_operator_promotion_journey.md`。

E5 不等于生产 promotion platform：当前仍是单环境 filesystem CAS、固定 ADT binding/profile 和 PoC operator principal；生产 IAM、审批、分布式 registry、K8s rollout 与 SLA 仍未实现。

### 10.4 Candidate 4 ScenarioAdapter 当前实施状态（2026-08-19）

Candidate 4 已完成最小 deep seam：common `AgentRuntime` 通过 exact `adapter_id@version` registry 选择 scenario implementation，并只调用 `validate / evaluate / analyze`；runtime snapshot 绑定 adapter descriptor 与 build manifest；ordinary request 使用 snapshot-bound adapter。未知 adapter 在 resource binding 前 fail closed。

Certification evidence 不再只是松散 PASS 字段：ADT 固定 `adt.tracer.v1.suite` 和 8 个 case IDs，common lifecycle 独立核对 suite identity、case count/order/status 与 oracle defects；`PASS + 0 cases` 负向 adapter 已被测试阻止。完整设计、证据和不宣称范围见 `11_candidate_4_scenario_adapter.md`。

这只证明依赖方向和单场景 seam，不证明 package/compiler 已通用。下一次抽象决策必须由一个足够不同的第二 synthetic scenario 驱动。

## 11. 推荐的代码切分

这不是要求立即重构目录，只是避免继续把新逻辑塞进现有大文件。

```text
src/ontology_agent/
  studio/
    workspace.py       # draft revision lifecycle
    intake_adt.py      # fixed ADT intake adapter
    service.py         # save / validate / publish use cases
  agent/
    service.py         # resolve / plan / execute / evidence use case
  kernel/
    contracts.py       # shared DTO/contracts
    release.py         # portable OntologyReleaseBundle
    runtime_snapshot.py# local BoundRuntimeSnapshot
    registry.py        # filesystem port/adapter + explicit activation
    validation.py      # common validation orchestration
  scenarios/adt/
    adapter.py         # ADT capability, query lowering, operators, controls
  apps/
    studio_api.py
    agent_api.py
    demo_host.py       # PoC composition root；不是第三产品
```

不要求现在一次性搬文件。优先用新 façade 把 portable release 与 runtime binding 从现有 `publisher.py` 中切出，再让 UI 只依赖稳定 API，最后逐步移动内部逻辑。

## 12. 架构收敛候选

### Candidate 1 — Portable Release / Runtime Binding boundary（推荐先做）

- **Cluster**：`publisher.py`、`io.py`、validation/capability manifests、`latest.json`、runtime snapshot loading、Docker/K8s。
- **Why coupled**：生产者源码/OS/toolchain、semantic package、事实数据、golden control 和消费者 runtime 被压成一个 checksum；独立 Studio 与 Agent 正常情况下无法交换 artifact。
- **Dependency category**：PoC 为 Local-substitutable filesystem registry；未来 registry 为 Remote but owned / Ports & Adapters。
- **Test impact**：新增 producer→consumer portability、publish≠activate、semantic-only release、ADT-certified binding、rollback/tamper boundary tests；保留现有 immutable artifact tests。
- **价值**：真正建立两个产品的数据上下游关系，也是后续 UI 和 Studio workflow 不返工的前提。

### Candidate 2 — Console → Governed API boundary

- **Cluster**：`ontology-console/app.js`、runtime API、control API、browser smoke。
- **Why coupled**：Console 完整复制 package、validation、planner、compiler、fixtures、oracle、execution 和 evidence；两套实现已经产生不同数字。
- **Dependency category**：Remote but owned / Ports & Adapters。Browser 使用 typed HTTP client；测试用 FastAPI 或 in-memory adapter。
- **Test impact**：用 browser-to-API boundary tests 替换 Console 内部 calculation/mutation authority tests；保留少量 UI rendering tests 和 backend golden tests。
- **价值**：形成“页面真的在用 ontology backend”的可见演示证据，并消除双重真相。

### Candidate 3 — Studio Draft + Intake Workspace deep module

- **Cluster**：intake files、`SourceReference`、`package.yaml`、control API、validation/publisher、Console draft state。
- **Why coupled**：当前 draft 只在浏览器，backend 只读固定文件，submission→candidate 完全缺失；来源信息靠人工重复写入多个对象，且没有 sheet/row/cell 或 assertion anchor。
- **Dependency category**：Local-substitutable；PoC 用 filesystem workspace 和 Excel/CSV/Markdown/SQL adapters，测试用 temporary directory。
- **Test impact**：新增 bundle→candidate、conflict→clarification、source-anchor、revision/save/validate/publish boundary tests；删除浏览器内假 publish 的 authority assertions。
- **价值**：补齐 Ontology Studio 最核心的产品任务，证明我们设计的输入模板真的能被加工。

### Candidate 4 — `ScenarioAdapter` deep module

- **Cluster**：`capabilities.py`、`planning.py`、`sql_compiler.py`、`runtime.py`、`data_validation.py`。
- **Why coupled**：一个新指标/场景要同时修改 intent、operator、validation、SQL、facts、claims、answer；ADT metric IDs 和行为散落在五个模块。
- **Dependency category**：In-process + Local-substitutable；DuckDB 是本地 stand-in。
- **Test impact**：以 `validate / plan / execute / evaluate` adapter boundary tests 取代针对内部 helper 的碎片测试；保留 generic release/API tests。
- **价值**：为第二场景提供可量化的复用边界；现在只定义最小 seam，不造万能 compiler。

### Candidate 5 — Certification Profile boundary

- **Cluster**：`data_validation.py`、golden directory、`evaluation.py`、publisher 和 request-time validation。
- **Why coupled**：开发期 oracle、普通 semantic 发布门、runtime readiness 和每次请求检查混在一起，导致没有完整 golden 的场景无法发布。
- **Dependency category**：Local-substitutable。
- **Test impact**：ADT mutation/oracle tests 移入 explicit certification suite；普通 release tests 证明无 oracle 也可发布；request tests 不重跑完整 oracle。
- **价值**：让 common template 可用于现实中“不可能提供完整 control data”的 External Reviewer/customer 场景，同时保留 ADT 的强验证。

推荐顺序：**Candidate 1 → Candidate 2 → Candidate 3 → Candidate 4**；Candidate 5 作为 Candidate 1 的必要子任务一并完成。

## 13. 轻量测试策略

当前阶段只保留下列三层：

1. **Product journey**：一条正常路径、一条 blocking validation、一条 clarify、一条 refused、一条 backend unavailable。
2. **Business correctness**：8-case golden suite、control oracle、mapping/filter/calendar/join 的少量高价值 mutations。
3. **Deployment smoke**：API readiness、Console/API E2E、Linux arm64 container、K8s probes。

逐字段 fuzz、大规模重哈希图攻击、真实并发 registrar、生产权限/IAM 和正式合同冻结测试不属于本阶段 DoD。

### 13.1 已登记但不单独扩 scope 的技术债

- `SourceReference` 目前没有 file checksum 和 sheet/row/cell/assertion anchor；在 E4 一并补最小 provenance anchor。
- 文档来源和物理 DataSource 都使用 `source.*` ID，Evidence UI 需要显式区分 `document_sources` 与 `data_sources`。
- `pyproject.toml`、API version、README image tag 与 K8s image tag 存在 `0.1.0/0.2.0` 漂移；E6 统一 release version。
- K8s execution output 使用 `emptyDir`，Pod 重启会丢失；synthetic demo 可接受，但必须标注 ephemeral，不称为审计持久化。
- 当前 Docker build 期间自行 publish，再只启动 runtime app；E1/E6 改为显式 release artifact 和 runtime binding，避免继续绕过 Studio。

## 14. 立即决策点

建议接受以下三点后直接开始 E1：

1. backend synthetic ADT `1.2.0` 是唯一 canonical demo truth；Console 的 public-style dataset 退出 live path；
2. 第一切片先拆 portable release/runtime binding，再做 Console API cutover和Studio draft/intake；
3. PoC 允许一个 composition deployment，但 Studio API、Agent API 和 shared code 保持逻辑独立。

如果这三点成立，下一份产出不是新 PRD，而是 Candidate 1 的接口设计；接口确认后立即实施 E1。
