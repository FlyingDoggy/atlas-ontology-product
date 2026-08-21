# ADT LLM Engineering Demo — Implementation & Release Record v0.1

状态：`DEPLOYED / DESKTOP ENGINEERING DEMO GO`

日期：2026-08-19

后续版本：Studio LLM Phase 2 已在 `15_studio_llm_phase2_implementation_and_release.md` 实现并发布；本文保留为 Agent-first Phase 1 的历史发布记录。

上游方案：`13_llm_enabled_products_reviewed_candidate.md`

## 1. 本次到底发布了什么

这是 Agent-first 的 constructed-synthetic ADT `LLM Engineering Demo`，不是完整通用产品，也不是 HKEX 业务验证。

- Ontology Agent 的 **ADT overview** 继续使用 deterministic runtime 生成 dashboard、claims 和 evidence；
- **Ask the Agent** 使用 Qwen 3.8 Max 做 closed goal grounding 和 bounded next-tool selection；
- 数字、比较、排序、拆解和限制全部来自 active ontology snapshot 上的 deterministic tools；
- 最终事实文本由 closed AnswerClause 与 deterministic renderer 生成；
- Ontology Studio 继续承担 intake、draft、validation、publish 和 governance；本版没有启用 Studio LLM；
- Studio 和 Agent 是两个独立产品入口，共享登录 session，并可在顶部快速切换。

对外标签固定为：

> **LLM Engineering Demo — constructed-synthetic ADT; bounded engineering controls; not Stage 1 governed-evidence conformant; not HKEX validated; not production-ready.**

## 2. 第一性原理与执行链

LLM 擅长理解语言和选择分析路径，但不能成为指标真相、SQL authority 或数字计算器。因此本版执行链为：

```text
registered synthetic question
→ exact egress/profile/rollout/evaluation checks
→ closed ModelQuestionProjection
→ Qwen binds BoundGoalCandidate
→ deterministic Binder validates exact IDs and required analysis denominator
→ compare_periods
→ closed ModelEvidenceProjection
→ Qwen selects one permitted next action
→ rank_contributors | decompose_change | finish
→ typed verified results
→ AnswerObligation completeness validation
→ deterministic closed-answer rendering in a private buffer
→ final snapshot/profile/rollout/egress re-read
→ atomic EngineeringDemoResponseCommit
→ user-visible answer
```

Qwen 不能执行 SQL、Python、shell、filesystem、browser 或任意 HTTP tool，也不能生成自由事实段落。

## 3. 已实现的产品能力

### Ontology Agent

- deterministic ADT dashboard：两个季度的 ADT、变动、segment contribution、calendar/activity decomposition 和 claim-level evidence；
- 四个服务端登记问题：英文 period compare、英文 driver、中文 driver、英文 calendar/activity decomposition；
- 三个 snapshot-bound tools：`compare_periods`、`rank_contributors`、`decompose_change`；
- Qwen 返回 closed JSON schema，随后由 deterministic validator 再校验 intent、language、tool denominator、model identity 和 digest；
- 页面显示 model、case、snapshot、执行路线、tool/model call count、outcome、profile/obligation/commit handles；
- 五结果合同：`ANSWERED`、`CLARIFY`、`REFUSED`、`FAILED_PRECONDITION`、`FAILED_EXECUTION`；
- 任意失败丢弃 private buffer，不返回 partial numbers 或 findings。

### Ontology Studio

- persisted ADT intake/draft/revision workspace；
- metric、entities、rules、policies、mappings 和 validation 状态；
- draft CAS、validate、portable publish 与 Agent activation 分离；
- 顶部直接跳转 Ontology Agent。

Studio LLM observation/disposition/decision tracer 属于下一阶段，不在本次发布中。

## 4. 信任与数据边界

- 共享 Demo 只接受 exact registered constructed-synthetic questions；任意改写或粘贴文本在 provider call 前拒绝；
- model payload 从正向 allowlist projection 构造，不从普通 execution response 做删字段投影；
- projection 不包含 SQL、物理表列、mapping/source IDs、locator/path、policy detail、credentials 或 raw rows；
- API key 仅注入 internal `model-gateway` container；browser、Console、runtime、Studio、Agent-control、auth 和 bootstrap 均无 key；
- Model Gateway 端口没有 host/public publish；
- raw prompt/response 不持久化，metadata trace 使用受限字段；
- dashboard 与 deterministic `/api/analyze` 不依赖 Qwen，可独立工作。

## 5. 冻结运行工件

| 工件 | 身份 / digest |
|---|---|
| Engineering Run Profile | `adt.agent.qwen3.8max.v1` / `00bf0def0279cb09f965c35366ba90965d2f26a4cba5cecea93bd03258fcdeeb` |
| Registered Question Family | `adt.synthetic.analysis.v1` / `49539b9c004eb748c95d2e372fa84a231d9172ecc452ccfbdb3457ffeb15e8ae` |
| Model Egress Decision | `egress.adt.qwen.demo.v1` / `3a63d36deb40a4cdacb46a5453b2e604263cfe88b371ce1212d415bcfbe88303` |
| Evaluation Manifest | `eval-manifest.adt.llm.v1` / file checksum `f5ac89304f6a21c311f0c53c7008c9a17c5034ec8906230a3163a0bd7314f4ef` |
| Rollout | `rollout.adt.qwen.demo.v1`, epoch `1`, `active-question-family-canary` |
| Requested/accepted model | `qwen3.8-max` / `qwen3.8-max` |

