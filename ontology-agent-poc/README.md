# Atlas Ontology Studio + Analytic Agent Engineering Demo

这是一个完全使用合成数据、可执行的多 solution 工程演示。当前安装两个彼此独立的 ontology package：

- `ontology.exchange_analytics.adt`：ADT reference case；
- `ontology.exchange_analytics.cash_trading`：由 Deloitte HK 转写材料编译出的 Cash Trading case。

两者复用同一套 Studio、发布生命周期、Agent 运行时、PostgreSQL/S3 持久化和 React 产品界面。它证明的是“新增 case 主要增加 package、adapter 与 controls，而不是复制产品”的闭环，不宣称已经得到 HKEX 真实业务口径或达到生产就绪：

```text
人工转写/附件
  → solution-owned Intake register + source anchors / gaps
  → PostgreSQL/S3 persisted DraftWorkspace head + immutable revision
  → typed Ontology Package candidate
  → Studio semantic validation
  → portable immutable OntologyReleaseBundle
  → Agent-local data/runtime binding
  → solution-owned certification
  → explicit activation of BoundRuntimeSnapshot
  → governed analysis plan
  → deterministic SQL / operators
  → typed claims + evidence
  → optional Qwen goal binding / bounded tool choice
  → closed deterministic answer + atomic demo commit
```

当前已通过 ADT 与 Cash Trading 两个 adapter 证实公共运行内核，但这仍是 **constructed-synthetic Engineering Demo**。它证明框架可扩展，不证明能够无人工语义建模地自动理解任意文档、SQL 或客户数据。

## 快速运行

```bash
uv sync --frozen
uv run python scripts/generate_fixtures.py
uv run ontology-agent validate
# 推荐的产品生命周期是三个独立动作：
uv run ontology-agent release
uv run ontology-agent prepare
uv run ontology-agent activate --snapshot <prepare 返回的 checksum>

# 本地 demo 兼容命令组合执行 release → prepare → certify → activate：
uv run ontology-agent publish
uv run ontology-agent evaluate
uv run ontology-agent analyze \
  --question "Why did total turnover fall in Q4 versus Q3, and which segment contributed most?"
uv run pytest

# PostgreSQL/S3 模式下一次性幂等初始化所有已登记 demo solution：
uv run ontology-agent bootstrap-all-demo
```

运行时 API：

```bash
uv run uvicorn ontology_agent.api:app --host 127.0.0.1 --port 8790
```

默认 API 只暴露运行面：

- `GET /api/healthz`：进程存活，不代表快照可用；
- `GET /api/readyz`：验证 active snapshot、release、数据、Agent build 和输出目录；
- `GET /api/product/context`：返回 backend-owned `ProductContextV1`；在新基础设施模式下，PostgreSQL 中的活动索引和 S3 exact-version 构件必须同时通过回读；
- `GET /api/solutions`：列出 Agent 可使用的 solution；
- `GET /api/solutions/{solution_id}/questions`：返回该 solution 注册的问题族；
- `GET /api/solutions/{solution_id}/runtime/active`：读取该 solution 的 exact active runtime；
- `GET /api/solutions/{solution_id}/ontology`：读取该 solution 的安全 ontology 视图；
- `POST /api/solutions/{solution_id}/analyze`：按 solution adapter 执行受约束分析；
- `POST /api/analyze`：固定 synthetic demo principal，不接受调用方自报 role；
- `GET /api/llm/status`：只返回安全的 profile、rollout、model 和 question-family 状态；
- `GET /api/llm/questions`：返回四个获准的 constructed-synthetic registered questions；
- `POST /api/llm/analyze`：Qwen 只做 closed goal grounding 与 bounded next-tool selection；未登记问题零模型调用；
- `GET /api/executions/{execution_id}`：返回已脱敏的步骤和证据，不返回 SQL、参数、行或内部错误；
- `GET /api/ontology`、`GET /api/snapshots`、`GET /api/runtime/active`：只返回安全的 release/active 视图。

