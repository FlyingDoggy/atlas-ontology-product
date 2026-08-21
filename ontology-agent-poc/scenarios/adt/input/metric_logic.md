# ADT 分析场景——指标逻辑（Reference Example）

> 每行代表一个指标或一个需要独立治理的计算结果。公式只使用下表已定义的指标/字段。

| ID | 指标名称 | 业务定义 | 计算逻辑 | 过滤/范围 | 粒度与可切分维度 | 单位 | 空值/除零 | 主要来源 | 状态/备注 |
|---|---|---|---|---|---|---|---|---|---|
| M-01 | 合资格成交额 | 指定期间内满足成交资格规则的执行成交额总和 | `SUM(executed_value_hkd_mn)` | `status='EXECUTED' AND cancellation_flag=false`；通过交易日历绑定指定期间 | 市场-期间；可按板块 | HKD_MN | 金额或关键字段为空则校验失败 | metric logic、data dictionary、existing SQL | confirmed |
| M-02 | 交易日数 | 指定期间内获批准交易日的去重日期数 | `COUNT(DISTINCT calendar_date)` | `is_trading_day=true`；来自日历，不从成交事实推断 | 市场-期间 | TRADING_DAY_COUNT | 0 时拒绝 ADT | metric logic、calendar | confirmed；半日市按 1 天 |
| M-03 | 平均每日成交额（ADT） | 同期间的合资格成交额除以交易日数 | `M-01 / M-02` | 分子分母必须来自同一市场、期间和发布快照 | 市场-期间；板块 ADT 只共享市场日历分母 | HKD_MN_PER_TRADING_DAY | 分母为 0 时拒绝 | M-01、M-02 | confirmed |
| M-04 | ADT 变化 | 当前期 ADT 与基期 ADT 的差额和相对变化 | `ADT_current - ADT_previous`; `delta / ADT_previous` | 必须明确两个不重叠期间 | 两期间比较 | HKD_MN_PER_TRADING_DAY、% | 基期为 0 时百分比拒绝 | M-03 | confirmed |
| M-05 | 板块净变化贡献 | 某板块成交额变化占总体成交额变化的比例 | `(segment_current-segment_previous)/(total_current-total_previous)` | 所有板块必须完整对账；总变化不能为 0 | 板块-两期间 | % | 总变化为 0 时拒绝 | M-01、segment mapping | confirmed；这是净变化份额，不是 Q4 占比 |
| M-06 | 交易日效应 | 先固定基期日均成交额，计算交易日数变化带来的成交额变化 | `(D_current-D_previous) * ADT_previous` | 两期间、相同市场和快照 | 两期间 | HKD_MN | 任一输入缺失则失败 | M-02、M-03 | confirmed；顺序法、非因果 |
| M-07 | 活跃度效应 | 在当前期交易日数下，计算日均成交额变化带来的成交额变化 | `(ADT_current-ADT_previous) * D_current` | 两期间、相同市场和快照 | 两期间 | HKD_MN | 任一输入缺失则失败 | M-02、M-03 | confirmed；顺序法、非因果 |
| M-08 | 分解残差 | 验证两项效应能否闭合到总成交额变化 | `turnover_delta - M-06 - M-07` | 绝对值需在容差内 | 两期间 | HKD_MN | 超容差则失败 | M-01、M-06、M-07 | confirmed；参考数据应为 0 |

## 需要业务方特别说明的内容

- 指标名称相同但公式、范围、日历或单位不同的版本必须拆开写，不能在备注中含糊处理。
- 如果 SQL 与文字定义不一致，请描述实际报告当前采用哪一种，并把冲突保留给双方确认，不要自行“修正”。
- 任何异常日、停市、半日市、冲销、补录、币种换算或重算规则，都应写成单独规则或待确认项。

