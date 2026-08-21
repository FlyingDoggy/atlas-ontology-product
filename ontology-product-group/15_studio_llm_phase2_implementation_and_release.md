# Ontology Studio LLM Phase 2 — Implementation & Release Record v0.1

状态：`DEPLOYED / DESKTOP ENGINEERING DEMO GO`

日期：2026-08-20

上游方案：`13_llm_enabled_products_reviewed_candidate.md`

前序发布：`14_llm_engineering_demo_implementation_and_release.md`

## 1. 结论

Phase 2 已完成并部署。它不是“让 Qwen 自动构建 ontology”，而是打通了一条更小、可核验的产品链：

```text
Cleared ADT transcription
→ positive allowlist projection
→ Qwen proposes exactly five typed observations
→ immutable ObservationSet
→ human accept / edit / reject for every item
→ one CAS-protected draft revision, or REVIEWED_NO_CHANGE
→ validation and publication remain separate human-governed actions
```

因此，当前 Demo 已同时具备：

- Agent：Qwen 理解登记问题并选择受限分析路径，确定性 runtime 负责所有数字和事实；
- Studio：Qwen 从获准的 ADT 转写片段提出五类候选，人工逐项决定后才可能形成新 draft；
- 两个独立产品入口、共享登录 session 和双向快捷跳转；
- 同一 EC2 上可通过公网 HTTPS 使用。

这仍然是 constructed-synthetic ADT `LLM Engineering Demo`，不是通用 ontology compiler、HKEX 业务验证、Stage 1 governed-evidence conformance 或生产系统。

## 2. 第一性原理

### 2.1 先定义谁拥有真相

LLM 的能力是理解非结构化语言、提出结构化候选和帮助人做决策；它不拥有指标定义、source support、draft、publish 或 runtime activation authority。由此得到四条硬边界：

1. 模型输出叫 `ObservationSet`，不能叫 ontology truth；
2. 每条 observation 必须绑定获准 source anchor，并通过 closed slot/type/value 校验；
3. 五条 observation 必须全部由人 accept、edit 或 reject，不能部分生效；
4. 人工审核最多创建 draft，validation、publish、prepare、activate 继续是后续独立动作。

### 2.2 先控制模型能看到什么

安全边界不是“发出去后再删敏感字段”，而是从允许字段正向构造 `StudioModelInputProjection`。当前只投影四段 constructed-synthetic ADT 转写、批准的 anchor、当前 typed value 和五槽位合同。

以下材料即使已经登记，也不会进入 Qwen：SQL、data model、data dictionary、物理表列、raw/sample rows、文件路径、凭据和未解析附件。

### 2.3 先证明用户任务，再谈平台

Phase 2 只证明一个完整任务：业务人员可以把一组被允许的解释性转写交给模型，看到有来源的结构化建议，逐项作决定，并明确知道结果尚未发布。它没有先建设 generic document parser、RAG 平台、通用 ontology DSL 或自动 publish workflow。

### 2.4 失败必须比成功更简单

profile、slot manifest、prompt、projection policy、egress decision、evaluation、rollout、model identity、schema、deadline 任一不匹配，模型链路 fail closed；Studio 原有 deterministic draft/validation 功能仍可用。API key 只在 model-gateway，浏览器和两个产品服务都拿不到。

## 3. 当前产品体验

Studio 新增 `AI intake review` 工作台，按一条可见的四阶段轨道呈现：

1. `Cleared input`：显示批准的转写证据和 source anchor；
2. `Qwen proposal`：显示五个 typed proposal，邻接标注 `PROPOSED · not published ontology`；
3. `Human decision`：每项必须 Accept、Edit 或 Reject；
4. `Versioned draft`：只有完整审核后才允许 CAS 写入，之后仍需 validation。

每行同时展示 Source evidence、Qwen proposal 和 Human decision，避免用户把“模型说了什么”误认为“系统已经确认什么”。审核历史持久化；已审 observation set 显示最终 decision。

Phase 2 公网验收使用 reject-all 路径，结果为 `REVIEWED_NO_CHANGE`，draft revision 从 2 到 2，没有暴露 Publish 按钮。Accept/Edit、stale revision、wrong subject、缺项与重复 disposition 由自动化测试覆盖。

## 4. 技术切面

### 4.1 Studio domain