Studio 发布面是独立的 `ontology_agent.api:control_app`；Agent prepare/activate 面是独立的 `ontology_agent.api:agent_control_app`。两者都不应挂到普通 runtime route。PoC 中的固定角色只是政策逻辑模拟，不是身份认证；真实环境必须接入客户 IAM。

Studio control API 当前提供 solution-aware catalog 与 descriptor-driven workspace：

- `GET /control/solutions`：读取 PostgreSQL + exact S3 验证后的 solution registration 与四类 component descriptors；catalog 不产生 release/activation authority；
- `GET .../editor`：返回 exact Authoring Profile 驱动的字段、控件、枚举和当前 durable workspace；
- `POST .../draft-operations`：提交通用 path/value operations，由已登记 solution adapter 翻译并执行 expected-revision CAS；
- `GET /control/workspaces/workspace.adt.reference`：持久化 draft、revision、validation、modified fields；
- `GET .../intake`：五类 cleared synthetic assets、checksum、source anchors 与 gaps；
- `GET .../revisions`：checksum-protected immutable revision records；
- `PATCH .../draft`：以 `expected_revision` 做 CAS 更新四个受限字段；
- `POST .../validate`：对 exact current draft 运行 backend semantic validation；
- `POST .../publish`：只发布 portable release，不激活 Agent。

这不是任意 ontology CRUD 或“上传即理解”的文档/SQL parser。需求与指标逻辑通过 solution-owned compile spec 和人工确认规则建模；data model、dictionary 与 SQL 只有在编译、验证并产生可追溯 binding 后才进入运行时。

Agent operator control API：

- `GET /agent-control/runtime/status/{package_id}`：读取 exact active ref 与当前激活事件持久化的 exact rollback target；
- `POST /agent-control/runtime/prepare`：绑定本地数据、校验 adapter 并运行 solution-owned certification suite；
- `POST /agent-control/runtime/activate`：以 expected-current CAS 激活 certified snapshot；
- `POST /agent-control/runtime/rollback`：以 exact target snapshot + expected-current 执行显式回滚；
- `POST /agent-control/runtime/verify-active`：对 exact active snapshot 复跑 8-case，并在 suite 前后检查 pointer 未变化。

Operator control 属于 Analytic Agent 产品，不是第三个产品。普通 runtime API 无法执行 prepare/activate，也不能接受用户自报 role。

PostgreSQL/S3 产品状态与生命周期初始化命令：

```bash
uv run alembic -c alembic.ini upgrade head
uv run ontology-agent bootstrap-all-demo
uv run ontology-agent bootstrap-product-context
uv run ontology-agent bootstrap-solution-catalog
uv run ontology-agent gc-lifecycle-artifacts --grace-seconds 86400
```

`ONTOLOGY_PRODUCT_STATE_MODE=postgresql-s3` 时，solution catalog、workspace head/history、
product context 的数据库记录或 exact S3 version 任一不可读都会令 readiness
fail-closed；默认 `legacy-compatibility` 只用于迁移和隔离测试，不声称使用了 PostgreSQL/S3。

`ONTOLOGY_LIFECYCLE_STATE_MODE=postgresql-s3` 时，release、runtime snapshot、active
head 与 activation event 持久化到 PostgreSQL，release/snapshot bytes 以 exact S3
version 持久化。激活和回滚共用同一个 PostgreSQL CAS 顺序域；本地 filesystem
只作为可重建 cache/compatibility source，不能覆盖 PostgreSQL active head。生命周期
状态 API 从当前 activation event 重建 rollback target，因此页面刷新或 control service
重启不会丢失回滚入口；target 缺失、身份不闭合或不再处于 READY 时 fail closed。生命周期
对象清理默认 dry-run，最短 grace window 为一小时，已提交或仍在 lease window 内的
对象不得删除。

`bootstrap-solution-catalog` 会先核验每个 registration 的 component digest，
再核对 registration 与 semantic source 的 solution/semantic-version/scenario/display
identity，以及 Authoring Profile 的 workspace/adapter/semantic-slot closure，
最后写入 PostgreSQL 与 exact S3 version。这个 registration 只是 Studio discovery/
delivery index，不代替 semantic release、runtime snapshot 或 activation。

