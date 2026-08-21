# E5 — Governed Agent Runtime Promotion Journey

状态：Implemented / Local Verified  
日期：2026-08-19  
范围：ADT constructed-synthetic single-environment PoC；不是生产 release orchestration、IAM 或 multi-cluster rollout

## 1. 第一性原理

E5 不从“需要一个运维页面”出发，而从三个不可省略的问题出发：

1. **谁有权改变状态？** Studio 只能发布 Release；只有 Agent Runtime Control 能 prepare、certify 和 CAS-activate。
2. **什么证据足以证明状态？** Release PASS 不代表可执行；Prepared PASS 不代表 active；Active 只有绑定 exact snapshot 的 8-case verification PASS 才有运行证据。
3. **失败时什么继续服务？** prepare/certification 失败不触碰 active；activation 使用 expected-current CAS，冲突不覆盖；verification 期间 active 发生切换则整次证明失效。PoC 在技术激活后的 verification 失败不会自动回滚，这是必须显式保留、不能被 UI 掩盖的生产化缺口。

由此得到最小状态链：

```text
Studio Release
  → Agent prepare + binding checks + ADT certification + pre-activation 8-case
  → PreparedRuntimeSnapshot (READY, not active)
  → expected-current CAS activation
  → exact active snapshot post-activation 8-case
  → ordinary Analysis Workspace consumes that exact snapshot
```

## 2. 产品边界

- Ontology Studio：产生 `ReleaseRef`，不能修改 active pointer。
- Ontology Analytic Agent / Runtime Operations：拥有 prepare、certification、activation 和 active verification。
- Console：只是两个产品的 PoC shell 和 API caller，不自行 certification、不写 pointer、不运行 golden suite。
- Shared contracts/kernel：提供 exact ReleaseRef、RuntimeSnapshotRef、ActivationReceipt 和 ActiveRuntimeVerification；不是第三个产品。

Agent 的 operator API 单独部署，不挂到 ordinary runtime app：

- `GET /agent-control/healthz`
- `GET /agent-control/runtime/status/{package_id}`
- `POST /agent-control/runtime/prepare`
- `POST /agent-control/runtime/activate`
- `POST /agent-control/runtime/verify-active`

## 3. 安全与正确性不变量

### 3.1 Prepare

- 只接受 exact portable release checksum；
- 校验 adapter/query-engine compatibility、完整 data binding 和 dataset identity；
- ADT certification 必须通过 control checks 与固定 8-case suite；
- 失败不改变 active；
- Console 不能把 `certify_adt=false` 的 snapshot 激活到 ADT channel，activation backend 强制 `adt-golden-v1`。

### 3.2 Activation

- 只接受已持久化、可重新验证、带 required certification 的 RuntimeSnapshotRef；
- caller 带上刚观察到的 exact current ref；
- backend 在同一 pointer lock 内做 CAS；
- active 已变化则 conflict，不执行 last-write-wins。

### 3.3 Active verification

- request 必须绑定 exact expected active snapshot；
- suite 开始前重读 active 并比对；
- suite 使用与 Agent runtime 相同的 `analyze_snapshot` application boundary；
- suite 结束后再次重读 active；
- 期间 pointer 改变即使所有 cases PASS，也返回 conflict；
- report 绑定 snapshot、8 个 case status、execution IDs 与 constructed-synthetic oracle defects。

## 4. UI surface

Semantic Layer 新增一个最小 `Agent activation` tab，只展示四格状态和三个动作：

1. Studio Release；
2. Prepared + Certified；
3. Active Runtime；
4. Active Verification 8/8。

三个按钮严格顺序启用：`Prepare & certify` → `Activate with CAS` → `Verify active 8 cases`。UI 不提供任意环境、binding、credential 或 raw manifest 编辑器，避免把 PoC 变成假的通用运维平台。

## 5. Verification evidence

- full backend/contract suite：58/58 PASS；
- backend tests 覆盖 exact 8-case verification、stale expected snapshot、suite 中途 pointer switch conflict；
- API test 覆盖 Studio release → prepare/certify → no implicit active → activate → verify 8/8 → status；
- wrong amount mapping 的 semantic release 被 certification 阻止，旧 active 保持；
- Console contract 证明 prepare/activate/verify 都只调用 Agent control API，browser 没有 golden runner；
- real-browser smoke 覆盖：Draft save、backend validation、Release not activated、Prepared+Certified、CAS Activated、Active 8/8、随后 ordinary Chat 使用新 active snapshot；
- clean-root browser evidence：Studio 发布 `1.2.1` 后 active 仍为 `1.2.0`；CAS activation 后才切换为 `1.2.1`，exact active verification 为 8/8；
- browser fallback calls 保持 0。

## 6. 当前边界

可以声称：ADT fixed release 能经独立 Agent operator control 面成为 exact verified active runtime。

不能声称：

- 这是生产 promotion workflow、审批系统或 deployment controller；
- filesystem CAS 可以替代 K8s/DB/object-store 下的分布式事务；
- 8-case synthetic oracle 等于 HKEX 业务验收；
- snapshot 之外的 mutable external warehouse 已获得一致性隔离；
- post-activation verification 失败会自动 rollback 或在切流前完成 traffic hold；当前 PoC 只把失败标记为 NO-GO；
- ARM64 image 和 HKEX K8s 环境已经实测。

## 7. 下一步

第一优先级从“再加页面”转为 `ScenarioAdapter` deep module：把目前散落在 capability、validation、planning、SQL、runtime、claim/evidence 和 certification 中的 ADT-specific 行为收进一个可替换接口。随后必须用第二个业务场景验证哪些部分真正 common；没有第二场景，不继续宣称通用 ontology compiler。