- `StudioObservationService` 负责 projection、模型调用、strict candidate validation、ObservationSet persistence、human disposition 和 draft CAS；
- `StudioIntakeProjector` 只读取 allowlist 中的转写片段，并验证登记文件 checksum；
- `StudioRunProfile` 绑定 provider/model、prompt manifest、projection policy、slot manifest、budgets、deadline 和 trace policy；
- `StudioEgressDecision`、`StudioEvaluationManifest`、`StudioRolloutRecord` 共同决定 active-observation-canary 是否可以执行；
- Studio API 只提供 status、list、generate 和 review；不存在 LLM publish route。

### 4.2 Model Gateway

- Qwen key 只注入 internal `model-gateway` container；端口不发布到 host 或公网；
- Agent 与 Studio 使用不同的 profile、projection 和 response contract，共享的只是 provider transport、secret、deadline 和 schema enforcement 机制；
- response model 必须精确为 `qwen3.8-max`；
- 缺失字段只能规范化为 `MISSING`，不能由 gateway 猜测业务值或伪造 source support。

### 4.3 Agent reliability hardening

同一 release 还补齐了 Agent 的持久 automatic-off：`PROFILE_MISMATCH`、`LEAK_DETECTED`、`DEADLINE_EXCEEDED`、`SCHEMA_FAILURE` 和 `MODEL_IDENTITY_MISMATCH` 会将 exact rollout epoch 写入 SQLite latch。旧 epoch 后续请求被阻断；新 epoch 可显式恢复。失败不返回 partial analytic answer。

### 4.4 升级安全

`bootstrap-demo` 不再假定镜像自带 semantic release 是最新版本。升级时：

- 如果现有 active snapshot 与新 runtime build 兼容，返回 `PRESERVED_EXISTING_ACTIVE`；
- 如果不兼容，以同一个 active semantic release 重建 snapshot，再用 expected-current CAS 切换；
- 不允许软件升级把 Studio 后来发布的 ontology 回滚到镜像内置版本。

本次 EC2 升级实际返回 `PRESERVED_EXISTING_ACTIVE`。

## 5. 冻结 Studio LLM 工件

下表 digest 是运行时 canonical identity，不等同于文件字节 SHA-256。

| 工件 | Identity / digest |
|---|---|
| Studio Run Profile | `adt.studio.qwen3.8max.v1` / `e7eb853736c686cc9be104dbbde9693fc09725bd3073d1729bde9a61eec6c006` |
| Semantic Slot Manifest | `slots.studio.adt.reference.v1` / `428b2681fb9fa3679c29296252e933006bfc54f4ac707f8aea2d1e613dfe99ff` |
| Prompt Manifest | digest `e0b5d286e5a6669aaafe9885a65f75f8569708078e76c899197323fe940ce261` |
| Projection Policy | digest `129a1bc5e8c76b8296ab72fcc4f962efdc87153a82a8554ec118bd40a7b256b4` |
| Egress Decision | `egress.studio.adt.qwen.demo.v1` / `cbcb25e87b6c0d1da083b1e8d7bd3fe243d1eee7ccc3f5dc82f310ebc85267b6` |
| Evaluation Manifest | `eval-manifest.studio.adt.v1` / `da56039984b182188508ad33d5bfa8ac90390c1b62812bf5da62132360473535` |
| Rollout | `rollout.studio.adt.qwen.demo.v1`, epoch `1`, `active-observation-canary` |
| Requested/accepted model | `qwen3.8-max` / `qwen3.8-max` |

当前 rollout 于 2026-09-18 23:00 UTC 到期，egress decision 于 2026-09-19 00:00 UTC 到期。续期必须形成新批准记录并重跑 evaluation。

## 6. 实测证据

### 6.1 真实 Qwen evaluation

真实 Qwen 返回并通过 strict validation 的五个槽位为：

1. ADT metric definition；
2. included trade status = `EXECUTED`；
3. cancelled-trade exclusion = `true`；
4. allowed dimensions = period + segment；
5. amount mapping = `executed_value_hkd_mn`。

模型没有直接写 draft。公网验收随后把五项全部 Reject，服务端记录 immutable human decision，draft 保持不变。

### 6.2 自动化与静态验证

- backend：`119 tests collected`，全量 pytest PASS；
- ontology package：33 项 semantic/data/SHACL checks，`33/33 PASS`；
- JavaScript syntax、Python deployment smoke syntax、Docker Compose config：PASS；
- Studio 本地真实 Qwen browser E2E：PASS；
- 公网 Agent Playwright：登录/退出、Dashboard、21 evidence、真实 Qwen committed answer、fail-closed、产品双向跳转全部 PASS；
- 公网 Studio Playwright：真实 Qwen、5/5 slots、source/proposal/decision 三列、reject-all、draft unchanged、no publish action 全部 PASS；
- 运行容器 secret inspection：只有 model-gateway 存在 `ONTOLOGY_QWEN_API_KEY`，其余六个产品/控制/展示服务为 0。

