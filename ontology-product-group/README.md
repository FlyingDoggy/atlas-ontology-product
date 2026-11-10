# Ontology Analytics Product Family 规划文档

当前状态：产品组总体规划 v1.0 与 Shared Product Contract v0.1 均已获 Muyu 批准并置为 `Approved/Frozen`。Ontology Studio 与 Ontology Analytic Agent 两份 Product-Domain PRD 已完成两轮 adversarial critic review、主审修订及三路 fresh-reader final closure：Product PASS 0/0/0，Correctness/Security PASS 0/0/0，Delivery PASS 0/0/1（仅 frozen `core@1` 的非阻断历史措辞，留待 `core@1.1` 澄清）。两份 PRD/Companion 仍是 Revised Candidate，不是 implementation authority。R-01 的方向已获 Decision Owner 批准，但后续 exact `core@1.1` freeze packet 尚未通过独立 conformance gate，因此不得冒充 Frozen Core authority。

与该正式 Stage 1 gate 分开，constructed-synthetic `LLM Engineering Demo` 的 Agent-first Phase 1 与 Studio Phase 2 均已实现并部署到 EC2。Agent 使用 Qwen 3.8 Max 做 closed goal binding 和 bounded tool choice，事实仍由 deterministic ontology tools 与 closed renderer 产生；Studio 使用 Qwen 从批准的 ADT 转写中提出五个 typed observations，经人工逐项 disposition 后才可能形成 draft，且不能直接 publish。其明确标签为非 Stage 1 conformant、非 customer validated、非 production-ready。这个独立 demo class 不解除双 PRD formal approval 或完整 Product Target 的 blocker。

## 文档序列

1. `01_product_group_strategy.md`：一个 Product Family、两个独立 Product Domain、一个 Shared Contracts & Kernel 的父级规划。
2. `02_shared_product_contract.md`：Core Product Contract，冻结 GSR/VRS、authority、projection、gate、lifecycle、evidence 与 change contracts。
   - `shared-contract/01_synthetic_trusted_flow_core.md`：ADT Stage 1 的固定范围、claim ceiling、vertical slices、ROM 和 out-of-scope。
   - `shared-contract/02_technical_conformance_annex.md`：逐对象 identity、canonicalization、gate reuse、CAS/release algorithm 与 conformance matrix。
   - `shared-contract/fixtures/canonical-json-v1.0-vectors.json`：34 positive + 30 negative fixed vectors；由独立 verifier 校验。
3. `03_ontology_studio_prd.md`：Studio 用户任务、safe intake、blind Candidate/Trace、Decision、GSR 和 Change Inbox 产品要求。
4. `04_ontology_analytic_agent_prd.md`：Runtime Release Operations、governed analytics、five outcomes、Claims、evidence/replay 和 safe feedback 产品要求。
5. `05_stage1_demo_delivery_companion.md`：两产品共用的 Demo Promise、minimum surface、slice RACI、metrics、proxy protocols 和 delivery readiness；不是第三产品或 runtime authority。
   - `fixtures/product-family-metric-events-v0.1.json`：Studio、Agent、Product-family calculator 共用的 product-reporting consistency fixture；不是 runtime authority。
6. `06_poc_engineering_baseline_and_backlog.md`：现有 PoC 工程事实、canonical ADT baseline、架构收敛候选和实施顺序。
7. `07_candidate_1_portable_release_runtime_binding_rfc.md`：已接受的 E1 深模块接口、依赖策略、测试边界和实施约束。
8. `08_candidate_2_console_api_cutover.md`：已实现的 E2 live Agent API cutover、唯一 truth 边界、浏览器验证与 Candidate 3 handoff。
9. `09_candidate_3_studio_draft_intake_workspace.md`：已实现的 E3 + fixed E4 intake/draft/revision/control API、产品边界、critic closure 与验证证据。
10. `10_e5_operator_promotion_journey.md`：已实现的 release → prepare/certify → CAS activate → active 8-case → ordinary Chat journey 与第一性不变量。
11. `11_candidate_4_scenario_adapter.md`：已实现的 exact-bound ScenarioAdapter seam、evidence invariants、critic limits 与第二场景验真标准。
12. `reviews/proposed-profile-revision-core-1.1.md`：R-01 决策包，显式合并 E-01 与 E-02；当前只是 Decision Candidate。
13. `12_llm_enabled_studio_agent_architecture_candidate.md`：LLM 双产品架构 Round 1 输入，现已被 reviewed candidate 取代。
14. `13_llm_enabled_products_reviewed_candidate.md`：两轮三视角 critic review 后的 LLM 产品方案；选择 Agent-first Engineering Demo，定义 Qwen、egress、closed answer、no-partial、rollout 与 Studio second-stage 边界。
15. `14_llm_engineering_demo_implementation_and_release.md`：Agent-first Qwen 实现、冻结工件、真实 eval、EC2 release、claim ceiling、残余差距与下一阶段记录。
16. `15_studio_llm_phase2_implementation_and_release.md`：Studio ClearedInput → Qwen ObservationSet → human disposition → draft CAS 的实现、真实公网验收、发布证据与 lesson learned。
17. Studio、Agent 与 Shared Kernel 技术设计/ADR：围绕 approved vertical slices 增量形成。

