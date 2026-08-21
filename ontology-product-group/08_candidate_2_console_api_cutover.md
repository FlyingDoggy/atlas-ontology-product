# Candidate 2 — Console → Governed Agent API Cutover

状态：Implemented / Local Verified  
日期：2026-08-19  
范围：ADT constructed-synthetic PoC；不是 HKEX 业务验证或生产安全架构

## 1. Outcome

Analysis Workspace 的 live path 已从浏览器内 evaluator 切到真实 Agent runtime API。Console 现在只负责提问、状态映射和证据呈现；ADT 解析、policy、plan、DuckDB execution、answer 和 evidence 全部由 active `BoundRuntimeSnapshot` 后面的 backend 产生。

已经消除的双重真相包括：

- live path 不再使用 `SOURCE_FIXTURES`、浏览器 regex resolver、browser policy、compiler 或 evaluator；
- 旧 `XHKG-CASH`、286,355 / 229,799 和 HKEX public-reference wording 已退出 Console；
- canonical truth 只剩 `ontology.exchange_analytics.adt@1.2.0`、`SYNTH-CASH`、constructed synthetic；
- 浏览器内 Publish 按钮不能修改 active runtime；发布和激活仍属于 backend control surfaces；
- backend unavailable 时显式 unavailable，browser analysis fallback 保持 0。

## 2. Runtime boundary

```text
Console
  → GET /api/readyz
  → GET /api/runtime/active
  → GET /api/ontology
  → POST /api/analyze
      → active BoundRuntimeSnapshot
      → boundary / policy
      → typed plan / DuckDB
      → sanitized answer + claims/evidence
  ← ANSWERED | CLARIFY | REFUSED | FAILED
```

Runtime app 只为配置的 Console origins 开启 CORS。普通 API response 不返回 SQL text、parameters、rows、filesystem path 或 internal error；Console Inspector 只呈现 safe plan、step SQL hash、snapshot、execution 和 claim evidence。

## 3. Product ownership

| Concern | Owner |
|---|---|
| Active snapshot、question handling、policy、calculation、evidence | Ontology Analytic Agent |
| Browser rendering、language、interaction state | Console shell |
| Release / prepare / activation | Studio Release + Agent Runtime Control APIs；不是 browser |
| Local browser draft diagnostics | 临时隔离资产；Candidate 3 替换，不是 authority |

两个产品可以在同一 PoC shell 中展示，但 authority 与状态边界没有重新合并。

## 4. Verification evidence

- Python regression：48 tests PASS；其中新增 live-chat call-path、no active-browser-publish、single ADT truth、typed routes 和 CORS contract。
- JavaScript syntax：`app.js`、`api-client.js`、`smoke_test.mjs` 全部 `node --check` PASS。
- Real-browser smoke：真实 Console + runtime API；覆盖 ANSWERED、CLARIFY、forecast refusal、raw-row policy denial、backend unavailable。
- 实测 active snapshot：`88c3286bb49971326cd4cdba05a99a86e36ed8681ea7912f1b9439aeb2a6fe19`。
- 浏览器 API calls：7；`browserAnalysisFallbackCalls = 0`；无 page/console error。
- ANSWERED 页面展示 backend 数字 130.32bn / 110.49bn、Main Board 81.6% 与 constructed-synthetic limitation。

## 5. Deliberate limits

Candidate 2 没有假装 Studio 已接通。Studio/Semantic 页面仍保留 local preview diagnostics，但它们：

- 不参与 Agent live request path；
- 不能形成 backend release；
- 不能切换 active snapshot；
- 下一步由 persisted Draft + Intake Workspace 替换。

因此 Candidate 2 的 DoD 是“Agent live path 只有一个 authority”，不是“整个 Studio 已开发完成”。

## 6. Next slice

Candidate 3 依次补：

1. persisted ADT DraftWorkspace 与 revision/stale lifecycle；
2. GET / PATCH / validate / publish control API；
3. fixed ADT intake submission register、attachments/checksums、source anchors、gaps；
4. Console Studio 调用 control API；
5. publish 后由 Agent prepare / certify / activate，再回到同一 Analysis Workspace 验证 exact snapshot。
