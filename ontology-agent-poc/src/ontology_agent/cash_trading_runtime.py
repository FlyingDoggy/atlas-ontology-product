from __future__ import annotations

import json
import math
import re
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Mapping

import duckdb

from .contracts import PublicationError, VerifiedSnapshot
from .io import sha256_value, write_json
from .models import (
    AnalysisPlan,
    AnalysisResponse,
    AtomicQueryContract,
    EvidenceRecord,
    OntologyPackage,
    PeriodDefinition,
    PlanStep,
    StepExecution,
)
from .runtime_snapshot import verify_snapshot_handle
from .scenario import BoundAnalysisGoal
from .sql_compiler import CompiledQuery


CASH_OPERATOR_VERSION = "1.0.0"
_DATA_START = date(2026, 8, 3)
_DATA_END = date(2026, 8, 9)
_DETAIL_ROLES = {"MarketSurveillanceDemo", "TradingDemo"}
_AGGREGATE_ROLES = {*_DETAIL_ROLES, "MarketsDemo"}
_LIMITATIONS = (
    "Constructed-synthetic data and provisional rules; not HKEX validated.",
    "Potential self-trade is a deterministic triage candidate, not a misconduct conclusion.",
    "Observed order-event timelines may be incomplete and do not reconstruct missing events.",
)


