-- Compiler-generated reference SQL for the constructed-synthetic Cash Trading case.
-- It is not External Reviewer/customer-provided SQL and does not establish production correctness.
-- Every provisional rule is linked to the versioned CT-ASM assumption register.

CREATE OR REPLACE TEMP VIEW cash_trade_analytics AS
WITH corrected_originals AS (
  SELECT DISTINCT reference_trading_activity_id AS trading_activity_id
  FROM trading_activity
  WHERE upper(trim(coalesce(is_correction, 'N'))) IN ('Y', 'TRUE', '1')
    AND reference_trading_activity_id IS NOT NULL
), effective_participant AS (
  SELECT
    t.trading_activity_id,
    a.participant_type,
    a.participant_status,
    row_number() OVER (
      PARTITION BY t.trading_activity_id
      ORDER BY a.valid_from_timestamp DESC NULLS LAST, a.participant_id
    ) AS match_rank
  FROM trading_activity AS t
  LEFT JOIN account_reference AS a
    ON upper(trim(a.participant_id)) = upper(trim(t.participant_id))
   AND (a.venue_code IS NULL OR upper(trim(a.venue_code)) = upper(trim(t.venue_code)))
   AND a.valid_from_timestamp <= t.transaction_timestamp
   AND (a.valid_to_timestamp IS NULL OR t.transaction_timestamp < a.valid_to_timestamp)
)
SELECT
  t.trading_activity_id,
  t.business_date,
  t.venue_code,
  t.market_segment,
  t.instrument_id,
  t.participant_id,
  t.buy_participant_id,
  t.sell_participant_id,
  t.trade_quantity,
  t.trade_notional AS trade_notional_hkd,
  t.base_notional_before_haircut AS base_notional_usd,
  t.transaction_timestamp,
  t.receive_timestamp,
  TRUE AS is_eligible_trade,
  coalesce(
    upper(trim(ep.participant_type)) = 'CLIENT'
      AND upper(trim(ep.participant_status)) = 'ACTIVE',
    FALSE
  ) AS is_active_client,
  t.buy_participant_id IS NOT NULL
    AND t.sell_participant_id IS NOT NULL AS has_both_participant_ids,
  t.buy_participant_id IS NOT NULL
    AND t.sell_participant_id IS NOT NULL
    AND upper(trim(t.buy_participant_id)) = upper(trim(t.sell_participant_id))
      AS is_potential_self_trade,
  date_diff('millisecond', t.transaction_timestamp, t.receive_timestamp) >= 0
    AS is_nonnegative_latency,
  date_diff('millisecond', t.transaction_timestamp, t.receive_timestamp)
    AS capture_latency_ms
FROM trading_activity AS t
LEFT JOIN corrected_originals AS c
  ON c.trading_activity_id = t.trading_activity_id
LEFT JOIN effective_participant AS ep
  ON ep.trading_activity_id = t.trading_activity_id
 AND ep.match_rank = 1
WHERE t.activity_type = 'TRADE'
  AND t.trade_status = 'ACTIVE'
  AND upper(trim(coalesce(t.is_correction, 'N'))) NOT IN ('Y', 'TRUE', '1')
  AND t.reference_trading_activity_id IS NULL
  AND c.trading_activity_id IS NULL;

