# Ontology Studio Agentic Core v4 — Critic Review Packet

评审对象：`plans/ontology-studio-agentic-core-v4-candidate.md`  
评审状态：Round 1 待开始  
评审要求：只评价本次 Agentic 构建内核，不扩大到企业 Knowledge Center、移动端、长期域名、IAM 或新商业功能

## A. 决策问题

当前候选方案能否把 Ontology Studio 从固定阶段的一次性 JSON 生成器，重构为真正可检索材料、调用工具、迭代修复的 Agentic Builder/Reviewer，同时保留企业发布所需的证据、权限、CAS、HITL 和 Release 权威边界？

通过后立即按纵向 Slice 实现；未通过则只修正 P0/P1，不进入开发。

## B. 当前事实基线

### B1. 已有产品资产

- Python/FastAPI/Pydantic 后端，React/TypeScript 前端；
- PostgreSQL + S3-compatible authority；
- Blank/Reference Solution、Source Library、Exact Source Version、preview；
- durable Construction Job：queue、lease、retry、cancel、stale fencing；
-类型化 `PackageDraftOperation`、Candidate、Human Disposition、CAS Draft；
- Validator、Release、Runtime Snapshot、Activation/Rollback；
- 隔离的 Semantica HTTP Worker 边界；
- Qwen OpenAI-compatible Model Gateway；
- Deloitte HK Cash Trading 原始输入和产品补充 SQL；
- Real-Qwen E2E gate 已升级为检查正式 Metric operation，而不是只检查 Candidate 总数。

### B2. 当前实现的关键限制

代码证据：

- `studio/builder.py` 把资产固定为 `SEMANTIC / ANALYTICS / DATA` 三类；当前计划为 `SEMANTIC, SEMANTIC, DATA, ANALYTICS`。
- `_phase_request` 预装 Evidence、整个 Draft Context 和 prior operations；模型不能主动搜索。
- `HttpBuilderModel.generate` 每阶段只调用一次 `/model/v1/ontology-build`。
- `model_gateway.py` 使用 JSON response format，未向模型传入可执行 Tool schema，也未处理 Tool Call。
- Build Skill manifest 声明了五个 Tool ID，但当前 Orchestrator 没有 Model-controlled Tool Loop。
- `normalize_evidence` 默认最多 256 fragment；每阶段再取 160。
- Semantica 在 `StudioConstructionService.start` 中作为固定的后续 stage 调用，而不是 Builder Tool。
- current Construction Worker 只报告粗粒度 `BUILDING_CANDIDATES`，没有 Agent step checkpoint。

### B3. 真实失败证据

最近一次 Cash Trading strict run：

- Solution：`ontology.custom.2ec30bf44a55`；Task 后缀：`98a7568a`；
- Outcome：`REVIEW_READY_WITH_WARNINGS`；
- Candidate：141；compile eligible：75；
- 类型计数：Data Source 4、Dimension 3、Gap 7、Join 1、Link 6、Mapping 37、Metric 8、Object 20、Property 32、Requirement 7、Rule 8、Source 7、SQL Contract 1；
- 八个 Metric 的 `proposed_operation` 全部为空，因此正式可发布 Metric 为 0；strict gate FAIL；
- Builder 报缺 `order_status`、`order_quantity`、`cumulative_executed_quantity`、`receive_timestamp`、买卖参与者 ID、`base_notional`、参与者类型/状态等字段；这些字段在 Deloitte 数据字典中存在；
- Semantica stage 为 `degraded-unavailable`，但这不是 Metric 失败的直接原因。

结论：当前 Outcome 名称和 Candidate 数量会制造虚假完成感；输入材料并非根本缺失，模型的可见性和执行方式才是主要问题。

### B4. 对照证据

FM Agent 的 `onto-build` / `onto-review` 只是 Markdown Skill，方法本身粗糙且硬编码 14 个 YAML，但它们依赖宿主 Agent 的文件读取、搜索、写入和迭代能力，所以方向上比当前封闭阶段调用更接近正确内核。

Semantica 可提供概念归一、关系建议和图能力，但不能替代指标公式、SQL、来源权威、HITL 或发布生命周期。

## C. 约束与明确不做

- 仅两个用户产品：Ontology Studio 和 Ontology Analytic Agent；
- Cash Trading/ADT 不进入通用代码；
- Candidate 不能自动成为 Draft；
- Reviewer/Semantica 不能自动批准；
- Analytic Agent 只读 Active Runtime Snapshot；
- 本轮不做移动端、长期域名、IAM、Knowledge Center 总体架构、Skill Marketplace 或通用代码执行沙箱；
- 当前优先完成 Cash Trading E2E，但不能以 case adapter 或 baseline replay 通过。

