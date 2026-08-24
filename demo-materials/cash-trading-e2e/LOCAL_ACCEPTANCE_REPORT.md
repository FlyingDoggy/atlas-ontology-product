# Cash Trading Demo 本地验收记录

验收时间：2026-08-24（Asia/Shanghai）

## 结论

本地 Cash Trading Demo 主线通过：

`Build 入口 → 预构建 Ontology Package → 语义资产与知识图谱 → 来源预览 → DeepAgent 真实查询`

未部署 EC2，等待 Muyu 本地验收审批。

## Package 合同

| 项目 | 结果 |
| --- | --- |
| Package ID | `ontology.exchange_analytics.cash_trading` |
| Construction Draft | `v0.2.2` |
| Draft checksum | `9647a55d99b1e9f8fce1aac42cffbfee2dd29fe582e685628794f55a2f63fee5` |
| Reviewed / Agent Active baseline | `v0.2.1` |
| Entities | 9 |
| Properties | 83 |
| Relationships | 14 |
| Dimensions | 8 |
| Metric assets | 22 |
| Data sources | 9 |
| Semantic bindings | 80 |
| Joins | 8 |

## 自动化回归

- Frontend：13 个 test files，93 个 tests 全部通过。
- Frontend production build：通过。
- Cash Trading backend：33 个 tests 全部通过。
- Docker：Web、Studio、Runtime、Agent Control、Auth、Model Gateway、PostgreSQL、MinIO 和 Semantica Worker 健康；Construction Worker 正常运行。

## 真实 Agent 验收

以下问题均由 DeepAgent + Qwen 3.8 Max 调用 Cash Trading Ontology 工具完成，状态为 `GROUNDED`，未进入 fallback：

1. M-01 Order Rejection Rate：`16.666667%`。
2. M-03 Trade Capture Latency：p50 `9 ms`，p95/p99 `15 ms`。
3. M-08 Potential Self-Trade Daily Trend：2026-08-03、08-04、08-06、08-07 均为 `10%`，并保留 triage / candidate 限制措辞。

最终 UI 另执行一次 M-01，验证 Markdown 标题、列表、结果表格和证据展开均正常。

## 浏览器验收

- 解决方案目录可搜索并打开 Cash Trading 参考方案。
- “新建解决方案”可展示从材料构建入口与材料指导。
- Package 总览、业务模型、指标与规则、知识图谱均可加载。
- 来源材料可打开 exact source Drawer，并真实预览 Excel Sheet/Cell；无浏览器 console error。
- Analytic Agent 可读取 Active Ontology 和样例数据并返回答案。
- 实机截图位于 `screenshots/`。

## 交付材料

- `Cash_Trading_Demo_使用手册.md`
- `../../output/pdf/Atlas_Ontology_Cash_Trading_Demo_使用手册.pdf`
- `Cash_Trading_E2E_Demo_操作流程.md`
- `Cash_Trading_Demo_问题与期望答案.md`
- `假设与补充记录.md`
- `source-manifest.json`

## 边界

- 数据为构造型样例，不是 HKEX 生产数据。
- Review Pack 是内部基线，不代表 Deloitte HK/HKEX 正式确认。
- Build 入口本次只用于演示，不在现场真实运行通用 Builder。
- EC2 发布不在本次本地验收内。
