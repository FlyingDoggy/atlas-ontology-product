# Candidate 4 — ScenarioAdapter Deep Module

状态：Implemented / Local Verified
日期：2026-08-19
范围：ADT constructed-synthetic PoC 的最小可替换 seam；不是通用 ontology compiler 或动态 plugin platform

## 1. 第一性原理

这次重构不从“以后可能有很多场景”出发，而从一个已经发生的事实出发：新增一个指标或场景，目前必须同时修改 capability、validation、intent resolution、planning、SQL、facts、claims、answer 和 certification。真正的问题不是文件夹不好看，而是 common lifecycle 直接知道 ADT 怎么算。

因此只接受三个可证伪目标：

1. common lifecycle 根据 exact `adapter_id@version` 选择实现，未知版本在读取数据前 fail closed；
2. snapshot 绑定被选 adapter 的 identity 与 build manifest，分析时不能换成另一个实现；
3. adapter 必须提供足够的 certification evidence，`PASS + 0 cases` 不能被 prepare/activation 接受。

第二场景出现前，不声称该接口已经证明“通用”。

## 2. 最小接口

`ScenarioAdapter` 只有三类业务动作：

- `validate`：场景 capability + runtime binding/data validation；
- `evaluate`：固定 certification/verification suite；
- `analyze`：隐藏 resolve → plan → compile → execute → facts → claims/evidence → answer。

另有两类只读合同信息：

- `descriptor`：exact adapter、query engine、certification profile、suite ID 和固定 case IDs；
- `build_manifest`：绑定实际实现文件与依赖，用于 immutable runtime snapshot verification。

Common lifecycle 继续拥有 release loading、resource locator resolution、artifact persistence、checksums、CAS activation 和 active pointer；adapter 无权直接激活。

## 3. 当前依赖方向

```text
Studio Release
  → AgentRuntime
      → ScenarioAdapterRegistry.resolve(exact id + version)
      → adapter.validate(...)
      → common snapshot persistence/checksum
      → adapter.evaluate(...)
      → common readiness + CAS activation

ordinary request
  → verified active snapshot
      → snapshot-bound adapter.analyze(...)
```

`AgentRuntime` 不再直接 import/call：

- `validate_adt_capability`；
- `run_binding_checks`；
- `run_certification_checks`；
- `run_golden_suite`。

ADT-specific binding/profile factories 也移到 `adt_scenario.py`；API 与 legacy CLI 作为固定 ADT composition root 可以显式选择它们。

## 4. Evidence contract

ADT adapter descriptor 固定：

- adapter：`adt-reference@1.0.0`；
- query engine：`duckdb.local@1`；
- certification profile：`adt-golden-v1@1.0.0`；
- suite：`adt.tracer.v1.suite`；
- cases：4 ANSWERED、1 CLARIFY、3 REFUSED 的固定 8 个 case IDs。

Common lifecycle independently核对 suite ID、case count、case IDs/order、case status 和 oracle defects。即使一个 adapter 返回 `status=PASS`，只要缺 case、case FAIL 或 oracle defects 非空，证据仍被拒绝。

## 5. 实现位置

- `src/ontology_agent/scenario.py`：contract、descriptor、registry、evidence invariants；
- `src/ontology_agent/adt_scenario.py`：唯一 ADT implementation/composition profile；
- `src/ontology_agent/lifecycle.py`：只通过 selected adapter validate/evaluate；
- `src/ontology_agent/runtime.py`：public analysis dispatcher；现有 ADT implementation 暂保留为 private `_analyze_adt_snapshot`；
- `src/ontology_agent/runtime_snapshot.py`：校验 snapshot binding 与 exact adapter build；
- `tests/test_scenario_adapter.py`：adapter boundary 与负向证据。

## 6. Verification

- full backend/contract regression：63/63 PASS；JavaScript/Python syntax checks PASS；
- exact registry selection PASS；duplicate registration 与 unknown version fail closed；
- unknown adapter 在无效 resource root 被访问前拒绝；
- recording adapter 证明 prepare validation、pre/post evaluation 和 ordinary analysis 都走同一 bound instance；
- malformed `PASS + 0 cases` adapter evidence 被 common lifecycle 阻止；
- snapshot adapter manifest 仍参与 checksum/tamper verification；
- 原 ADT calculation、mutation gates、API、Studio、Console contracts 和 E5 lifecycle regression 保持通过。
- clean-root browser journey PASS：release `1.2.1` 后 active 保持 `1.2.0`，CAS 后切到 `1.2.1`，`adt.tracer.v1.suite` 8/8，browser fallback 0。

## 7. Critic conclusion and deliberate limits

本轮通过的 claim 是：**common Agent lifecycle/runtime 已有一个真实被消费、exact-bound、fail-closed 的 scenario seam。**

仍不能声称：

- 已有第二业务场景；
- package model、formula AST、query contracts 和 evidence model 已被第二场景证明通用；
- adapter 可动态上传、安装或运行不可信第三方代码；registry 仍是进程内受控 composition；
- ADT implementation 已完成物理目录迁移；当前先冻结依赖方向，避免为了移动文件制造风险；
- fixed regex resolver/DuckDB compiler 能处理开放式 customer 问题；
- post-activation verification failure 已有 traffic hold/automatic rollback。

下一次真正检验不是再抽象一层，而是选择一个足够不同、仍可合成且可验证的第二场景，用“新增场景需改哪些 common 文件”作为量化指标。若仍需修改 common lifecycle 才能接入，接口就没有通过。