class CashTradingAnalysisFailure(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CashRequest:
    intent: Literal[
        "anomaly_triage",
        "time_series",
        "timeline_evidence",
        "latency_profile",
        "evidence_audit",
    ]
    start: date | None
    end: date | None
    participant_id: str | None = None


def _boundary(
    status: Literal["CLARIFY", "REFUSED"], answer: str, code: str
) -> AnalysisResponse:
    return AnalysisResponse(status=status, answer=answer, boundary_code=code)


def _is_chinese(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", value))


def _extract_dates(question: str) -> tuple[date, ...]:
    found: list[date] = []
    for year, month, day in re.findall(r"(20\d{2})-(\d{1,2})-(\d{1,2})", question):
        try:
            candidate = date(int(year), int(month), int(day))
        except ValueError:
            continue
        if candidate not in found:
            found.append(candidate)

    chinese = list(
        re.finditer(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", question)
    )
    for match in chinese:
        try:
            candidate = date(
                int(match.group(1)), int(match.group(2)), int(match.group(3))
            )
        except ValueError:
            continue
        if candidate not in found:
            found.append(candidate)
    if chinese:
        year = int(chinese[0].group(1))
        tail = question[chinese[0].end() :]
        for month, day in re.findall(r"(?<!年)(\d{1,2})月(\d{1,2})日", tail):
            try:
                candidate = date(year, int(month), int(day))
            except ValueError:
                continue
            if candidate not in found:
                found.append(candidate)
    return tuple(sorted(found))


def resolve_cash_request(
    package: OntologyPackage,
    question: str,
    role: str,
    bound_intent: str | None = None,
) -> CashRequest | AnalysisResponse:
    if role not in _AGGREGATE_ROLES:
        return _boundary(
            "REFUSED",
            f"Role {role} is not permitted to use this constructed-synthetic scenario.",
            "ROLE_DENIED",
        )
    lower = question.lower()
    if any(
        term in lower
        for term in (
            "market abuse",
            "misconduct",
            "committed abuse",
            "prove that",
            "操纵市场",
            "市场滥用",
            "违规结论",
            "证明其违规",
        )
    ):
        return _boundary(
            "REFUSED",
            "This scenario can identify provisional triage candidates and evidence, but cannot establish misconduct or market abuse.",
            "UNSUPPORTED_MISCONDUCT_CONCLUSION",
        )

    supported_intents = {
        "anomaly_triage",
        "time_series",
        "timeline_evidence",
        "latency_profile",
    }
    if bound_intent is not None and bound_intent not in supported_intents:
        return _boundary(
            "REFUSED",
            "The grounded goal does not match an executable Cash Trading pattern.",
            "BOUND_GOAL_DENIED",
        )
    if bound_intent is not None:
        intent = bound_intent
    elif any(term in lower for term in ("definition", "evidence behind", "governed", "定义", "口径", "依据")):
        return CashRequest(intent="evidence_audit", start=None, end=None)
    elif any(term in lower for term in ("latency", "p50", "p95", "p99", "延迟", "时延")):
        intent = "latency_profile"
    elif any(term in lower for term in ("timeline", "event sequence", "生命周期", "时间线")):
        intent = "timeline_evidence"
    elif any(term in lower for term in ("trend", "daily", "by day", "趋势", "每天", "逐日")):
        intent = "time_series"
    elif any(term in lower for term in ("self-trade", "self trade", "自成交")):
        intent = "anomaly_triage"
    else:
        return _boundary(
            "REFUSED",
            "The question does not match a registered Cash Trading analysis pattern.",
            "UNSUPPORTED_INTENT",
        )

    if intent == "timeline_evidence" and role not in _DETAIL_ROLES:
        return _boundary(
            "REFUSED",
            "This role may use aggregate results but not participant or event-level evidence.",
            "DETAIL_GRAIN_DENIED",
        )
    participant_match = re.search(r"\bPART\d{3}\b", question.upper())
    participant_id = participant_match.group(0) if participant_match else None
    if intent == "timeline_evidence" and participant_id is None:
        return _boundary(
            "CLARIFY",
            "Please specify the synthetic participant ID for the evidence timeline.",
            "MISSING_PARTICIPANT",
        )

    dates = _extract_dates(question)
    if not dates:
        return _boundary(
            "CLARIFY",
            "Please specify a business date or date range within the scenario window.",
            "MISSING_TIME_RANGE",
        )
    start, end = dates[0], dates[-1]
    scenario_start = package.scenario.data_window_start
    scenario_end = package.scenario.data_window_end
    if start < scenario_start or end > scenario_end:
        return _boundary(
            "CLARIFY",
            f"The requested range is outside the available scenario window {scenario_start} to {scenario_end}.",
            "UNKNOWN_TIME_RANGE",
        )
    if (end - start).days > 92:
        return _boundary(
            "REFUSED",
            "The demo policy limits a single surveillance request to three months.",
            "TIME_RANGE_DENIED",
        )
    return CashRequest(
        intent=intent,
        start=start,
        end=end,
        participant_id=participant_id,
    )


class CashTradingDuckDB:
    """Bounded DuckDB façade; it never executes package- or user-supplied SQL."""

    def __init__(self, resource_paths: Mapping[str, Path]):
        self.resource_paths = {key: value.resolve() for key, value in resource_paths.items()}
        self.connection = duckdb.connect(":memory:")
        self._register_sources()

    def _register_sources(self) -> None:
        table_sources = {
            "order_activity": "source.order_activity",
            "trading_activity": "source.trading_activity",
            "instrument_reference": "source.instrument_reference",
            "account_reference": "source.account_reference",
            "trading_calendar": "source.trading_calendar",
            "order_type_reference": "source.order_type_reference",
            "exchange_rate": "source.exchange_rate",
        }
        for table, source_id in table_sources.items():
            path = self.resource_paths.get(source_id)
            if path is None or not path.is_file() or path.suffix.lower() != ".parquet":
                raise CashTradingAnalysisFailure(
                    f"No verified Parquet resource is bound for {source_id}"
                )
            self.connection.read_parquet(str(path)).create_view(table)
        self.connection.execute(
            """
            CREATE VIEW cash_trade_analytics AS
            WITH corrected_originals AS (
              SELECT DISTINCT reference_trading_activity_id AS id
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
              t.trade_id,
              t.buy_order_id,
              t.sell_order_id,
              t.trade_quantity,
              t.trade_notional AS trade_notional_hkd,
              t.base_notional_before_haircut AS base_notional_usd,
              t.transaction_timestamp,
              t.receive_timestamp,
              ep.participant_type,
              TRUE AS is_eligible_trade,
              coalesce(
                upper(trim(ep.participant_type)) = 'CLIENT'
                  AND upper(trim(ep.participant_status)) = 'ACTIVE',
                FALSE
              ) AS is_active_client,
              t.buy_participant_id IS NOT NULL AND t.sell_participant_id IS NOT NULL
                AS has_both_participant_ids,
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
              ON c.id = t.trading_activity_id
            LEFT JOIN effective_participant AS ep
              ON ep.trading_activity_id = t.trading_activity_id
             AND ep.match_rank = 1
            WHERE t.activity_type = 'TRADE'
              AND t.trade_status = 'ACTIVE'
              AND upper(trim(coalesce(t.is_correction, 'N'))) NOT IN ('Y', 'TRUE', '1')
              AND t.reference_trading_activity_id IS NULL
              AND c.id IS NULL
            """
        )
        self.connection.execute(
            """
            CREATE VIEW cash_order_lifecycle_analytics AS
            WITH corrected_originals AS (
              SELECT DISTINCT reference_activity_id AS id
              FROM order_activity
              WHERE upper(trim(coalesce(correction_indicator, 'N'))) IN ('Y', 'TRUE', '1')
                AND reference_activity_id IS NOT NULL
            ), eligible_events AS (
              SELECT o.*
              FROM order_activity AS o
              LEFT JOIN corrected_originals AS c
                ON c.id = o.activity_id
              WHERE upper(trim(coalesce(o.correction_indicator, 'N'))) NOT IN ('Y', 'TRUE', '1')
                AND c.id IS NULL
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
                ep.participant_type AS participant_type,
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
                max(CASE WHEN latest_rank = 1 THEN participant_type END) AS participant_type,
                max(CASE WHEN latest_rank = 1 THEN order_type END) AS order_type,
                max(CASE WHEN latest_rank = 1 THEN session_phase END) AS session_phase,
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
                bool_or(latest_rank = 1 AND canonical_order_status = 'FILLED')
                  AS latest_is_filled,
                max(CASE WHEN latest_rank = 1 THEN order_quantity END)
                  AS final_order_quantity,
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
              participant_type,
              order_type,
              session_phase,
              is_client,
              is_submitted,
              is_rejected,
              is_client AND is_submitted AND NOT is_rejected AS is_eligible_client_order,
              is_client AND is_submitted AND NOT is_rejected AND latest_is_filled
                AS is_fully_filled,
              is_canceled,
              final_order_quantity,
              final_cumulative_executed_quantity
            FROM lifecycle
            """
        )

    def execute(self, query: CompiledQuery) -> list[dict[str, Any]]:
        cursor = self.connection.execute(query.sql, list(query.params))
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> CashTradingDuckDB:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _query(
    operation: str,
    sql: str,
    params: tuple[Any, ...],
    metrics: tuple[str, ...],
    mappings: tuple[str, ...],
    sources: tuple[str, ...],
) -> CompiledQuery:
    return CompiledQuery(
        operation=operation,
        sql=sql.strip(),
        params=params,
        metric_ids=metrics,
        mapping_ids=mappings,
        source_ids=sources,
    )


def _summary_query(start: date, end: date) -> CompiledQuery:
    return _query(
        "CashSelfTradeSummary",
        """
        SELECT
          count(DISTINCT trading_activity_id) FILTER (WHERE has_both_participant_ids)
            AS eligible_trade_count,
          count(DISTINCT trading_activity_id) FILTER (WHERE is_potential_self_trade)
            AS candidate_trade_count,
          100.0 * count(DISTINCT trading_activity_id) FILTER (WHERE is_potential_self_trade)
            / nullif(count(DISTINCT trading_activity_id) FILTER (WHERE has_both_participant_ids), 0)
            AS candidate_rate_percent,
          count(DISTINCT buy_participant_id) FILTER (WHERE is_potential_self_trade)
            AS candidate_participant_count,
          count(DISTINCT instrument_id) FILTER (WHERE is_potential_self_trade)
            AS candidate_instrument_count
        FROM cash_trade_analytics
        WHERE business_date BETWEEN ? AND ?
        """,
        (start, end),
        (
            "metric.self_trade_eligible_trade_count",
            "metric.potential_self_trade_count",
            "metric.potential_self_trade_rate",
        ),
        (
            "binding.trade.id",
            "binding.trade.business_date",
            "binding.trade.has_both_participants",
            "binding.trade.self_trade",
        ),
        ("source.cash_trade_analytics",),
    )


def _candidate_breakdown_query(start: date, end: date) -> CompiledQuery:
    return _query(
        "CashSelfTradeBreakdown",
        """
        SELECT buy_participant_id AS participant_id, instrument_id,
               count(DISTINCT trading_activity_id) AS candidate_trade_count
        FROM cash_trade_analytics
        WHERE business_date BETWEEN ? AND ? AND is_potential_self_trade
        GROUP BY buy_participant_id, instrument_id
        ORDER BY candidate_trade_count DESC, participant_id, instrument_id
        """,
        (start, end),
        ("metric.potential_self_trade_count",),
        (
            "binding.trade.business_date",
            "binding.trade.participant",
            "binding.trade.instrument",
            "binding.trade.self_trade",
        ),
        ("source.cash_trade_analytics",),
    )


def _trend_query(start: date, end: date) -> CompiledQuery:
    return _query(
        "CashSelfTradeDailyTrend",
        """
        SELECT business_date,
               count(DISTINCT trading_activity_id) FILTER (WHERE has_both_participant_ids)
                 AS eligible_trade_count,
               count(DISTINCT trading_activity_id) FILTER (WHERE is_potential_self_trade)
                 AS candidate_trade_count,
               100.0 * count(DISTINCT trading_activity_id) FILTER (WHERE is_potential_self_trade)
                 / nullif(count(DISTINCT trading_activity_id) FILTER (WHERE has_both_participant_ids), 0)
                 AS candidate_rate_percent
        FROM cash_trade_analytics
        WHERE business_date BETWEEN ? AND ?
        GROUP BY business_date
        ORDER BY business_date
        """,
        (start, end),
        (
            "metric.self_trade_eligible_trade_count",
            "metric.potential_self_trade_count",
            "metric.potential_self_trade_rate",
        ),
        (
            "binding.trade.business_date",
            "binding.trade.has_both_participants",
            "binding.trade.self_trade",
        ),
        ("source.cash_trade_analytics",),
    )


def _latency_query(start: date, end: date) -> CompiledQuery:
    return _query(
        "CashTradeLatencyProfile",
        """
        SELECT
          count(*) FILTER (WHERE capture_latency_ms >= 0) AS eligible_latency_count,
          count(*) FILTER (WHERE capture_latency_ms < 0) AS negative_latency_count,
          min(capture_latency_ms) FILTER (WHERE capture_latency_ms >= 0) AS minimum_ms,
          quantile_disc(capture_latency_ms, 0.50) FILTER (WHERE capture_latency_ms >= 0) AS p50_ms,
          quantile_disc(capture_latency_ms, 0.95) FILTER (WHERE capture_latency_ms >= 0) AS p95_ms,
          quantile_disc(capture_latency_ms, 0.99) FILTER (WHERE capture_latency_ms >= 0) AS p99_ms,
          max(capture_latency_ms) FILTER (WHERE capture_latency_ms >= 0) AS maximum_ms
        FROM cash_trade_analytics
        WHERE business_date BETWEEN ? AND ?
          AND transaction_timestamp IS NOT NULL
          AND receive_timestamp IS NOT NULL
        """,
        (start, end),
        ("metric.trade_capture_latency_ms",),
        (
            "binding.trade.business_date",
            "binding.trade.transaction_timestamp",
            "binding.trade.receive_timestamp",
            "binding.trade.capture_latency",
        ),
        ("source.cash_trade_analytics",),
    )


def _timeline_queries(
    start: date, end: date, participant_id: str
) -> tuple[CompiledQuery, CompiledQuery]:
    trades = _query(
        "CashSelfTradeCandidateEvents",
        """
        SELECT trading_activity_id, business_date,
               strftime(transaction_timestamp, '%Y-%m-%dT%H:%M:%S.%fZ') AS event_timestamp,
               'TRADE' AS event_type, trade_id, buy_order_id, sell_order_id,
               instrument_id, buy_participant_id AS participant_id
        FROM cash_trade_analytics
        WHERE business_date BETWEEN ? AND ?
          AND is_potential_self_trade
          AND upper(trim(buy_participant_id)) = ?
        ORDER BY event_timestamp, trading_activity_id
        """,
        (start, end, participant_id.upper()),
        ("metric.potential_self_trade_count",),
        (
            "binding.trade.business_date",
            "binding.trade.participant",
            "binding.trade.self_trade",
        ),
        ("source.cash_trade_analytics",),
    )
    orders = _query(
        "CashLinkedOrderEvents",
        """
        WITH selected_orders AS (
          SELECT DISTINCT order_id
          FROM (
            SELECT buy_order_id AS order_id
            FROM cash_trade_analytics
            WHERE business_date BETWEEN ? AND ? AND is_potential_self_trade
              AND upper(trim(buy_participant_id)) = ?
            UNION ALL
            SELECT sell_order_id AS order_id
            FROM cash_trade_analytics
            WHERE business_date BETWEEN ? AND ? AND is_potential_self_trade
              AND upper(trim(sell_participant_id)) = ?
          )
          WHERE order_id IS NOT NULL
        ), lifecycle AS (
          SELECT o.*,
                 max(CASE WHEN upper(o.activity_type) = 'NEW' THEN 1 ELSE 0 END)
                   OVER (PARTITION BY o.venue_code, o.trading_date, o.order_id)
                   AS has_new
          FROM order_activity AS o
          INNER JOIN selected_orders AS s ON s.order_id = o.order_id
        )
        SELECT activity_id, trading_date AS business_date,
               strftime(transaction_timestamp, '%Y-%m-%dT%H:%M:%S.%fZ') AS event_timestamp,
               activity_type AS event_type,
               trade_id, order_id, instrument_id, participant_id,
               has_new = 1 AS observed_lifecycle_complete
        FROM lifecycle
        ORDER BY event_timestamp, event_sequence_no, activity_id
        """,
        (start, end, participant_id.upper(), start, end, participant_id.upper()),
        ("metric.potential_self_trade_count",),
        ("binding.trade.business_date", "binding.trade.participant"),
        ("source.order_activity", "source.cash_trade_analytics"),
    )
    return trades, orders


def _plan(
    package: OntologyPackage,
    request: CashRequest,
    question: str,
    role: str,
    snapshot_checksum: str,
) -> AnalysisPlan:
    patterns = {item.intent: item for item in package.analysis_patterns}
    pattern = patterns[request.intent]
    metric = pattern.required_metrics[-1]
    policy_id = (
        "policy.cash_markets_demo"
        if role == "MarketsDemo"
        else "policy.cash_surveillance_demo"
    )
    period_id = (
        "definition-only"
        if request.start is None
        else f"{request.start.isoformat()}..{request.end.isoformat()}"
    )
    bounds = (
        ()
        if request.start is None or request.end is None
        else (
            PeriodDefinition(
                id=period_id,
                start=request.start,
                end=request.end,
                inclusive=True,
            ),
        )
    )
    result_grain = {
        "anomaly_triage": ("aggregate",),
        "time_series": ("daily",),
        "timeline_evidence": ("trade_event", "order_event"),
        "latency_profile": ("aggregate",),
        "evidence_audit": ("definition",),
    }[request.intent]
    sources = (
        ("source.cash_trade_analytics", "source.order_activity")
        if request.intent == "timeline_evidence"
        else ("source.cash_trade_analytics",)
    )
    policy_decision_id = "policy-decision." + sha256_value(
        {
            "policy": policy_id,
            "role": role,
            "intent": request.intent,
            "period": period_id,
            "participant": request.participant_id,
            "snapshot": snapshot_checksum,
        }
    )[:16]
    payload = {
        "operation": pattern.operation,
        "operator_version": CASH_OPERATOR_VERSION,
        "analysis_pattern": pattern.id,
        "scenario_id": package.scenario.id,
        "metric": metric,
        "periods": (period_id,),
        "period_bounds": bounds,
        "dimensions": tuple(pattern.required_dimensions),
        "result_grain": result_grain,
        "filters": tuple(
            dict.fromkeys(
                rule
                for required_metric in pattern.required_metrics
                for rule in next(
                    item for item in package.metrics if item.id == required_metric
                ).query.filters
            )
        ),
        "source_ids": sources,
        "population_id": f"{package.scenario.id}:{package.scenario.market_id}",
        "market_id": package.scenario.market_id,
        "timezone": package.scenario.timezone,
        "policy_id": policy_id,
        "policy_decision_id": policy_decision_id,
        "role": role,
        "snapshot_checksum": snapshot_checksum,
    }
    contract = AtomicQueryContract(
        contract_id="aqc." + sha256_value(payload)[:16],
        **payload,
    )
    step = PlanStep(
        step_id="cash-analysis",
        operation=pattern.operation,
        contract=contract,
    )
    plan_payload = {
        "intent": request.intent,
        "question": question,
        "snapshot_checksum": snapshot_checksum,
        "steps": [step.model_dump(mode="json")],
    }
    plan_hash = sha256_value(plan_payload)
    return AnalysisPlan(
        plan_id="plan." + plan_hash[:16],
        plan_hash=plan_hash,
        **plan_payload,
    )


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.000001")).normalize()
    return value


def _step(queries: tuple[CompiledQuery, ...], rows: list[dict[str, Any]]) -> StepExecution:
    sql = "\n\n-- next bounded query --\n\n".join(query.sql for query in queries)
    params = tuple(value for query in queries for value in query.params)
    return StepExecution(
        step_id="cash-analysis",
        status="PASS",
        sql=sql,
        params=params,
        sql_hash=sha256_value(
            [{"operation": query.operation, "sql": query.sql, "params": query.params} for query in queries]
        ),
        rows=tuple(rows),
    )


def _path_value(facts: dict[str, Any], path: str) -> Any:
    current: Any = facts
    for token in path.removeprefix("/facts/").split("/"):
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def _evidence(
    *,
    package: OntologyPackage,
    snapshot: VerifiedSnapshot,
    plan: AnalysisPlan,
    execution: StepExecution,
    execution_id: str,
    facts: dict[str, Any],
    specs: tuple[
        tuple[
            str,
            Literal["numeric", "direction", "ranking", "limitation", "definition"],
            str,
            str,
            str | None,
            tuple[str, ...],
            tuple[str, ...],
        ],
        ...,
    ],
) -> tuple[EvidenceRecord, ...]:
    metrics = {item.id: item for item in package.metrics}
    contract = plan.steps[0].contract
    result: list[EvidenceRecord] = []
    for claim_id, claim_type, claim, path, unit, metric_ids, mapping_ids in specs:
        value = _path_value(facts, path)
        if isinstance(value, Decimal):
            display = f"{value:.2f}"
        elif isinstance(value, bool):
            display = "true" if value else "false"
        else:
            display = str(value)
        result.append(
            EvidenceRecord(
                claim_id=claim_id,
                claim_type=claim_type,
                claim=claim,
                result_path=path,
                value=str(value),
                display_value=display,
                unit=unit,
                execution_id=execution_id,
                snapshot_checksum=snapshot.snapshot_checksum,
                plan_hash=plan.plan_hash,
                dataset_checksum=snapshot.dataset_checksum,
                policy_id=contract.policy_id,
                policy_decision_id=contract.policy_decision_id,
                query_or_operator_hashes=(
                    execution.sql_hash or sha256_value({"operation": contract.operation}),
                ),
                metric_ids=metric_ids,
                metric_versions=tuple(metrics[item].version for item in metric_ids),
                mapping_ids=mapping_ids,
                source_ids=(
                    "source.sample_data",
                    "source.assumption_register",
                    "source.derived_oracle",
                ),
                step_ids=("cash-analysis",),
            )
        )
    return tuple(result)


def _answer(
    request: CashRequest,
    question: str,
    role: str,
    facts: dict[str, Any],
) -> str:
    zh = _is_chinese(question)
    limitation = (
        "以上仅为基于合成数据和临时规则的筛查候选，不构成违规结论。"
        if zh
        else "This is a constructed-synthetic triage result under provisional rules, not a misconduct conclusion."
    )
    if request.intent == "anomaly_triage":
        summary = facts["summary"]
        core = (
            f"{request.start}至{request.end}共有 {summary['eligible_trade_count']} 笔自成交口径合格成交，"
            f"其中 {summary['candidate_trade_count']} 笔为潜在自成交候选，候选率 {Decimal(str(summary['candidate_rate_percent'])):.2f}%。"
            if zh
            else f"From {request.start} to {request.end}, {summary['eligible_trade_count']} trades were eligible for the self-trade denominator; "
            f"{summary['candidate_trade_count']} were potential self-trade candidates, a {Decimal(str(summary['candidate_rate_percent'])):.2f}% candidate rate."
        )
        if role != "MarketsDemo":
            core += (
                f" 涉及 {summary['candidate_participant_count']} 个参与者和 {summary['candidate_instrument_count']} 个证券。"
                if zh
                else f" They involved {summary['candidate_participant_count']} participants and {summary['candidate_instrument_count']} instruments."
            )
        return core + " " + limitation
    if request.intent == "time_series":
        parts = [
            f"{row['business_date']}: {row['candidate_trade_count']}/{row['eligible_trade_count']} ({Decimal(str(row['candidate_rate_percent'])):.2f}%)"
            for row in facts["daily"]
        ]
        prefix = "逐日候选率：" if zh else "Daily candidate rates: "
        return prefix + "; ".join(parts) + ". " + limitation
    if request.intent == "timeline_evidence":
        quality = facts["timeline_quality"]
        core = (
            f"{request.participant_id} 在所选日期有 {quality['candidate_trade_count']} 笔候选成交及 "
            f"{quality['linked_order_event_count']} 条关联订单事件；{quality['incomplete_order_count']} 个订单未观察到 NEW 事件。"
            if zh
            else f"{request.participant_id} has {quality['candidate_trade_count']} candidate trade(s) and "
            f"{quality['linked_order_event_count']} linked order event(s) in the selected range; "
            f"{quality['incomplete_order_count']} linked order(s) have no observed NEW event."
        )
        return core + " " + limitation
    if request.intent == "latency_profile":
        latency = facts["latency"]
        core = (
            f"{request.start}至{request.end}的 {latency['eligible_latency_count']} 条非负延迟观测中，"
            f"p50/p95/p99 分别为 {latency['p50_ms']}/{latency['p95_ms']}/{latency['p99_ms']} 毫秒，"
            f"最小/最大为 {latency['minimum_ms']}/{latency['maximum_ms']} 毫秒；负延迟例外 {latency['negative_latency_count']} 条。"
            if zh
            else f"Across {latency['eligible_latency_count']} non-negative observations from {request.start} to {request.end}, "
            f"p50/p95/p99 capture latency was {latency['p50_ms']}/{latency['p95_ms']}/{latency['p99_ms']} ms; "
            f"minimum/maximum was {latency['minimum_ms']}/{latency['maximum_ms']} ms, with {latency['negative_latency_count']} negative-latency exception(s)."
        )
        return core + " No SLA or breach classification is assumed."
    definition = facts["definition"]
    return (
        f"潜在自成交候选率定义为：{definition['numerator']} / {definition['denominator']}。"
        f"当前身份层级为 {definition['identity_level']}；修正记录及被修正原记录均排除。{limitation}"
        if zh
        else f"Potential self-trade candidate rate is defined as {definition['numerator']} divided by {definition['denominator']}. "
        f"The current identity level is {definition['identity_level']}; correction rows and corrected originals are excluded. {limitation}"
    )


def _execute(
    context: CashTradingDuckDB,
    request: CashRequest,
    role: str,
) -> tuple[tuple[CompiledQuery, ...], list[dict[str, Any]], dict[str, Any]]:
    if request.intent == "evidence_audit":
        facts = {
            "definition": {
                "numerator": "distinct eligible trades where normalized buy_participant_id equals normalized sell_participant_id",
                "denominator": "distinct eligible active trades with both participant IDs present",
                "identity_level": "participant_id (provisional)",
                "decision_ids": ["CT-ASM-005", "CT-ASM-006", "CT-ASM-007"],
                "classification": "constructed_synthetic",
            },
            "limitations": list(_LIMITATIONS),
        }
        query = _query(
            "CashEvidenceAudit",
            "SELECT 'bounded semantic evidence; no data query required' AS evidence_scope",
            (),
            ("metric.potential_self_trade_rate",),
            ("binding.trade.has_both_participants", "binding.trade.self_trade"),
            ("source.cash_trade_analytics",),
        )
        return (query,), context.execute(query), facts

    if request.start is None or request.end is None:
        raise CashTradingAnalysisFailure("Executable request has no bounded date range")
    if request.intent == "anomaly_triage":
        summary_query = _summary_query(request.start, request.end)
        breakdown_query = _candidate_breakdown_query(request.start, request.end)
        summary_rows = context.execute(summary_query)
        if len(summary_rows) != 1 or summary_rows[0]["eligible_trade_count"] == 0:
            raise CashTradingAnalysisFailure("Self-trade denominator is empty")
        summary = {key: _normalize_value(value) for key, value in summary_rows[0].items()}
        breakdown = context.execute(breakdown_query)
        facts = {
            "summary": summary,
            "candidate_breakdown": breakdown if role != "MarketsDemo" else [],
            "limitations": list(_LIMITATIONS),
        }
        return (summary_query, breakdown_query), [*summary_rows, *breakdown], facts
    if request.intent == "time_series":
        query = _trend_query(request.start, request.end)
        rows = context.execute(query)
        if not rows:
            raise CashTradingAnalysisFailure("No daily self-trade population was found")
        facts = {
            "daily": [
                {key: _normalize_value(value) for key, value in row.items()}
                for row in rows
            ],
            "limitations": list(_LIMITATIONS),
        }
        return (query,), rows, facts
    if request.intent == "latency_profile":
        query = _latency_query(request.start, request.end)
        rows = context.execute(query)
        if len(rows) != 1 or rows[0]["eligible_latency_count"] == 0:
            raise CashTradingAnalysisFailure("Latency population is empty")
        facts = {
            "latency": {key: _normalize_value(value) for key, value in rows[0].items()},
            "percentile_method": "nearest_rank",
            "limitations": [*_LIMITATIONS, "No approved SLA or breach threshold is assumed."],
        }
        return (query,), rows, facts
    if request.participant_id is None:
        raise CashTradingAnalysisFailure("Timeline request has no participant")
    trade_query, order_query = _timeline_queries(
        request.start, request.end, request.participant_id
    )
    trades = context.execute(trade_query)
    if not trades:
        raise CashTradingAnalysisFailure("Participant has no candidate trade in the selected range")
    orders = context.execute(order_query)
    incomplete_orders = {
        row["order_id"]
        for row in orders
        if not row["observed_lifecycle_complete"]
    }
    facts = {
        "participant_id": request.participant_id,
        "candidate_trades": trades,
        "linked_order_events": orders,
        "timeline_quality": {
            "candidate_trade_count": len(trades),
            "linked_order_event_count": len(orders),
            "incomplete_order_count": len(incomplete_orders),
            "events_are_observed_only": True,
        },
        "limitations": list(_LIMITATIONS),
    }
    return (trade_query, order_query), [*trades, *orders], facts


def _evidence_specs(request: CashRequest) -> tuple[tuple[Any, ...], ...]:
    if request.intent == "anomaly_triage":
        return (
            (
                "claim.cash.self_trade.denominator",
                "numeric",
                "Eligible self-trade denominator",
                "/facts/summary/eligible_trade_count",
                "TRADE",
                ("metric.self_trade_eligible_trade_count",),
                ("binding.trade.has_both_participants",),
            ),
            (
                "claim.cash.self_trade.candidates",
                "numeric",
                "Potential self-trade candidates",
                "/facts/summary/candidate_trade_count",
                "TRADE",
                ("metric.potential_self_trade_count",),
                ("binding.trade.self_trade",),
            ),
            (
                "claim.cash.self_trade.rate",
                "numeric",
                "Potential self-trade candidate rate",
                "/facts/summary/candidate_rate_percent",
                "PERCENT",
                ("metric.potential_self_trade_rate",),
                ("binding.trade.has_both_participants", "binding.trade.self_trade"),
            ),
        )
    if request.intent == "latency_profile":
        return tuple(
            (
                f"claim.cash.latency.{name}",
                "numeric",
                f"Trade capture latency {name}",
                f"/facts/latency/{name}",
                "MILLISECOND" if name.endswith("_ms") else "OBSERVATION",
                ("metric.trade_capture_latency_ms",),
                ("binding.trade.capture_latency",),
            )
            for name in (
                "eligible_latency_count",
                "p50_ms",
                "p95_ms",
                "p99_ms",
                "negative_latency_count",
            )
        )
    if request.intent == "timeline_evidence":
        return (
            (
                "claim.cash.timeline.candidate_count",
                "numeric",
                "Candidate trades in evidence timeline",
                "/facts/timeline_quality/candidate_trade_count",
                "TRADE",
                ("metric.potential_self_trade_count",),
                ("binding.trade.self_trade",),
            ),
            (
                "claim.cash.timeline.observed_only",
                "limitation",
                "Timeline contains observed events only",
                "/facts/timeline_quality/events_are_observed_only",
                None,
                ("metric.potential_self_trade_count",),
                ("binding.trade.self_trade",),
            ),
        )
    if request.intent == "evidence_audit":
        return (
            (
                "claim.cash.self_trade.definition",
                "definition",
                "Published provisional potential self-trade definition",
                "/facts/definition/identity_level",
                None,
                ("metric.potential_self_trade_rate",),
                ("binding.trade.has_both_participants", "binding.trade.self_trade"),
            ),
        )
    return tuple(
        (
            f"claim.cash.trend.{index}.rate",
            "numeric",
            f"Potential self-trade rate on {row['business_date']}",
            f"/facts/daily/{index}/candidate_rate_percent",
            "PERCENT",
            ("metric.potential_self_trade_rate",),
            ("binding.trade.business_date", "binding.trade.self_trade"),
        )
        for index, row in enumerate([])
    )


def _trend_evidence_specs(facts: dict[str, Any]) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        (
            f"claim.cash.trend.{index}.rate",
            "numeric",
            f"Potential self-trade rate on {row['business_date']}",
            f"/facts/daily/{index}/candidate_rate_percent",
            "PERCENT",
            ("metric.potential_self_trade_rate",),
            ("binding.trade.business_date", "binding.trade.self_trade"),
        )
        for index, row in enumerate(facts["daily"])
    )


def analyze_cash_snapshot(
    snapshot: VerifiedSnapshot,
    *,
    question: str,
    role: str,
    execution_dir: Path,
    bound_goal: BoundAnalysisGoal | None = None,
) -> AnalysisResponse:
    try:
        verify_snapshot_handle(snapshot)
    except PublicationError:
        return AnalysisResponse(
            status="FAILED",
            answer="The bound Cash Trading snapshot failed integrity verification.",
            boundary_code="SNAPSHOT_VERIFICATION_FAILED",
        )
    resolved = resolve_cash_request(
        snapshot.package,
        question,
        role,
        bound_intent=bound_goal.intent if bound_goal is not None else None,
    )
    if isinstance(resolved, AnalysisResponse):
        return resolved.model_copy(update={"snapshot_checksum": snapshot.snapshot_checksum})

    plan = _plan(snapshot.package, resolved, question, role, snapshot.snapshot_checksum)
    execution_id = "exec." + uuid.uuid4().hex
    executions: list[StepExecution] = []
    try:
        with CashTradingDuckDB(snapshot.resource_paths) as context:
            queries, rows, facts = _execute(context, resolved, role)
        execution = _step(queries, rows)
        executions.append(execution)
        raw_specs = (
            _trend_evidence_specs(facts)
            if resolved.intent == "time_series"
            else _evidence_specs(resolved)
        )
        specs = tuple(raw_specs)  # preserve fixed ordering in persisted evidence
        evidence = _evidence(
            package=snapshot.package,
            snapshot=snapshot,
            plan=plan,
            execution=execution,
            execution_id=execution_id,
            facts=facts,
            specs=specs,  # type: ignore[arg-type]
        )
        response = AnalysisResponse(
            status="ANSWERED",
            answer=_answer(resolved, question, role, facts),
            execution_id=execution_id,
            snapshot_checksum=snapshot.snapshot_checksum,
            plan=plan,
            steps=tuple(executions),
            facts=facts,
            evidence=evidence,
        )
    except Exception as exc:
        executions.append(
            StepExecution(
                step_id="cash-analysis",
                status="FAIL",
                error=f"{type(exc).__name__}: {exc}",
            )
        )
        response = AnalysisResponse(
            status="FAILED",
            answer="The Cash Trading analysis stopped without releasing a partial answer.",
            execution_id=execution_id,
            snapshot_checksum=snapshot.snapshot_checksum,
            plan=plan,
            steps=tuple(executions),
            boundary_code="EXECUTION_FAILED",
        )
    if response.execution_id:
        write_json(
            execution_dir / f"{response.execution_id}.json",
            response.model_dump(mode="json"),
        )
    return response