## 评审材料

- `reviews/review-packet.md`：统一事实基线和评审要求。
- `reviews/round-1-findings.md`：第一轮三视角独立评审及主要分歧。
- `reviews/round-2-adjudication.md`：交叉质询、主审裁决和 delivery slices。
- `reviews/reader-testing.md`：四次 fresh-reader 测试、发现的问题和最终 PASS 记录。
- `reviews/shared-contract-review-packet.md`：Shared Product Contract 的当前实现基线、约束和评审问题。
- `reviews/shared-contract-round-1.md`：Shared Product Contract 第一轮三视角 findings。
- `reviews/shared-contract-round-2-architecture.md`、`shared-contract-round-2-security.md`、`shared-contract-round-2-delivery.md`：第二轮交叉质询。
- `reviews/shared-contract-round-2-adjudication.md`：Shared Product Contract 主审裁决、最终对象模型与切片。
- `reviews/shared-contract-reader-testing.md`：三路最终 fresh-reader PASS、自动校验与未关闭实现 blocker 的汇总记录。
- `reviews/product-prds-review-packet.md`：双 Product-Domain PRD Round 1 冻结 packet。
- `reviews/product-prds-round-1-{architecture,security,delivery}.md`：三路独立 critic findings。
- `reviews/product-prds-round-2-{architecture,security,delivery}.md`：三路交叉质询与 scope 收敛。
- `reviews/product-prds-round-2-adjudication.md`：主审裁决、accepted revision、slice ownership 与 PASS 条件。
- `reviews/product-prds-consistency-matrix-r2.md`：修订后的 cross-PRD closure self-check。
- `reviews/product-prds-fresh-reader-{product,security,delivery}.md`：修订后第一轮独立 reader gate；0 P0，并识别剩余治理/合同/口径 closure。
- `reviews/product-prds-fresh-reader-{product,security,delivery}-final.md`：最终 focused closure；三路均 PASS，Product/Security 0/0/0，Delivery仅1个frozen-parent非阻断P2。
- `reviews/proposed-erratum-concept-not-bound.md`：E-01；不改动 frozen parent 的 `CONCEPT_NOT_BOUND` 修订提案。
- `reviews/proposed-erratum-reference-selection.md`：E-02；Reference Truth selection 的两阶段 authority/commit修订提案。
- `reviews/proposed-profile-revision-core-1.1.md`：E-01 + E-02 consolidated R-01 decision pack。
- `reviews/product-prds-approval-candidate-manifest.md`：精确绑定两份 PRD + Companion digests 的 blocked candidate snapshot；不是 approval record。
- `reviews/llm-enabled-products-review-packet.md`：LLM 双产品架构的冻结事实 packet。
- `reviews/llm-enabled-products-round-1-{architecture,security,delivery}.md`：第一轮三视角独立 critic review。
- `reviews/llm-enabled-products-round-2-cross-examination-brief.md`：Round 1 findings 的 consolidated cross-examination brief。
- `reviews/llm-enabled-products-round-2-{architecture,security,delivery}.md`：第二轮交叉质询与交付裁决。
- `reviews/llm-enabled-products-round-2-adjudication.md`：最终主审裁决、Option A-secure、20–30 pd delivery slices 与 executable gates。

本目录只规划产品边界、正式产品合同和演进，不替代 `ontology-agent-blueprint` 中的 Ontology/Runtime 工程设计。