CREATE OR REPLACE TEMP VIEW cash_order_lifecycle_analytics AS
WITH corrected_originals AS (
  SELECT DISTINCT reference_activity_id AS activity_id
  FROM order_activity
  WHERE upper(trim(coalesce(correction_indicator, 'N'))) IN ('Y', 'TRUE', '1')
    AND reference_activity_id IS NOT NULL
), eligible_events AS (
  SELECT o.*
  FROM order_activity AS o
  LEFT JOIN corrected_originals AS c
    ON c.activity_id = o.activity_id
  WHERE upper(trim(coalesce(o.correction_indicator, 'N'))) NOT IN ('Y', 'TRUE', '1')
    AND o.reference_activity_id IS NULL
    AND c.activity_id IS NULL
), effective_participant AS (
  SELECT
    o.activity_id,
    a.participant_type,
    a.participant_status,
    row_number() OVER (
      PARTITION BY o.activity_id
      ORDER BY a.valid_from_timestamp DESC NULLS LAST, a.participant_id
    ) AS match_rank
  FROM eligible_events AS o
  LEFT JOIN account_reference AS a
    ON upper(trim(a.participant_id)) = upper(trim(o.participant_id))
   AND (a.venue_code IS NULL OR upper(trim(a.venue_code)) = upper(trim(o.venue_code)))
   AND a.valid_from_timestamp <= o.transaction_timestamp
   AND (a.valid_to_timestamp IS NULL OR o.transaction_timestamp < a.valid_to_timestamp)
), ranked_events AS (
  SELECT
    concat(o.venue_code, '|', cast(o.trading_date AS VARCHAR), '|', o.order_id)
      AS lifecycle_key,
    o.*,
    coalesce(
      upper(trim(ep.participant_type)) = 'CLIENT'
        AND upper(trim(ep.participant_status)) = 'ACTIVE',
      FALSE
    ) AS is_client_event,
    CASE
      WHEN upper(trim(o.order_status)) = 'CANCELLED' THEN 'CANCELED'
      ELSE upper(trim(o.order_status))
    END AS canonical_order_status,
    CASE
      WHEN upper(trim(coalesce(o.execution_type, ''))) = 'CANCELLED' THEN 'CANCELED'
      ELSE upper(trim(coalesce(o.execution_type, '')))
    END AS canonical_execution_type,
    row_number() OVER (
      PARTITION BY o.venue_code, o.trading_date, o.order_id
      ORDER BY o.transaction_timestamp DESC, o.event_sequence_no DESC, o.activity_id DESC
    ) AS latest_rank
  FROM eligible_events AS o
  LEFT JOIN effective_participant AS ep
    ON ep.activity_id = o.activity_id
   AND ep.match_rank = 1
), lifecycle AS (
  SELECT
    lifecycle_key,
    trading_date,
    venue_code,
    max(CASE WHEN latest_rank = 1 THEN market_segment END) AS market_segment,
    max(CASE WHEN latest_rank = 1 THEN instrument_id END) AS instrument_id,
    max(CASE WHEN latest_rank = 1 THEN participant_id END) AS participant_id,
    bool_or(latest_rank = 1 AND is_client_event) AS is_client,
    bool_or(upper(trim(activity_type)) IN ('NEW', 'REJECT')) AS is_submitted,
    bool_or(
      upper(trim(activity_type)) = 'REJECT'
      OR canonical_order_status = 'REJECTED'
      OR canonical_execution_type = 'REJECTED'
    ) AS is_rejected,
    bool_or(
      upper(trim(activity_type)) = 'CANCEL'
      OR canonical_order_status = 'CANCELED'
      OR canonical_execution_type = 'CANCELED'
    ) AS is_canceled,
    bool_or(latest_rank = 1 AND canonical_order_status = 'FILLED') AS latest_is_filled,
    max(CASE WHEN latest_rank = 1 THEN order_quantity END) AS final_order_quantity,
    max(CASE WHEN latest_rank = 1 THEN cumulative_executed_quantity END)
      AS final_cumulative_executed_quantity
  FROM ranked_events
  GROUP BY lifecycle_key, trading_date, venue_code
)
SELECT
  lifecycle_key,
  trading_date,
  venue_code,
  market_segment,
  instrument_id,
  participant_id,
  is_client,
  is_submitted,
  is_rejected,
  is_client AND is_submitted AND NOT is_rejected AS is_eligible_client_order,
  is_client AND is_submitted AND NOT is_rejected AND latest_is_filled
    AS is_fully_filled,
  is_canceled,
  final_order_quantity,
  final_cumulative_executed_quantity
FROM lifecycle;