## D. 候选方案摘要

1. 外层确定性 Workflow 锁定来源/版本/预算/权限，管理任务和权威生命周期。
2. 内层 `StudioAgentRuntime` 运行真实 Tool-Calling Loop，而不是固定 Phase。
3. 完整 Evidence 建索引，模型只拿 Source Catalog，通过 search/read/range 工具按需读取。
4. LLM 可自由写隔离 Candidate Workspace；每次写入即时类型校验、来源绑定和 revision audit。
5. Completion Checker 把缺失闭包返回模型修复；无法完成则诚实 `BLOCKED`。
6. Reviewer 使用独立上下文和只读 Candidate 权限，只写 Finding。
7. Semantica 改为可选 `graph.propose` Tool。
8. 首版实现薄的产品自有 tool-calling loop；框架通过 `StudioAgentRuntime` Port 可替换，不把 DeepAgents/Pi 变成业务架构。
9. 现有 Source、Job、CAS、HITL、Validation、Release/Activation 复用。
10. 用微型通用 fixture + Cash Trading strict gate 验收。

## E. 信任边界

| 区域 | 可读 | 可写 | 是否权威 |
|---|---|---|---|
| Exact Source / Evidence | 当前 Run 选定来源 | Source 登记流程 | 是，来源身份权威 |
| Agent transcript/checkpoint | 当前 Run | Runtime 追加 | 是，运行审计权威 |
| Candidate Workspace | 当前 Run + Draft 摘要 | Builder Candidate tools | 否 |
| Review Findings | Candidate + Evidence | Reviewer Finding tools | 否 |
| Draft | 已处置资产 | Human Decision + CAS | 是 |
| Release / Active | 通过验证的 Draft | Release/Activation Service | 是 |

## F. 第一轮 Reviewer 输出格式

每位 Reviewer 必须输出：

1. `retain / modify / reject`；
2. Findings，标记 `P0 / P1 / P2`；
3. 每个 Finding 的证据、失败模式、修正建议、Acceptance Check；
4. 时间定位：`当前 Slice / near-term / long-term`；
5. 三条你认为最值得被其他 Reviewer 挑战的主张。

不要只评价架构图；必须检查可实现性和可证伪性。

## G. 三个独立评审视角

### Reviewer A：Architecture & Generalization

重点：

- 是否真的是 Agentic Runtime，而不是换名后的固定流程；
- Runtime Port、Tool Harness、Workflow 和 Semantica 的边界是否稳定；
- 是否暗藏 Cash/交易分析假设；
- 自建薄 Loop 与 DeepAgents Adapter 的选择是否合理；
- 纵向 Slice 是否能逐步替换而不形成第二套永久内核。

### Reviewer B：Correctness, Data & Security

重点：

- Evidence search/read 是否能保留 Exact Version、locator、checksum 和权限；
- Candidate 可写自由是否会造成伪来源、越权、Prompt injection、重复副作用或数据泄露；
- checkpoint/retry/cancel/CAS 是否在 Agent loop 下仍正确；
- Completion Checker 能否避免虚假成功；
- Builder、Reviewer、Semantica、HITL、Release 的 authority 是否明确。

### Reviewer C：Delivery & Productization

重点：

- 切片是否能在当前代码库真实落地，而非再写一套大框架；
- 哪些模块可复用、哪些应删除或 adapter 化；
- Cash strict gate 是否足够代表可演示成功；
- 任务中心、Run 进度和 Review UX 是否与真实后台状态一致；
- 测试、部署、回退和用户手册的出口是否清楚。

## H. 必须重点挑战的三条候选主张

1. **不引入 DeepAgents 也能用薄 Tool-Calling Loop 建成正确的 Agentic 内核。**
2. **完整 Evidence Index + 按需检索能解决当前 Cash Trading 的主要构建失败，而不需要 case-specific adapter。**
3. **允许 LLM 在 Candidate Workspace 内自由迭代，同时把 Draft/Release 权威完全留在确定性外壳，既能获得模型能力又不牺牲企业正确性。**

## I. 通过标准

- Round 1 三份独立报告完成；
- Round 2 每位 Reviewer 至少反驳或修正一条其他视角主张；
- 主审明确 adjudicate 每个 P0/P1：接受、修改、拒绝或延期；
- 最终文档无未处置 P0；P1 已修复或由 Decision Owner 明确接受；
- 最终基线明确列出 superseded 文档、实施切片、测试门禁和回退路径。