当前 rollout 于 2026-09-18 23:00 UTC 到期，egress decision 于 2026-09-19 00:00 UTC 到期。续期必须形成新的批准记录并重跑 evaluation；不得只改日期绕过验证。

## 6. 实际模型评估

四个 registered cases 均使用真实 Qwen 3.8 Max 完成并形成 committed answer：

| Case | Tool sequence | Provider calls | Result |
|---|---|---:|---|
| `adt.compare.en.v1` | `compare_periods` | 2 | ANSWERED / committed |
| `adt.driver.en.v1` | `compare_periods → rank_contributors` | 2 | ANSWERED / committed |
| `adt.driver.zh.v1` | `compare_periods → rank_contributors` | 2 | ANSWERED / committed |
| `adt.decompose.en.v1` | `compare_periods → decompose_change` | 2 | ANSWERED / committed |

冻结 manifest 同时记录以下 security gates 为通过：unregistered input 零调用、projection leak 阻断、early-finish partial release 阻断、rollout race 阻断、model identity mismatch 阻断与 exact output schema。

## 7. 部署结果

Release tag：`0.2.0-llm-demo.1`

EC2 release directory：`/home/ec2-user/atlas-adt-demo-0.2.0-llm-demo.1`

- backend image：`sha256:24403cfb6897fc061010e91e7e6189dff64f9a2cdd0609ec99d6c22ef62b3256`；
- Console image：`sha256:aa503f50e2ed77339c7aa6e4e7577d58afa1a26ebb417940a2f3bdd35efe35a5`；
- backend wheel：`09049dd364b8fc0f69f9d0e409ce7093c82054eaf8e5ae4836710d8c310f30cc`。

- Agent：<https://accomplish-bandwidth-anything-stand.trycloudflare.com/ontology-agent/>
- Studio：<https://accomplish-bandwidth-anything-stand.trycloudflare.com/ontology-studio/>
- shared Demo credential：工作区 `AWS info/demo-access.txt`，不写入本记录；
- ingress：Cloudflare Quick Tunnel → loopback-only Console → authenticated reverse proxy → internal services；
- runtime、Studio、Agent-control、auth、Console、Model Gateway 均通过 container health check；
- backend regression：`98 passed`；ADT semantic/data/SHACL validation：`33/33 PASS`；
- Console JavaScript syntax 与 Docker Compose static config 均通过；
- 公网 Playwright smoke 已通过登录/退出、Agent/Studio canonical path、双向跳转、21 条 dashboard evidence、真实 Qwen answer commit、backend unavailable fail-closed 和 browser fallback=0；
- 公网验收时 active ontology version 为 `1.2.1`，active snapshot 为 `ed8877f4788af519703c6c24b44b46bb1037c6710adf4b3a99bf0113e8eae1fe`。

Quick Tunnel 是临时公网入口；tunnel container 重建会改变 hostname，且没有生产 SLA。

## 8. 仍然没有做的事情

- Studio LLM extraction/observation/human disposition workflow；
- shared-account arbitrary free text 或任何 HKEX/客户材料外发；
- full VRS-bound LLM profile、Frozen Core ResultReleaseCommit 或 Stage 1 conformance；
- individual IAM/SSO/MFA/per-user audit；
- stable owned domain、production ingress、multi-node state 和 HA；
- persistent automatic-off operator automation。当前 provider/schema/tool/deadline/authority 失败会逐请求 fail closed，versioned rollout 可由 operator 切为 `OFF`，且 in-flight commit 在 off/epoch change 后为零；下一版应把指定 trigger 自动写入持久 off latch，并在 UI/status 中暴露原因。
- second real business scenario；因此仍不能证明跨场景 compiler/product generality。

## 9. 下一阶段

先用当前 Agent-first Demo 做一次内部演练和一次客户叙事演练，验证“LLM 是否真正帮助解释 ontology 驱动的分析”，而不是先扩更多功能。通过后按顺序推进：

1. 持久 automatic-off latch、operator reason/status 与 recovery record；
2. Studio `ClearedInput projection → ObservationSet → accept/edit/reject → human Decision → new draft CAS` tracer；
3. 用第二个业务场景验证 ScenarioAdapter 和 intake template 的通用性；
4. 只有在真实客户环境目标明确后，再设计 VRS integration、IAM、audit、stable ingress 和 Knowledge Center 连接。

这样可以保持两个产品边界清晰：Studio 生产受治理的语义资产，Agent 消费已发布 ontology 做分析；Shared Kernel 只提供中性的合同、secret transport、deadline、digest 和 commit 机制，不形成第三个用户产品。
