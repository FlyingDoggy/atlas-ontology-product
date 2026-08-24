# Cash Trading Analytic Agent：问题与期望答案

## 使用说明

- 数据期间：2026-08-03 至 2026-08-07；2026-08-05 为非交易日。
- 数据性质：构造型样例数据，不是 HKEX 生产数据。
- 数值由 Ontology Package 中的指标定义和确定性查询工具计算；DeepAgent 负责理解问题、选工具和解释。
- 明日 Deloitte HK 提供的新问题应追加为新的验收用例，不覆盖本文件中的基线。

## 八项基线问题

### Q1 — Order Rejection Rate

问题：`What was the order rejection rate from 2026-08-03 to 2026-08-07?`

期望事实：

- Rejected orders：200
- Submitted orders：1,200
- Order rejection rate：16.666667%
- Metric：`metric.order_rejection_rate`（M-01）

### Q2 — Order Fill Rate

问题：`What was the order fill rate from 2026-08-03 to 2026-08-07?`

期望事实：

- Executed order quantity：0
- Submitted order quantity：5,064,000
- Order fill rate：0%
- Metric：`metric.order_fill_rate`（M-02）
- 必须说明：样例 EXECUTE 事件无法可靠关联到 NEW 生命周期，因此该 0% 受数据关系缺口影响，不能解释为市场没有成交。

### Q3 — Trade Capture Latency

问题：`What were p50, p95 and p99 trade capture latency from 2026-08-03 to 2026-08-07?`

期望事实：

- Eligible records：200
- Minimum：3 ms
- P50：9 ms
- P95：15 ms
- P99：15 ms
- Maximum：15 ms
- Negative latency records：0
- Metric：`metric.trade_capture_latency_ms`（M-03）

### Q4 — Active Client Trading Volume

问题：`What was active client trading volume from 2026-08-03 to 2026-08-07?`

期望事实：

- Trade quantity：1,500
- Native notional：HKD 52,235
- USD pre-haircut notional：USD 6,678.36426
- Active clients：3
- Published KPI value：0.052235 HKD million
- Metric：`metric.active_client_trading_volume`（M-04）
- 必须把 HKD 和 USD pre-haircut 明确分开。

### Q5 — Client Order Completion Rate

问题：`What was the client order completion rate from 2026-08-03 to 2026-08-07?`

期望事实：

- Fully filled client orders：0
- Eligible client orders：150
- Completion rate：0%
- Metric：`metric.client_order_completion_rate`（M-05）
- 必须说明与 Q2 相同的生命周期关联缺口。

### Q6 — Cancel-to-Trade Ratio

问题：`What was the cancel-to-trade ratio from 2026-08-03 to 2026-08-07?`

期望事实：

- Canceled order lifecycles：300
- Eligible trades：200
- Ratio：150%
- Metric：`metric.cancel_to_trade_ratio`（M-06）

### Q7 — Order-to-Trade Ratio

问题：`What was the order-to-trade ratio from 2026-08-03 to 2026-08-07?`

期望事实：

- Submitted orders：1,200
- Eligible trades：200
- Ratio：300%
- Formula：`submitted orders / (2 × eligible trades)`
- Metric：`metric.order_to_trade_ratio`（M-07）

### Q8 — Potential Self-Trade Daily Trend

问题：`Show the daily potential self-trade rate from 2026-08-03 to 2026-08-07.`

期望事实：

| 日期 | Potential self-trade rate |
| --- | ---: |
| 2026-08-03 | 10% |
| 2026-08-04 | 10% |
| 2026-08-06 | 10% |
| 2026-08-07 | 10% |

全期间：20 个候选 / 200 个 eligible trades = 10%。Metric 为 `metric.potential_self_trade_rate`（M-08）。必须使用“potential / candidate / triage”措辞，不能断言 misconduct、market abuse 或违规。

## 可选开放问题

以下问题用于观察 DeepAgent 的规划能力，不作为当前固定数值回归门禁：

1. `Compare the order rejection rate, cancel-to-trade ratio and order-to-trade ratio for the sample period. What should an operations team examine first?`
2. `Which Cash Trading metrics in this package have material data-quality limitations? Explain the limitation and its impact.`
3. `What ontology sources and decisions support the potential self-trade rate?`
4. `Explain how active client trading volume distinguishes native HKD notional from USD pre-haircut notional.`

## 判定失败的回答

- 数值与以上确定性结果不一致。
- 没有工具调用或证据，却给出新的业务数值。
- 把构造型样例说成 HKEX 真实数据。
- 把 Review Pack 当成 Deloitte HK/HKEX 已确认结论。
- 把 potential self-trade 说成违法、操纵或违规事实。
- 对 M-02 / M-05 只说 0%，不披露 EXECUTE-to-NEW 关联缺口。
