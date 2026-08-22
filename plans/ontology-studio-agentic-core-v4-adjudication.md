# Ontology Studio Agentic Core v4 — Critic Review 裁决

状态：`APPROVED_WITH_MODIFICATIONS`  
日期：2026-08-23  
主审：Codex  
评审输入：

- `ontology-studio-agentic-core-v4-candidate.md`
- `ontology-studio-agentic-core-v4-review-packet.md`
- 当前代码、Cash Trading 严格门禁失败记录、FM Build/Review Skill 与 Semantica 方向证据

## 1. 裁决结论

候选方案的产品内核通过：

> **确定性外壳 + Agentic 内核。约束副作用，不约束思考；约束写入边界，不约束探索过程；确定性系统负责守门，不负责替 LLM 建 Ontology。**

候选方案不能原样进入开发。两轮评审确认必须修正状态拓扑、Candidate 真相源、完成分母、Evidence Receipt、Tool Loop 恢复语义和指标语义门禁。上述修改已写入 `ontology-studio-agentic-core-v4-final.md`；设计层 P0 已清零，可以开始第一个纵向切片。

“设计通过”不等于“产品完成”。每个实现 P0 均已转换为对应 Slice 的不可跳过出口门禁；门禁未通过不得进入下一片或宣称 Cash 构建成功。

## 2. 评审过程

第一轮采用三个独立视角：

1. Architecture & Generalization；
2. Correctness, Data & Security；
3. Delivery & Productization。

三方第一轮均为 `MODIFY`，共同否决了：

- 从 Build 一路延伸到 Active 的单线状态机；
- 第二套 Agent Run/Task 权威；
- mutable Candidate、Run 内嵌 Candidate 和 S3 Bundle 三重真相；
- 以合法 JSON、Candidate 数量或 Metric ID 证明 Ontology 正确；
- 旧 Builder 自动回退、固定 phase 或 packaged-case fallback；
- 用 Prompt 约束替代服务端权限边界。

第二轮交叉质询要求每位 Reviewer 主动撤回过严结论并挑战其他视角。最终形成一致意见：

- 不引入 DeepAgents/LangGraph 作为默认运行时；先实现一个串行、可替换的薄 Tool Loop adapter；
- 不建设通用全文检索平台；本轮只让 Cash 所需 XLSX、SQL、结构化来源摘要无静默截断；
- 不建设 theorem prover；只做当前支持能力范围内可证伪的类型、单位、粒度、映射、Join、Filter、SQL 和 Mock Oracle 门禁；
- 不重建 Task Center、Review UI 或发布链；只扩展现有主链；
- 第三个盲测业务案例不阻塞 Cash Demo，只阻塞未来“默认支持任意案例”的产品声明。

## 3. 主审决策

### D-01 单一权威拓扑 — `RETAIN WITH MODIFICATION`

采用：

```text
ConstructionJob       唯一 mutable task / lease / cancel / retry 权威
AgentAttempt          append-only 执行日志和 checkpoint，不拥有产品任务状态
ObligationLedger      enqueue 时冻结，模型只读
CandidateWorkspace    attempt 内 mutable、非权威、lease-fenced
CandidateBundle       completion 时一次性 seal 的 immutable artifact
ConstructionRun       immutable REVIEW_READY | BLOCKED outcome，引用 Bundle
ReviewDecision        独立 HITL 权威
Draft / Validation / Release / ActivePointer
                      继续作为各自独立权威
Task Center           投影以上状态向量
```

拒绝：Build Job 的 `HUMAN_REVIEW → RELEASED → ACTIVE` 状态，以及任何可独立改变产品状态的 `studio_agent_runs`。

### D-02 Candidate 真相源 — `RETAIN WITH MODIFICATION`

