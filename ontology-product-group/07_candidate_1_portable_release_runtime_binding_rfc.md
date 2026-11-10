# Candidate 1 RFC：Portable Release / Runtime Binding

状态：Implemented；local functional verification PASS，Linux ARM64/目标 K8s 待 E6 实机验证
决策日期：2026-08-19
范围：Ontology Studio → Ontology Analytic Agent 的最小可移植交付边界

## Problem

现有 `publisher.py` 把语义包、producer 源码/测试、OS/Python、Agent 实现、事实数据和 golden control 压成一个 snapshot checksum；`latest.json` 又同时表示“最新发布”与“当前运行”。这使 Studio 与 Agent 不能作为两个独立产品交换稳定 artifact，也使没有完整 golden data 的真实场景无法完成 semantic publication。

当前 `DataSource.location/fingerprint` 还把本地文件位置和数据身份写进 Ontology Package。只在旧 publisher 外包一层 façade 不能形成真正 portable release，因此 E1 必须同时拆开语义数据合同和 Agent-local resource binding。

## Proposed Interface

普通调用者只使用四个业务动作：

```python
release = studio.publish(package, safe_sources=(), limitations=())

prepared = agent.prepare(
    release.ref,
    binding=runtime_binding,
    certification=adt_golden,  # optional
)

agent.activate(prepared.ref)
active = agent.open_active(environment_id="adt-poc")
```

- `OntologyReleaseBundle`：不可变、可复制；只含 Ontology Package、semantic validation、capability requirements、RDF/JSON-LD/SHACL、safe provenance、limitations 和 artifact digests。
- `BoundRuntimeSnapshot`：Agent-local；绑定 exact release、adapter/query runtime、local DataIdentity、binding validation 和可选 certification。
- `CertificationReceipt`：绑定 exact runtime binding；ADT profile 使用 synthetic oracle 与 8-case suite。普通 semantic release 不强制 golden。
- `ActivationRecord`：唯一能改变运行通道的动作；publish/prepare/certify 均不得隐式激活。

`open_active()` 返回已验证的 runtime handle；分析请求不再重跑整套 golden suite。

## Dependency Strategy

- Filesystem release/runtime store：**Local-substitutable**；测试使用 `tmp_path`。
- CSV + DuckDB：**Local-substitutable**；资源路径由 Agent-local resolver 解析，不进入 release。
- 未来 object/OCI registry：**Remote but owned / Ports & Adapters**；E1 只保留最小 repository seam，不实现网络 registry。
- Scenario adapter：E1 仍只有 ADT 实现；对普通调用者隐藏，暂不建设万能 compiler 或完整 plugin platform。

## Testing Strategy

新增 interface-boundary tests：

1. 同一 semantic package 在不同 producer 环境得到同一 release identity。
2. release 不含 source/test/OS/Python/data/golden/path/credential identity。
3. 无 golden 也能完成 semantic publication。
4. publish、prepare 均不改变 active；activate 才原子切换。
5. release 可被另一目录/进程的 Agent prepare。
6. adapter、data、runtime 任一变化只改变/阻断 runtime snapshot，不改变 release。
7. ADT certification 失败不产生可激活 snapshot，旧 active 继续服务。
8. request path 只验证 active snapshot integrity，不重跑 certification。
9. 现有 8-case suite、oracle、boundary-before-DuckDB、claim/evidence 结果保持不变。
10. release/snapshot/pointer tamper 均 fail closed。

旧 publication tests 中对 producer toolchain、runtime identity、dataset 和 control 必须同时存在于“发布物”的断言被替换；这些检查按责任迁移到 release 或 runtime boundary tests，而不是叠加两套真相。

## Implementation Recommendations

- `DataSource` 只表达逻辑 tabular contract；文件位置和 dataset fingerprint 迁入 `RuntimeBindingSpec`。
- semantic validation、runtime binding validation、ADT certification 三阶段必须有不同报告和 checksum。
- release version 是人类 alias，release checksum 是机器 exact identity；同版本不同内容拒绝。
- filesystem adapter 使用不可变目录和原子 active pointer；PoC 不把它称为生产 authority。
- certification 绑定不含 certification 本身的 `binding_checksum`，避免 digest cycle；最终 snapshot checksum再覆盖 binding + certification receipt。
- 保留旧 `publish_package()` 作为短期 demo composition wrapper，其真实语义为 publish → prepare → certify → activate；新产品接口不得依赖该 wrapper。
- 不在 E1 实现 full GSR/VRS、签名/PKI、IAM、审批、撤销、distributed registrar、warehouse connector 或第二业务场景。

## Acceptance Clarification

“类型合法但业务含义错误”的字段 mapping 未必能被通用 semantic validation识别。默认行为是：semantic release 可以形成，但 ADT binding/certification 必须阻止 prepare/activate，旧 active snapshot继续服务。若未来要求 Studio 在 publish 前阻断，intake 必须提供并批准明确的 mapping assertion；不能把该能力虚构为 SHACL 自动推断。

## Implementation Result

2026-08-19 已完成：

- `StudioReleases.publish()` 生成 deterministic semantic-only release；
- `AgentRuntime.prepare()/activate()/open_active()` 形成独立 runtime lifecycle；
- Ontology `DataSource` 与 Agent-local CSV/DataIdentity 分离；
- semantic、binding、certification 三阶段 validation 分开；
- ADT certification 同时运行 synthetic oracle 与 8-case suite；
- request path 只验证 release/snapshot/data/build/control identity，不重跑 golden；
- filesystem activation 在本地文件锁内执行 compare-and-set，支持显式 rollback；
- control、agent-control、runtime 三个 FastAPI surface 分离；
- Docker build 不再发布或激活；K8s demo 用显式 init container 填充共享 registry。

验证证据：43 项 pytest PASS；独立临时 registry 的 `release → prepare → activate → analyze` CLI black-box flow 返回 `PASS / PASS / PASS / ANSWERED`。唯一测试 warning 是 Starlette 对当前 TestClient/httpx 组合的 deprecation warning，不影响行为。

仍未声明：Linux ARM64 image build/run、customer K8s 集群、object/OCI registry、签名/IAM/审批/撤销、warehouse connector、第二业务场景和通用 compiler。
