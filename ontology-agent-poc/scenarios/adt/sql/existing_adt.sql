-- Synthetic existing SQL supplied as reference evidence.
-- The ontology compiler does not execute this file directly; it parses/reconciles
-- its intent against confirmed metric rules and physical mappings.
WITH eligible_trade AS (
    SELECT
        c.period_id,
        t.executed_value_hkd_mn
    FROM trade_fact AS t
    JOIN trading_calendar AS c
      ON t.market_id = c.market_id
     AND t.trade_date = c.calendar_date
    WHERE t.status = 'EXECUTED'
      AND t.cancellation_flag = FALSE
      AND c.period_id IN ('2025-Q3', '2025-Q4')
),
turnover AS (
    SELECT period_id, SUM(executed_value_hkd_mn) AS turnover_hkd_mn
    FROM eligible_trade
    GROUP BY period_id
),
trading_days AS (
    SELECT period_id, COUNT(DISTINCT calendar_date) AS trading_day_count
    FROM trading_calendar
    WHERE is_trading_day = TRUE
      AND period_id IN ('2025-Q3', '2025-Q4')
    GROUP BY period_id
)
SELECT
    t.period_id,
    t.turnover_hkd_mn,
    d.trading_day_count,
    t.turnover_hkd_mn / NULLIF(d.trading_day_count, 0) AS adt_hkd_mn
FROM turnover AS t
JOIN trading_days AS d USING (period_id)
ORDER BY t.period_id;