- 运行中 PG Candidate Workspace 是唯一 mutable truth；
- completion 对 exact Candidate head 执行；
- materializer 只 seal 一次 Candidate Bundle；
- Run、Reviewer、UI、HITL 全部读取同一 Bundle checksum；
- S3 是 checksum-bound 完整导出，不是另一权威；
- v1 Run 仅通过 read adapter 展示，历史不重写。

### D-03 Agent Runtime — `RETAIN WITH BOUNDARY`

- 首版采用产品自有、provider-neutral、串行 Tool Loop；
- Qwen OpenAI-compatible `tools/tool_calls` 是首个生产 adapter；
- fake/fault adapter 只用于相同合同的故障注入；
- 无 subagent、长期记忆、任意文件系统、代码执行、并行写工具；
- 若以后需要分支图、Agent 内 interrupt 或复杂 replay，重新做框架 ADR，并通过同一 `StudioAgentRuntime` port 接 LangGraph/DeepAgents adapter。

### D-04 Tool 权限与恢复 — `RETAIN AS P0`

- `RunAuthorityContext` 由服务端注入；模型不能提交 principal、workspace scope 或 source set；
- 只执行 provider 返回的结构化 `tool_calls`，不解析 source/content 中的伪 tool JSON；
- Tool schema closed，首版 `parallel_tool_calls=false`；
- mutation tool 绑定 run/attempt/lease/tool-call/idempotency key；
- Candidate revision、Tool receipt、Step head 对有状态 mutation 在同一 PG transaction 提交；
- 远端只读调用使用 durable receipt，不伪造分布式事务；
- stale lease、cancelled attempt、跨 Solution source 的有效写入/内容返回均为 0。

### D-05 完成分母 — `RETAIN AS P0`

采用冻结的 `BuildObjective + ObligationLedger`。模型可以发现并建议新增义务，但不能删除、降低或自行宣布预冻结义务完成。Cash 八指标是 Run 输入数据，不是通用 Checker 代码。

Completion 仅接受：

- 每个 obligation 由 typed Candidate、显式 Gap、Unsupported 或 NOOP 覆盖；
- Candidate materialization/closure/required validators 通过；
- 无 deterministic blocker；
- Bundle 成功 seal。

业务证据缺失/冲突形成 `BLOCKED Run`；模型、工具、存储、lease 或预算故障使 Job `FAILED`，不生成失败业务 Run。

### D-06 Exact Evidence — `RETAIN WITH NARROW SCOPE`

- Search hit 只用于发现，不能被引用；
- `read/read_range/sql.inspect` 由服务端签发 claim-level `EvidenceReceiptV2`；
- Receipt 绑定 exact source version、bytes checksum、parser artifact/version、canonical locator、returned content checksum、source-set 和 authority context；
- 本轮只完整支持 Cash 需要的 XLSX、SQL 和已登记结构化摘要；JPEG 可显式 unsupported 或使用独立登记的转写，不做 OCR 平台；
- parser 必须报告 COMPLETE/PARTIAL/UNSUPPORTED，不能把资源上限造成的 partial 冒充完整。

### D-07 指标正确性 — `RETAIN AS P0, REJECT OVERCLAIM`

门禁验证当前受支持的确定性语义签名：formula operand type、result type/unit、grain/time/filter、property/binding、source/join、SQL lineage 和 mock execution。

拒绝声称自动证明任意 SQL 与业务自然语言完全等价。无法确定的业务含义进入 Gap/assumption，由人确认。

### D-08 Reviewer 与 HITL — `RETAIN WITH AUTHORITY SPLIT`

- Reviewer 复用同一 Runtime，使用 fresh context 和只读 Candidate/Evidence registry；
- 唯一写工具是 `finding.upsert`；
- ModelFinding 永远 advisory，不能直接阻断 Draft apply；
- deterministic validator/policy 才能 hard block；
- Human principal 与 confirmation receipt 从服务端 session/demo principal 派生；
- ReviewDecision 绑定 sealed Bundle checksum 和 reviewed-content digest，通过既有 CAS 原子写 Draft。

