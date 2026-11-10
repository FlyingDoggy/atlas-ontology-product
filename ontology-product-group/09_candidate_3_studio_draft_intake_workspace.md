# Candidate 3 — Studio Draft + Intake Workspace

状态：Implemented / Local Verified
日期：2026-08-19
范围：fixed ADT constructed-synthetic vertical slice；不是通用 ontology compiler、customer 业务确认或生产内容管理平台

## 1. Outcome

Ontology Studio 不再只是浏览器内模拟器。当前切片已经把“External Review Team 能提供的有限安全输入”接到一个真实、持久化、可 review 的 DraftWorkspace：

```text
需求与流程转写 ─┐
指标逻辑转写 ───┼→ fixed ADT Intake Adapter
数据模型附件 ───┤     → Submission / checksums / claim ceiling
数据字典附件 ───┤     → four extracted fields + source anchors + gaps
现有 SQL 附件 ──┘     → persisted DraftWorkspace revisions
                         → backend semantic validation
                         → immutable OntologyReleaseBundle
```

这条路径直接回应了最初的现实约束：External Review Team 不需要填写 RDF、OWL、SHACL、AST 或内部 ontology schema；他们只转写需求与指标逻辑，并把 data model、data dictionary / metadata、SQL 作为文件整理。系统第一步登记材料，而不是假设他们能提供完整、机器可执行的业务真相。

## 2. Intake contract

Reference submission 固定登记五类 asset：

| Asset | 当前加工方式 | 不做的事 |
|---|---|---|
| 需求与端到端流程 | 从安全转写提取 eligibility 与 amount assertion | 不读取 customer 原始文档 |
| 指标逻辑 | 从 M-03 提取定义与允许维度 | 不推断未写明口径 |
| Data model | locator + checksum 登记 | 不假装已实现通用模型 parser |
| Data dictionary | locator + checksum 登记 | 不自动把 sample/enum 当业务确认 |
| Existing SQL | locator + checksum，`REGISTERED_NOT_PARSED` | 不宣称已有通用 SQL parser 或 SQL=truth |

Submission 明确带 `CONSTRUCTED_SYNTHETIC_NOT_CUSTOMER_VALIDATED` claim ceiling；真实 customer 定义未确认、SQL 未机器对账均作为 open gap 保留。

## 3. Draft surface

PoC 只开放四个对业务有意义且可验证的字段：

- ADT metric definition；
- eligible status / whether cancelled records are excluded；
- allowed Period / Segment dimensions；
- amount physical field mapping。

它们被编译回 exact typed `OntologyPackage`，不是另造一套网页模型。任意 Entity/Relation/Formula/Join CRUD 当前明确不做。

每个 DraftWorkspace 有：

- revision CAS，防止旧页面覆盖新版本；
- target semantic version 与 package checksum；
- validation 的 `NOT_RUN / STALE / PASS / FAIL` 生命周期；
- source anchors 与 `modified_fields`，区分“转写直接提取”与“后来人工改动”；
- checksum-protected、write-once revision records；
- last published release ref；
- persisted current state。

## 4. Product boundary

Studio publication 只产生 portable immutable `OntologyReleaseBundle`，不会修改 Agent active pointer。

```text
Studio PATCH / validate / publish
                 │
                 └── release 1.2.x
                         (not active)

Agent active 1.2.0 ── continues serving until separate
                       prepare + certify + activate succeeds
```

这不是未完成的副作用，而是产品边界的核心行为。错误 `order_value_hkd_mn` mapping 可以在结构/类型上形成 semantic release，但 ADT runtime certification 会阻止 prepare；旧 active snapshot 继续服务。

## 5. Control API

- `GET /control/workspaces/workspace.adt.reference`
- `GET /control/workspaces/workspace.adt.reference/intake`
- `GET /control/workspaces/workspace.adt.reference/revisions`
- `PATCH /control/workspaces/workspace.adt.reference/draft`
- `POST /control/workspaces/workspace.adt.reference/validate`
- `POST /control/workspaces/workspace.adt.reference/publish`

Console Studio 的 save、validate、publish 与 source register view 已切到以上 API；control backend 不可用时不运行本地 fallback。

## 6. Verification evidence

- Python full regression：54 tests PASS。
- Studio service tests：intake extraction/anchors/gaps、revision CAS、stale validation、exact publish、old release unchanged、revision tamper detection、wrong mapping certification block。
- API tests：workspace/intake/revisions、PATCH conflict、validate、publish、CORS、publish ≠ activate。
- Console contract：live Studio actions 只调用 control API；live Agent actions只调用 runtime API。
- Real-browser integrated smoke：5 个 intake assets；Draft save；backend validation；release `1.2.2`；active Agent 仍为 `1.2.0`；随后 ANSWERED / CLARIFY / REFUSED / POLICY_DENIED / unavailable 全部通过。
- Browser observed：runtime API calls 7、Studio API calls 5、analysis fallback calls 0、无正常页 console/page error。

版本 `1.2.2` 是重复 smoke 在临时 registry 中形成的测试版本，不是新的正式产品版本。

## 7. Critic findings closed

实现后自审发现：如果字段被人修改，保留原 source anchor 而不做标记会造成 provenance 误读。现已补：

- `modified_fields` 依据当前 draft 与原 extraction 的实际差异重算；
- 每次内容 revision 都形成 checksum-protected record；
- validation / publication 更新同一 revision 的状态，但不能改写 revision content；
- record tamper 会在读取时失败。

## 8. Deliberate limits and next work

当前可声称：固定 ADT input 能形成 traced draft 与 portable release。当前不能声称：

- 任意 External Reviewer workbook / Word / SQL 都能自动解析；
- SQL 与文字冲突可以自动裁决；
- extracted candidate 是 customer-confirmed truth；
- 生产 IAM、审批、审计、object storage、多人分布式锁已完成；
- 新 release 已被 Agent 绑定并激活。

下一工程切片不是继续扩大 Studio 表单，而是：用 `ScenarioAdapter` 收拢 ADT-specific validate/plan/execute/certify 接口，并补一个显式 operator journey，把被选中的 release prepare、certify、activate 后再运行同一 8-case suite。之后再用第二个业务场景检验哪些能力真正 common。