## ARM64 Docker 与 K8s

```bash
docker buildx build --platform linux/arm64 -t ontology-agent-poc:0.2.0-arm64 --load .
# init 与 runtime 共享同一个显式 registry volume；镜像 build 不再偷偷发布：
docker volume create ontology-agent-registry
docker run --rm -v ontology-agent-registry:/app/published \
  ontology-agent-poc:0.2.0-arm64 ontology-agent publish
docker run --rm -p 8790:8790 \
  -v ontology-agent-registry:/app/published \
  ontology-agent-poc:0.2.0-arm64
kubectl apply -f k8s/deployment-arm64.yaml
```

Dockerfile 使用 `uv.lock` 的 frozen 安装，但不在 image build 中发布或激活。正式的 common-product composition 位于 `../deploy/common-product`，包含 React、FastAPI、PostgreSQL、S3-compatible MinIO、共享账号登录和 Helm chart；初始化 job 会幂等安装 ADT 与 Cash Trading。它仍是 PoC composition，不是生产发布 authority。示例已区分 liveness 与 readiness；Linux ARM64 镜像已在本地 ARM64 Docker 构建并通过干净环境启动，HKEX 目标集群仍需实机验证。

## 关键可信边界

- typed YAML/JSON 是编辑和编译真相；RDF/JSON-LD 是发布投影。
- SHACL 验证图合同；SPARQL只做知识依赖查询；OWL完整推理暂不采用。
- Formula AST、单位、粒度、时间、人口、binding、join 等通用语义错误阻止 release；solution adapter/operator、真实数据和 oracle 问题在 prepare/certification 阶段阻止激活。
- 运行时只接受显式 active、不可拆分并再次校验的 `BoundRuntimeSnapshot`。
- `DataSource` 只表达逻辑 tabular contract；本地文件位置和 dataset identity 只存在于 Agent binding/snapshot。
- Qwen 不生成 SQL，不执行公式和数字计算，也不成为事实或发布 authority；它只在 exact Engineering Run Profile 下绑定 goal 并从三个 snapshot-bound tools 中选择下一步。
- 真实模型调用必须通过独立 `model-gateway`，同时匹配 egress decision、closed projection、registered question family、profile、rollout 与 frozen evaluation manifest；API key 只存在于该内部服务。
- 所有展示数字、方向、排名和限制都从 typed claim 与 closed AnswerClause 渲染，并链接 snapshot、plan、tool、evidence、obligation 与 atomic demo commit。
- provider/schema/tool/deadline/revocation 任一失败均丢弃 private answer buffer；不展示 partial analytic answer。
- 当前模式准确称为 `LLM Engineering Demo`，不是 Stage 1 governed-evidence conformance、HKEX validation 或 production readiness。

## 目录

```text
src/ontology_agent/     元模型、能力、校验、发布、计划、执行、治理查询和 API
src/ontology_agent/studio/ 通用 editor/store contracts、intake compatibility 与 workspace lifecycle
src/ontology_agent/solution_adapters/ ADT 与 Cash Trading 的 draft translation adapters
scenarios/adt/authoring/ exact editor descriptor 与 semantic-slot binding
scenarios/adt/input/    Deloitte 转写与附件的安全模拟输入
scenarios/adt/ontology/ 内部 typed package
scenarios/adt/data/     合成交易、证券和交易日历数据
scenarios/adt/golden/   构造的合成 control oracle 与完整问题集
scenarios/adt/sql/      现有 SQL 样例及对照查询
scenarios/adt/llm/      Engineering profile、prompt/tool/projection 与 registered question contracts
scenarios/cash_trading/ Deloitte 输入登记、显式假设、typed package、合成数据、controls 与 LLM contracts
published/releases/     Studio portable immutable releases
published/runtime/      Agent-local snapshots、certifications 与 active pointer
src/ontology_agent/llm_*.py   goal/binder/tool/answer/commit 的 closed runtime
src/ontology_agent/model_gateway.py   独立 Qwen server-side gateway
tests/                  unit、mutation、golden-suite、API 和端到端测试
```