### D-09 产品 UI — `RETAIN EXISTING MAINLINE`

不建设第二套 Task Center 或 Review 页面。现有路由、分页、保存进度、EIX 离开保护、ReviewDecisionV2、来源页和发布页继续使用。仅增加：状态向量投影、typed activity、obligation coverage、Evidence Receipt、Metric semantic signature 和结构化编辑。

### D-10 实施顺序 — `MODIFY`

由原六片压缩为四个诚实纵向 Slice：

1. A — Production Tracer；
2. B — Cash Builder Correctness；
3. C — Reviewer + HITL Product；
4. D — Governed Demo Exit。

Semantica、并行 Tool、第三盲案例、通用检索基础设施后置，不阻塞当前四片。

## 4. P0/P1 处置表

| Finding | 裁决 | 关闭方式 |
|---|---|---|
| 第二套任务/生命周期权威 | P0 retain | Final §4/§5 采用 Job/Attempt/Run/Review 状态向量 |
| Candidate 原子性、幂等和 seal | P0 retain | Final §6/§9 与 Slice A/B 门禁 |
| Completion 分母由模型控制 | P0 retain | Final §7 冻结 Objective/Ledger |
| v1/v2 混用或自动回退 | P0 retain | Final §12 engine contract enqueue-time freeze |
| Exact Evidence Receipt 缺失 | P0 retain | Final §8 与 Slice B 门禁 |
| Prompt injection/越权 | P0 narrow | 以服务端权限和 adversarial fixtures 解决；不建设 injection classifier |
| `compile_eligible` 仅等于 typed JSON | P0 retain | Final §10 semantic signature/golden gate |
| Model Finding 可硬阻断 | P0 retain | Final §11 advisory-only，hard blocker server-only |
| 客户端 reviewer 身份 | P0 for HITL | Final §11 server-derived principal；机器 identity 为 P1 audit |
| Slice 0 使用不存在的后续工具 | P0 retain | Slice A 同时交付最小正式 Evidence/Candidate/Validator/Journal |
| 全功能通用 Evidence 平台 | reject | 当前只支持 Cash 必需格式，保留 completeness contract |
| DeepAgents/LangGraph 默认引入 | reject | 薄 adapter + stable port；复杂性触发新 ADR |
| Task/Review UI 重建 | reject | 迁移扩展现有主链 |
| 真实人工 45 分钟门禁 | P1 | Demo 发布前演练，不阻塞 Slice A |
| 第三个真实业务案例 | P2 | 只阻塞未来默认泛化声明 |
| Semantica 默认前置 | reject | 可选 candidate-only tool，后置 |

## 5. 最终挑战主张与结论

### 主张 1：薄 Tool Loop 足以作为首版 Agentic 内核

结论：成立但有条件。真正稳定的是 Runtime/Tool/Checkpoint/Authority 合同，不是 while-loop 实现。Slice A 必须用真实 Qwen + 生产 Store 跑通，并用 fault adapter 证明恢复性。

### 主张 2：完整 Evidence Index 能解决当前 Cash 失败

结论：必要但不充分。它解决“看不到”，不能解决“看见但漏识别/识别错”。必须同时有 ObligationLedger、Candidate repair loop 和 semantic gate。

### 主张 3：Candidate Workspace 内自由探索与企业正确性兼容

结论：成立。前提是自由仅发生于 server-scoped、lease-fenced、非权威 Candidate Workspace，并在 immutable Bundle、HITL、CAS、Validation 边界终止。

## 6. Review Gate

- 设计 P0：`0 unresolved`；
- 设计 P1：均已落入明确 Slice 或后置项；
- 实施许可：`GO — Slice A`；
- Cash 成功声明：`NO-GO`，直到 Slice B semantic gate 通过；
- Demo 发布：`NO-GO`，直到 Slice C/D 通过。