## 7. EC2 发布结果

Release tag：`0.3.0-studio-llm-demo.1`

EC2 release directory：`/home/ec2-user/atlas-adt-demo-0.3.0-studio-llm-demo.1`

- backend image：`sha256:4fc6dbd751b00d52c7c13cc8de3fdde764b8a3219307f582116c24cc543dc08c`；
- Console image：`sha256:9c57ac5e008b515e149e2cc3800776b8dcfd5de45b44ca89a697b3d2e6d86021`；
- backend wheel：`09120396fef1b8fa3e7771fb823cd76c273909d2eab427b639e42146ce8c488a`；
- active ontology version：`1.2.1`；
- active snapshot：`ed8877f4788af519703c6c24b44b46bb1037c6710adf4b3a99bf0113e8eae1fe`；
- runtime、Studio、Agent-control、auth、Console、model-gateway：全部 healthy；
- error scan：无 traceback、exception、critical、fatal 或 application error。

公网入口：

- Agent：<https://accomplish-bandwidth-anything-stand.trycloudflare.com/ontology-agent/>
- Studio：<https://accomplish-bandwidth-anything-stand.trycloudflare.com/ontology-studio/>
- shared Demo credential：工作区 `AWS info/demo-access.txt`，不写入本文。

这是 Cloudflare Quick Tunnel 临时 hostname；tunnel container 重建后可能变化，没有生产 SLA。

## 8. 当前明确做不到什么

- 不能上传任意需求文档后自动构建 ontology；当前只处理一组固定、批准的 ADT 转写片段；
- 不能把 data model、data dictionary 或 SQL 自动解析成 governed semantic assets；
- 不能让模型直接确认 source truth、改 ontology、publish GSR 或 activate runtime；
- 不能接收任意共享账号 free text 并外发 Qwen；Agent 只允许四个登记问题，Studio 只允许服务器登记的 projection；
- 不能用这个 ADT case 证明跨交易所、跨指标或跨业务场景的通用性；
- 不具备个人 IAM、SSO、MFA、per-user audit、stable domain、HA 或生产运维承诺；
- 不具备完整 VRS-bound LLM capability、Frozen Core ResultReleaseCommit 或 Stage 1 conformance。

## 9. Lesson learned

1. **Ontology-based agent 的价值不来自“用了图技术”或“接了大模型”，而来自显式分离 proposal、truth、execution 和 release authority。**
2. **Studio 和 Agent 应继续作为两个产品。** Studio 的核心交付物是被人确认并可版本化的 semantic asset；Agent 的核心任务是消费 active snapshot 完成分析。两者共享合同和 kernel，但不共享产品状态机。
3. **企业材料不足时，最重要的不是让顾问填写复杂 ontology schema，而是把解释性转写变成有 source anchor、typed slot、Missing 和 human decision 的最小闭环。**
4. **通用性不能靠抽象接口命名证明。** 必须用第二个真实不同的数据模型/指标/分析流程，验证 slot、ScenarioAdapter 和 evidence contract 是否仍成立。
5. **Dashboard 和问数不是二选一。** Dashboard 负责稳定、可比较的 common view；Agent 负责探索、归因和追问。Studio 的“dashboard”应是治理工作台与 readiness/change overview，而不是业务数据 dashboard。

## 10. 下一步

现在不应继续横向堆功能。按顺序做：

1. 用当前公网版本完成一次内部 demo rehearsal，记录用户是否理解 Source → Proposal → Decision → Draft 以及 Agent 的 Dashboard → Ask → Evidence 故事；
2. 修正 rehearsal 中阻碍叙事或操作的 P0/P1 问题，冻结一个可重复的 15–20 分钟 demo script；
3. 选择第二个明显不同的 constructed-synthetic business scenario，验证 intake template、SemanticSlotManifest、ScenarioAdapter 和 answer obligations；
4. 只有第二场景通过后，才把共性抽成 common product configuration/compiler；
5. stable domain、individual identity、audit、customer data connection、VRS 和 Knowledge Center integration 作为面向真实环境的独立升级轨道，不反向污染当前验证核心假设的 Demo。

Phase 2 的完成标准是“双产品的 LLM 增量各有一条真实、可见、受限、可失败的端到端链路”。这个标准已经达到。通用产品和生产就绪标准尚未达到，也没有在本文中被暗示达到。