-- Seven non-latency source metrics. Percentages are returned on a 0-100 scale.
WITH order_control AS (
  SELECT
    count(DISTINCT lifecycle_key) FILTER (WHERE is_submitted) AS submitted_order_count,
    count(DISTINCT lifecycle_key) FILTER (WHERE is_rejected) AS rejected_order_count,
    sum(final_order_quantity) FILTER (WHERE is_submitted) AS submitted_order_quantity,
    sum(final_cumulative_executed_quantity) FILTER (WHERE is_submitted)
      AS executed_order_quantity,
    count(DISTINCT lifecycle_key) FILTER (WHERE is_eligible_client_order)
      AS eligible_client_order_count,
    count(DISTINCT lifecycle_key) FILTER (WHERE is_fully_filled)
      AS fully_filled_client_order_count,
    count(DISTINCT lifecycle_key) FILTER (WHERE is_canceled) AS canceled_order_count
  FROM cash_order_lifecycle_analytics
), trade_control AS (
  SELECT
    count(DISTINCT trading_activity_id) AS eligible_trade_count,
    sum(trade_quantity) FILTER (WHERE is_active_client) AS active_client_trade_quantity,
    sum(trade_notional_hkd) FILTER (WHERE is_active_client)
      AS active_client_trade_notional_hkd,
    count(DISTINCT trading_activity_id) FILTER (WHERE has_both_participant_ids)
      AS self_trade_eligible_trade_count,
    count(DISTINCT trading_activity_id) FILTER (WHERE is_potential_self_trade)
      AS potential_self_trade_count
  FROM cash_trade_analytics
)
SELECT
  o.submitted_order_count,
  o.rejected_order_count,
  100.0 * o.rejected_order_count / nullif(o.submitted_order_count, 0)
    AS order_rejection_rate_percent,
  o.submitted_order_quantity,
  o.executed_order_quantity,
  100.0 * o.executed_order_quantity / nullif(o.submitted_order_quantity, 0)
    AS order_fill_rate_percent,
  t.active_client_trade_quantity,
  t.active_client_trade_notional_hkd / 1000000.0 AS active_client_trading_volume_hkd_mn,
  o.eligible_client_order_count,
  o.fully_filled_client_order_count,
  100.0 * o.fully_filled_client_order_count / nullif(o.eligible_client_order_count, 0)
    AS client_order_completion_rate_percent,
  o.canceled_order_count,
  100.0 * o.canceled_order_count / nullif(t.eligible_trade_count, 0)
    AS cancel_to_trade_ratio_percent,
  t.eligible_trade_count * 2 AS order_to_trade_denominator,
  100.0 * o.submitted_order_count / nullif(t.eligible_trade_count * 2, 0)
    AS order_to_trade_ratio_percent,
  t.self_trade_eligible_trade_count,
  t.potential_self_trade_count,
  100.0 * t.potential_self_trade_count
    / nullif(t.self_trade_eligible_trade_count, 0) AS potential_self_trade_rate_percent
FROM order_control AS o
CROSS JOIN trade_control AS t;

-- Trade capture latency; DuckDB quantile_disc implements nearest-rank values.
SELECT
  count(*) FILTER (WHERE is_nonnegative_latency) AS eligible_latency_count,
  count(*) FILTER (WHERE NOT is_nonnegative_latency) AS negative_latency_count,
  min(capture_latency_ms) FILTER (WHERE is_nonnegative_latency) AS minimum_ms,
  quantile_disc(capture_latency_ms, 0.50) FILTER (WHERE is_nonnegative_latency) AS p50_ms,
  quantile_disc(capture_latency_ms, 0.95) FILTER (WHERE is_nonnegative_latency) AS p95_ms,
  quantile_disc(capture_latency_ms, 0.99) FILTER (WHERE is_nonnegative_latency) AS p99_ms,
  max(capture_latency_ms) FILTER (WHERE is_nonnegative_latency) AS maximum_ms
FROM cash_trade_analytics;
