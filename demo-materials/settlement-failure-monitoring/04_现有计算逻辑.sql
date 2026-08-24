-- Securities Settlement Failure Monitoring
-- Synthetic reference SQL for Ontology Studio E2E demonstration only.
-- Dialect: PostgreSQL 17
-- Bind parameter: :snapshot_date (DATE)

WITH eligible AS (
    SELECT
        s.*,
        (
            s.market_type = 'EXCHANGE_TRADED_EQUITY'
            AND s.settlement_date <= s.snapshot_date
            AND s.status <> 'CANCELLED'
        ) AS is_due,
        (
            s.market_type = 'EXCHANGE_TRADED_EQUITY'
            AND s.settlement_date <= s.snapshot_date
            AND s.status <> 'CANCELLED'
            AND s.remaining_quantity > 0
            AND s.status IN ('PENDING', 'PARTIALLY_SETTLED', 'FAILED')
        ) AS is_active_fail
    FROM settlement_instruction_snapshot AS s
    WHERE s.snapshot_date = :snapshot_date
),
valued AS (
    SELECT
        e.*,
        p.close_price,
        fx.hkd_rate,
        CASE
            WHEN e.is_active_fail
             AND p.close_price IS NOT NULL
             AND fx.hkd_rate IS NOT NULL
            THEN e.remaining_quantity * p.close_price * fx.hkd_rate
            ELSE NULL
        END AS outstanding_hkd_amount
    FROM eligible AS e
    LEFT JOIN daily_price AS p
      ON p.business_date = e.snapshot_date
     AND p.instrument_id = e.instrument_id
     AND p.currency = e.settlement_currency
    LEFT JOIN (
        SELECT
            rate_date,
            from_currency,
            MAX(CASE WHEN to_currency = 'HKD' THEN rate END) AS hkd_rate
        FROM fx_rate
        GROUP BY rate_date, from_currency
    ) AS fx
      ON fx.rate_date = e.snapshot_date
     AND fx.from_currency = e.settlement_currency
),
aged AS (
    SELECT
        v.*,
        CASE
            WHEN v.is_active_fail AND v.first_failed_date IS NOT NULL
            THEN (
                SELECT COUNT(*)
                FROM trading_calendar AS c
                WHERE c.calendar_date > v.first_failed_date
                  AND c.calendar_date <= v.snapshot_date
                  AND c.is_business_day = TRUE
            )
            ELSE NULL
        END AS fail_age_business_days
    FROM valued AS v
),
participant_amount AS (
    SELECT
        participant_id,
        SUM(outstanding_hkd_amount) AS participant_outstanding_hkd
    FROM aged
    WHERE is_active_fail
      AND outstanding_hkd_amount IS NOT NULL
    GROUP BY participant_id
),
ranked_participant AS (
    SELECT
        participant_id,
        participant_outstanding_hkd,
        DENSE_RANK() OVER (ORDER BY participant_outstanding_hkd DESC) AS amount_rank
    FROM participant_amount
),
snapshot_metrics AS (
    SELECT
        :snapshot_date::date AS snapshot_date,
        COUNT(DISTINCT instruction_id) FILTER (WHERE is_due) AS due_instruction_count,
        COUNT(DISTINCT instruction_id) FILTER (WHERE is_active_fail) AS active_fail_count,
        SUM(outstanding_hkd_amount) FILTER (WHERE is_active_fail) AS active_fail_outstanding_hkd,
        AVG(fail_age_business_days::numeric) FILTER (
            WHERE is_active_fail AND fail_age_business_days IS NOT NULL
        ) AS average_active_fail_age_bd,
        COUNT(*) FILTER (
            WHERE is_active_fail AND (close_price IS NULL OR hkd_rate IS NULL)
        ) AS unvalued_active_fail_count
    FROM aged
),
concentration AS (
    SELECT
        SUM(participant_outstanding_hkd) FILTER (WHERE amount_rank <= 3)
            / NULLIF(SUM(participant_outstanding_hkd), 0) AS top3_participant_fail_amount_share
    FROM ranked_participant
)
SELECT
    m.snapshot_date,
    m.due_instruction_count,
    m.active_fail_count,
    m.active_fail_count::numeric / NULLIF(m.due_instruction_count, 0) AS settlement_fail_rate,
    m.active_fail_outstanding_hkd,
    m.average_active_fail_age_bd,
    m.unvalued_active_fail_count,
    c.top3_participant_fail_amount_share
FROM snapshot_metrics AS m
CROSS JOIN concentration AS c;

-- M-06 uses first_failed_date as the cohort date and a Hong Kong business-day calendar.
WITH failed_cohort AS (
    SELECT DISTINCT
        s.instruction_id,
        s.participant_id,
        s.instrument_id,
        s.fail_reason_code,
        s.first_failed_date,
        s.fully_settled_date
    FROM settlement_instruction_snapshot AS s
    WHERE s.snapshot_date = :snapshot_date
      AND s.market_type = 'EXCHANGE_TRADED_EQUITY'
      AND s.settlement_date <= s.snapshot_date
      AND s.status <> 'CANCELLED'
      AND s.first_failed_date IS NOT NULL
),
recovery AS (
    SELECT
        f.*,
        CASE
            WHEN f.fully_settled_date IS NULL THEN NULL
            ELSE (
                SELECT COUNT(*)
                FROM trading_calendar AS c
                WHERE c.calendar_date > f.first_failed_date
                  AND c.calendar_date <= f.fully_settled_date
                  AND c.is_business_day = TRUE
            )
        END AS recovery_business_days
    FROM failed_cohort AS f
)
SELECT
    first_failed_date AS cohort_date,
    COUNT(*) AS failed_cohort_count,
    COUNT(*) FILTER (WHERE recovery_business_days <= 2) AS recovered_within_2bd_count,
    COUNT(*) FILTER (WHERE recovery_business_days <= 2)::numeric
        / NULLIF(COUNT(*), 0) AS recovery_within_2bd_rate
FROM recovery
GROUP BY first_failed_date
ORDER BY first_failed_date;
