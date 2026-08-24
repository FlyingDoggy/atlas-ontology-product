from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from .analytic_conversations import (
    AnalyticConversationContextV1,
    AnalyticTurnLeaseV1,
)
from .cash_trading_runtime import CashTradingDuckDB
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


_DATA_START = date(2026, 8, 3)
_DATA_END = date(2026, 8, 7)
_ALLOWED_ROLES = {"MarketSurveillanceDemo", "TradingDemo", "MarketsDemo"}
_DETAIL_ROLES = {"MarketSurveillanceDemo", "TradingDemo"}
_MODEL_NAME = "qwen3.8-max"
_QWEN_DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_ANALYTIC_MODEL_PROVIDER = "cash-trading-analytics"
_CASH_CONVERSATION_CHECKPOINTER = InMemorySaver()


class _CashTradingQwenModel(ChatOpenAI):
    """Give this runtime its own DeepAgent harness identity.

    Qwen is served through the OpenAI-compatible API, but the generic
    ``openai`` DeepAgent profile is shared by Studio construction.  A distinct
    LangSmith provider identity lets the analytic runtime expose a deliberately
    small tool surface without changing the Builder's agent harness.
    """

    def _get_ls_params(
        self, stop: list[str] | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        params = dict(super()._get_ls_params(stop=stop, **kwargs))
        params["ls_provider"] = _ANALYTIC_MODEL_PROVIDER
        return params


register_harness_profile(
    _ANALYTIC_MODEL_PROVIDER,
    HarnessProfile(
        base_system_prompt=(
            "Use the available domain tools directly. Choose the shortest "
            "sufficient tool path, inspect the returned evidence, and answer. "
            "Do not create task lists, delegate work, access files, or execute "
            "shell commands."
        ),
        excluded_tools=frozenset(
            {
                "write_todos",
                "ls",
                "read_file",
                "write_file",
                "edit_file",
                "glob",
                "grep",
                "execute",
            }
        ),
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
    ),
)


@dataclass(frozen=True, slots=True)
class DimensionColumn:
    dimension_id: str
    label: str
    trade_column: str | None
    order_column: str | None


_DIMENSIONS: dict[str, DimensionColumn] = {
    "business_date": DimensionColumn(
        "dimension.business_date", "business_date", "business_date", "trading_date"
    ),
    "venue": DimensionColumn("dimension.venue", "venue", "venue_code", "venue_code"),
    "market_segment": DimensionColumn(
        "dimension.market_segment", "market_segment", "market_segment", "market_segment"
    ),
    "instrument": DimensionColumn(
        "dimension.instrument", "instrument", "instrument_id", "instrument_id"
    ),
    "participant": DimensionColumn(
        "dimension.participant", "participant", "participant_id", "participant_id"
    ),
    "participant_type": DimensionColumn(
        "dimension.participant_type",
        "participant_type",
        "participant_type",
        "participant_type",
    ),
    "order_type": DimensionColumn(
        "dimension.order_type", "order_type", None, "order_type"
    ),
    "trading_session": DimensionColumn(
        "dimension.trading_session", "trading_session", None, "session_phase"
    ),
}

_DIMENSION_ALIASES = {
    "date": "business_date",
    "day": "business_date",
    "trading_date": "business_date",
    "dimension.business_date": "business_date",
    "venue_code": "venue",
    "dimension.venue": "venue",
    "segment": "market_segment",
    "dimension.market_segment": "market_segment",
    "instrument_id": "instrument",
    "dimension.instrument": "instrument",
    "participant_id": "participant",
    "dimension.participant": "participant",
    "dimension.participant_type": "participant_type",
    "dimension.order_type": "order_type",
    "session": "trading_session",
    "session_phase": "trading_session",
    "dimension.trading_session": "trading_session",
}

_PRIMARY_METRICS = {
    "M-01": "metric.order_rejection_rate",
    "M-02": "metric.order_fill_rate",
    "M-03": "metric.trade_capture_latency_ms",
    "M-04": "metric.active_client_trading_volume",
    "M-05": "metric.client_order_completion_rate",
    "M-06": "metric.cancel_to_trade_ratio",
    "M-07": "metric.order_to_trade_ratio",
    "M-08": "metric.potential_self_trade_rate",
}

_METRIC_ALIASES = {
    **{key.lower(): value for key, value in _PRIMARY_METRICS.items()},
    **{value.lower(): value for value in _PRIMARY_METRICS.values()},
    "order rejection rate": _PRIMARY_METRICS["M-01"],
    "订单拒绝率": _PRIMARY_METRICS["M-01"],
    "order fill rate": _PRIMARY_METRICS["M-02"],
    "订单成交率": _PRIMARY_METRICS["M-02"],
    "trade capture latency": _PRIMARY_METRICS["M-03"],
    "成交捕获延迟": _PRIMARY_METRICS["M-03"],
    "active client trading volume": _PRIMARY_METRICS["M-04"],
    "活跃客户成交量": _PRIMARY_METRICS["M-04"],
    "client order completion rate": _PRIMARY_METRICS["M-05"],
    "客户订单完成率": _PRIMARY_METRICS["M-05"],
    "cancel-to-trade ratio": _PRIMARY_METRICS["M-06"],
    "cancel to trade ratio": _PRIMARY_METRICS["M-06"],
    "撤单成交比": _PRIMARY_METRICS["M-06"],
    "order-to-trade ratio": _PRIMARY_METRICS["M-07"],
    "order to trade ratio": _PRIMARY_METRICS["M-07"],
    "订单成交比": _PRIMARY_METRICS["M-07"],
    "potential self-trade rate": _PRIMARY_METRICS["M-08"],
    "self-trade rate": _PRIMARY_METRICS["M-08"],
    "self trade rate": _PRIMARY_METRICS["M-08"],
    "潜在自成交率": _PRIMARY_METRICS["M-08"],
    "自成交率": _PRIMARY_METRICS["M-08"],
}


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def _formula_refs(node: Any) -> tuple[set[str], set[str]]:
    properties: set[str] = set()
    metrics: set[str] = set()

    def visit(value: Any) -> None:
        ref = getattr(value, "ref", None)
        if isinstance(ref, str):
            if ref.startswith("property."):
                properties.add(ref)
            elif ref.startswith("metric."):
                metrics.add(ref)
        for child in getattr(value, "args", ()) or ():
            visit(child)

    visit(node)
    return properties, metrics


@dataclass(slots=True)
class MetricTrace:
    metric_id: str
    metric_code: str
    metric_name_en: str
    metric_name_zh: str
    unit: str
    start_date: str
    end_date: str
    dimensions: tuple[str, ...]
    filters: dict[str, str]
    sql: str
    params: tuple[Any, ...]
    rows: list[dict[str, Any]]
    source_ids: tuple[str, ...]
    decision_ids: tuple[str, ...]
    mapping_ids: tuple[str, ...]
    limitations: tuple[str, ...] = ()

    @property
    def sql_hash(self) -> str:
        return sha256_value({"sql": self.sql, "params": self.params})

    def public_result(self) -> dict[str, Any]:
        return {
            "metric_code": self.metric_code,
            "metric_id": self.metric_id,
            # Keep the historical English field for API compatibility and expose
            # both labels so each product surface can render its active locale.
            "metric_name": self.metric_name_en,
            "metric_name_en": self.metric_name_en,
            "metric_name_zh": self.metric_name_zh,
            "unit": self.unit,
            "period": {"start": self.start_date, "end": self.end_date},
            "dimensions": list(self.dimensions),
            "filters": dict(self.filters),
            "rows": self.rows,
            "limitations": list(self.limitations),
            "evidence": {
                "sources": list(self.source_ids),
                "decisions": list(self.decision_ids),
                "mappings": list(self.mapping_ids),
                "query_hash": self.sql_hash,
            },
        }


@dataclass(frozen=True, slots=True)
class SemanticTrace:
    operation: Literal[
        "describe_capabilities", "inspect_ontology", "retrieve_evidence"
    ]
    topic: str
    result: dict[str, Any]
    source_ids: tuple[str, ...] = ()
    decision_ids: tuple[str, ...] = ()
    metric_ids: tuple[str, ...] = ()

    @property
    def trace_hash(self) -> str:
        return sha256_value(
            {
                "operation": self.operation,
                "topic": self.topic,
                "result": self.result,
                "source_ids": self.source_ids,
                "decision_ids": self.decision_ids,
                "metric_ids": self.metric_ids,
            }
        )


@dataclass(frozen=True, slots=True)
class QueryBoundary:
    status: Literal["CLARIFY", "REFUSED", "NO_DATA"]
    code: str
    answer_en: str
    answer_zh: str


class CashTradingQueryBoundary(ValueError):
    def __init__(self, boundary: QueryBoundary):
        super().__init__(boundary.answer_en)
        self.boundary = boundary


@dataclass(slots=True)
class CashTradingSemanticEngine:
    package: OntologyPackage
    resource_paths: Mapping[str, Path]
    role: str
    conversation_id: str | None = None
    conversation_context: AnalyticConversationContextV1 | None = None
    traces: list[MetricTrace] = field(default_factory=list)
    semantic_traces: list[SemanticTrace] = field(default_factory=list)
    boundary: QueryBoundary | None = None

    def _metric(self, requested: str) -> tuple[str, Any]:
        normalized = requested.strip().lower()
        metric_id = _METRIC_ALIASES.get(normalized)
        if metric_id is None:
            metric_id = next(
                (
                    item.id
                    for item in self.package.metrics
                    if normalized
                    in {
                        item.id.lower(),
                        item.name.en.lower(),
                        (item.name.zh or "").lower(),
                    }
                    and item.id in _PRIMARY_METRICS.values()
                ),
                None,
            )
        if metric_id is None:
            raise ValueError(
                "Unknown business metric. Use M-01 through M-08 or an exact ontology metric ID."
            )
        metric = next(item for item in self.package.metrics if item.id == metric_id)
        code = next(key for key, value in _PRIMARY_METRICS.items() if value == metric_id)
        return code, metric

    @staticmethod
    def _dates(start_date: str | None, end_date: str | None) -> tuple[date, date]:
        try:
            start = date.fromisoformat(start_date) if start_date else _DATA_START
            end = date.fromisoformat(end_date) if end_date else _DATA_END
        except ValueError as exc:
            raise ValueError("Dates must use YYYY-MM-DD.") from exc
        if start > end:
            raise ValueError("start_date cannot be after end_date.")
        if (end - start).days > 92:
            raise ValueError("A single demo query cannot exceed three months.")
        return start, end

    def _dimensions(self, values: Sequence[str] | None) -> tuple[DimensionColumn, ...]:
        result: list[DimensionColumn] = []
        for raw in values or ():
            normalized = raw.strip().lower()
            normalized = _DIMENSION_ALIASES.get(normalized, normalized)
            candidate = _DIMENSIONS.get(normalized)
            if candidate is None:
                raise ValueError(f"Unsupported dimension: {raw}")
            if candidate not in result:
                result.append(candidate)
        if len(result) > 2:
            raise ValueError("Use at most two grouping dimensions in one demo query.")
        if self.role == "MarketsDemo" and any(
            item.dimension_id in {"dimension.participant", "dimension.participant_type"}
            for item in result
        ):
            raise ValueError("MarketsDemo cannot access participant-level groupings.")
        return tuple(result)

    def _filters(self, raw: Mapping[str, str] | None) -> dict[str, str]:
        result: dict[str, str] = {}
        for key, value in (raw or {}).items():
            normalized = _DIMENSION_ALIASES.get(key.strip().lower(), key.strip().lower())
            if normalized not in _DIMENSIONS:
                raise ValueError(f"Unsupported filter dimension: {key}")
            if self.role == "MarketsDemo" and normalized in {"participant", "participant_type"}:
                raise ValueError("MarketsDemo cannot filter by participant identity.")
            result[normalized] = str(value)
        return result

    @staticmethod
    def _where(
        *,
        view: str,
        start: date,
        end: date,
        dimensions: Mapping[str, DimensionColumn],
        filters: Mapping[str, str],
    ) -> tuple[str, list[Any]]:
        is_trade = view == "trade"
        date_column = "business_date" if is_trade else "trading_date"
        clauses = [f"{date_column} BETWEEN ? AND ?"]
        params: list[Any] = [start, end]
        for name, value in filters.items():
            dimension = dimensions[name]
            column = dimension.trade_column if is_trade else dimension.order_column
            if column is None:
                raise ValueError(
                    f"Dimension {dimension.dimension_id} is not available for this metric."
                )
            clauses.append(f"upper(trim(cast({column} AS VARCHAR))) = upper(trim(?))")
            params.append(value)
        return " AND ".join(clauses), params

    @staticmethod
    def _select_group(
        dimensions: Sequence[DimensionColumn], *, view: str, prefix: str = ""
    ) -> tuple[str, str, tuple[str, ...]]:
        is_trade = view == "trade"
        expressions: list[str] = []
        labels: list[str] = []
        for item in dimensions:
            column = item.trade_column if is_trade else item.order_column
            if column is None:
                raise ValueError(
                    f"Dimension {item.dimension_id} is not available for this metric."
                )
            expressions.append(f"{prefix}{column} AS {item.label}")
            labels.append(item.label)
        select = (", ".join(expressions) + ", ") if expressions else ""
        group = " GROUP BY " + ", ".join(
            (item.trade_column if is_trade else item.order_column) or ""
            for item in dimensions
        ) if dimensions else ""
        return select, group, tuple(labels)

    def _execute(self, sql: str, params: Sequence[Any]) -> list[dict[str, Any]]:
        with CashTradingDuckDB(self.resource_paths) as database:
            cursor = database.connection.execute(sql, list(params))
            columns = [item[0] for item in cursor.description]
            return [
                {name: _json_value(value) for name, value in zip(columns, row, strict=True)}
                for row in cursor.fetchall()
            ]

    def _single_view_query(
        self,
        *,
        metric_id: str,
        dimensions: Sequence[DimensionColumn],
        filters: Mapping[str, str],
        start: date,
        end: date,
    ) -> tuple[str, tuple[Any, ...]]:
        if metric_id in {
            _PRIMARY_METRICS["M-01"],
            _PRIMARY_METRICS["M-02"],
            _PRIMARY_METRICS["M-05"],
        }:
            select, group, _ = self._select_group(dimensions, view="order")
            where, params = self._where(
                view="order",
                start=start,
                end=end,
                dimensions=_DIMENSIONS,
                filters=filters,
            )
            expressions = {
                _PRIMARY_METRICS["M-01"]: """
                    count(DISTINCT lifecycle_key) FILTER (WHERE is_rejected) AS rejected_order_count,
                    count(DISTINCT lifecycle_key) FILTER (WHERE is_submitted) AS submitted_order_count,
                    round(100.0 * count(DISTINCT lifecycle_key) FILTER (WHERE is_rejected)
                      / nullif(count(DISTINCT lifecycle_key) FILTER (WHERE is_submitted), 0), 6) AS value
                """,
                _PRIMARY_METRICS["M-02"]: """
                    sum(final_cumulative_executed_quantity) FILTER (WHERE is_submitted) AS executed_order_quantity,
                    sum(final_order_quantity) FILTER (WHERE is_submitted) AS submitted_order_quantity,
                    round(100.0 * sum(final_cumulative_executed_quantity) FILTER (WHERE is_submitted)
                      / nullif(sum(final_order_quantity) FILTER (WHERE is_submitted), 0), 6) AS value
                """,
                _PRIMARY_METRICS["M-05"]: """
                    count(DISTINCT lifecycle_key) FILTER (WHERE is_fully_filled) AS fully_filled_client_order_count,
                    count(DISTINCT lifecycle_key) FILTER (WHERE is_eligible_client_order) AS eligible_client_order_count,
                    round(100.0 * count(DISTINCT lifecycle_key) FILTER (WHERE is_fully_filled)
                      / nullif(count(DISTINCT lifecycle_key) FILTER (WHERE is_eligible_client_order), 0), 6) AS value
                """,
            }
            return (
                f"SELECT {select}{expressions[metric_id]} FROM cash_order_lifecycle_analytics WHERE {where}{group} ORDER BY ALL",
                tuple(params),
            )
        select, group, _ = self._select_group(dimensions, view="trade")
        where, params = self._where(
            view="trade",
            start=start,
            end=end,
            dimensions=_DIMENSIONS,
            filters=filters,
        )
        expressions = {
            _PRIMARY_METRICS["M-03"]: """
                count(*) FILTER (WHERE is_nonnegative_latency) AS eligible_latency_count,
                min(capture_latency_ms) FILTER (WHERE is_nonnegative_latency) AS minimum_ms,
                quantile_disc(capture_latency_ms, 0.50) FILTER (WHERE is_nonnegative_latency) AS p50_ms,
                quantile_disc(capture_latency_ms, 0.95) FILTER (WHERE is_nonnegative_latency) AS p95_ms,
                quantile_disc(capture_latency_ms, 0.99) FILTER (WHERE is_nonnegative_latency) AS p99_ms,
                max(capture_latency_ms) FILTER (WHERE is_nonnegative_latency) AS maximum_ms,
                count(*) FILTER (WHERE NOT is_nonnegative_latency) AS negative_latency_count,
                quantile_disc(capture_latency_ms, 0.95) FILTER (WHERE is_nonnegative_latency) AS value
            """,
            _PRIMARY_METRICS["M-04"]: """
                sum(trade_quantity) FILTER (WHERE is_active_client) AS active_client_trade_quantity,
                sum(trade_notional_hkd) FILTER (WHERE is_active_client) AS active_client_trade_notional_hkd,
                sum(base_notional_usd) FILTER (WHERE is_active_client) AS active_client_trade_notional_usd_pre_haircut,
                count(DISTINCT participant_id) FILTER (WHERE is_active_client) AS active_client_count,
                round(sum(trade_notional_hkd) FILTER (WHERE is_active_client) / 1000000.0, 6) AS value
            """,
            _PRIMARY_METRICS["M-08"]: """
                count(DISTINCT trading_activity_id) FILTER (WHERE is_potential_self_trade) AS potential_self_trade_count,
                count(DISTINCT trading_activity_id) FILTER (WHERE has_both_participant_ids) AS self_trade_eligible_trade_count,
                round(100.0 * count(DISTINCT trading_activity_id) FILTER (WHERE is_potential_self_trade)
                  / nullif(count(DISTINCT trading_activity_id) FILTER (WHERE has_both_participant_ids), 0), 6) AS value
            """,
        }
        return (
            f"SELECT {select}{expressions[metric_id]} FROM cash_trade_analytics WHERE {where}{group} ORDER BY ALL",
            tuple(params),
        )

    def _cross_view_query(
        self,
        *,
        metric_id: str,
        dimensions: Sequence[DimensionColumn],
        filters: Mapping[str, str],
        start: date,
        end: date,
    ) -> tuple[str, tuple[Any, ...]]:
        order_select, order_group, labels = self._select_group(dimensions, view="order")
        trade_select, trade_group, _ = self._select_group(dimensions, view="trade")
        order_where, order_params = self._where(
            view="order", start=start, end=end, dimensions=_DIMENSIONS, filters=filters
        )
        trade_where, trade_params = self._where(
            view="trade", start=start, end=end, dimensions=_DIMENSIONS, filters=filters
        )
        orders = """
          count(DISTINCT lifecycle_key) FILTER (WHERE is_submitted) AS submitted_order_count,
          count(DISTINCT lifecycle_key) FILTER (WHERE is_canceled) AS canceled_order_count
        """
        trades = "count(DISTINCT trading_activity_id) AS eligible_trade_count"
        if labels:
            join = " AND ".join(
                f"o.{label} IS NOT DISTINCT FROM t.{label}" for label in labels
            )
            dimension_projection = ", ".join(
                f"coalesce(o.{label}, t.{label}) AS {label}" for label in labels
            ) + ", "
            from_clause = f"orders o FULL OUTER JOIN trades t ON {join}"
        else:
            dimension_projection = ""
            from_clause = "orders o CROSS JOIN trades t"
        value = (
            "round(100.0 * o.canceled_order_count / nullif(t.eligible_trade_count, 0), 6)"
            if metric_id == _PRIMARY_METRICS["M-06"]
            else "round(100.0 * o.submitted_order_count / nullif(2 * t.eligible_trade_count, 0), 6)"
        )
        sql = f"""
          WITH orders AS (
            SELECT {order_select}{orders}
            FROM cash_order_lifecycle_analytics
            WHERE {order_where}{order_group}
          ), trades AS (
            SELECT {trade_select}{trades}
            FROM cash_trade_analytics
            WHERE {trade_where}{trade_group}
          )
          SELECT {dimension_projection}o.submitted_order_count, o.canceled_order_count,
                 t.eligible_trade_count, {value} AS value
          FROM {from_clause}
          ORDER BY ALL
        """
        return sql, tuple([*order_params, *trade_params])

    def query_metric(
        self,
        metric: str,
        start_date: str | None = None,
        end_date: str | None = None,
        group_by: Sequence[str] | None = None,
        filters: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        code, ontology_metric = self._metric(metric)
        start, end = self._dates(start_date, end_date)
        dimensions = self._dimensions(group_by)
        normalized_filters = self._filters(filters)
        if ontology_metric.id in {
            _PRIMARY_METRICS["M-06"],
            _PRIMARY_METRICS["M-07"],
        }:
            sql, params = self._cross_view_query(
                metric_id=ontology_metric.id,
                dimensions=dimensions,
                filters=normalized_filters,
                start=start,
                end=end,
            )
            runtime_sources = (
                "source.cash_order_lifecycle_analytics",
                "source.cash_trade_analytics",
            )
        else:
            sql, params = self._single_view_query(
                metric_id=ontology_metric.id,
                dimensions=dimensions,
                filters=normalized_filters,
                start=start,
                end=end,
            )
            runtime_sources = (
                "source.cash_order_lifecycle_analytics"
                if ontology_metric.base_entity == "entity.order_lifecycle"
                else "source.cash_trade_analytics",
            )
        rows = self._execute(sql, params)
        if not rows or all(row.get("value") is None for row in rows):
            if normalized_filters:
                boundary = QueryBoundary(
                    status="NO_DATA",
                    code="NO_MATCHING_DATA",
                    answer_en="No records match the selected period and filters.",
                    answer_zh="所选时间范围和筛选条件下没有匹配记录。",
                )
            else:
                boundary = QueryBoundary(
                    status="NO_DATA",
                    code="ZERO_DENOMINATOR",
                    answer_en=(
                        "The metric is undefined because its governed denominator is zero "
                        "for the selected range."
                    ),
                    answer_zh="所选范围内该指标的受治理分母为零，因此指标无定义。",
                )
            self.boundary = boundary
            raise CashTradingQueryBoundary(boundary)
        property_refs, metric_refs = _formula_refs(ontology_metric.formula)
        referenced_metrics = {
            item.id: item for item in self.package.metrics if item.id in metric_refs
        }
        for referenced in referenced_metrics.values():
            nested_properties, _ = _formula_refs(referenced.formula)
            property_refs.update(nested_properties)
        mapping_ids = tuple(
            item.id for item in self.package.bindings if item.logical_target in property_refs
        )
        trace = MetricTrace(
            metric_id=ontology_metric.id,
            metric_code=code,
            metric_name_en=ontology_metric.name.en or ontology_metric.name.zh or code,
            metric_name_zh=ontology_metric.name.zh or ontology_metric.name.en or code,
            unit=ontology_metric.unit,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            dimensions=tuple(item.dimension_id for item in dimensions),
            filters=normalized_filters,
            sql=sql,
            params=params,
            rows=rows,
            source_ids=tuple(dict.fromkeys([*ontology_metric.sources, *runtime_sources])),
            decision_ids=tuple(ontology_metric.decisions),
            mapping_ids=mapping_ids,
            limitations=(
                (
                    "The sample EXECUTE events cannot be reliably linked to the originating NEW order lifecycles; the zero result is therefore affected by an input relationship gap and must not be interpreted as no market execution."
                ,)
                if code in {"M-02", "M-05"}
                else (
                    "Potential self-trade is a triage candidate based on matching participants, not a misconduct or market-abuse conclusion."
                ,)
                if code == "M-08"
                else ()
            ),
        )
        self.traces.append(trace)
        return trace.public_result()

    def _record_semantic(
        self,
        *,
        operation: Literal[
            "describe_capabilities", "inspect_ontology", "retrieve_evidence"
        ],
        topic: str,
        result: dict[str, Any],
        source_ids: Sequence[str] = (),
        decision_ids: Sequence[str] = (),
        metric_ids: Sequence[str] = (),
    ) -> dict[str, Any]:
        self.semantic_traces.append(
            SemanticTrace(
                operation=operation,
                topic=topic,
                result=result,
                source_ids=tuple(dict.fromkeys(source_ids)),
                decision_ids=tuple(dict.fromkeys(decision_ids)),
                metric_ids=tuple(dict.fromkeys(metric_ids)),
            )
        )
        return result

    def describe_capabilities(self) -> dict[str, Any]:
        metrics_by_id = {item.id: item for item in self.package.metrics}
        metrics = [
            {
                "code": code,
                "id": metric_id,
                "name": {
                    "en": metrics_by_id[metric_id].name.en,
                    "zh": metrics_by_id[metric_id].name.zh,
                },
                "unit": metrics_by_id[metric_id].unit,
            }
            for code, metric_id in _PRIMARY_METRICS.items()
        ]
        dimensions = [
            {
                "id": item.dimension_id,
                "name": item.label,
            }
            for item in _DIMENSIONS.values()
            if not (
                self.role == "MarketsDemo"
                and item.dimension_id
                in {"dimension.participant", "dimension.participant_type"}
            )
        ]
        result = {
            "package_id": self.package.package_id,
            "version": self.package.version,
            "role": self.role,
            "sample_period": {"start": str(_DATA_START), "end": str(_DATA_END)},
            "metrics": metrics,
            "dimensions": dimensions,
            "supported_operations": [
                "metric value",
                "daily trend",
                "dimension breakdown (up to two dimensions)",
                "ontology definition lookup",
                "source and decision evidence lookup",
                "known limitation explanation",
            ],
            "boundaries": [
                "Only the active Cash Trading ontology package and bound sample data are authoritative.",
                "Potential self-trade is a triage signal, not a misconduct conclusion.",
                "The sample period is 2026-08-03 through 2026-08-07.",
                "Numeric answers require the governed metric query tool.",
            ],
        }
        primary_metrics = [metrics_by_id[item] for item in _PRIMARY_METRICS.values()]
        return self._record_semantic(
            operation="describe_capabilities",
            topic="active package capabilities",
            result=result,
            source_ids=[source for item in primary_metrics for source in item.sources],
            decision_ids=[decision for item in primary_metrics for decision in item.decisions],
            metric_ids=list(_PRIMARY_METRICS.values()),
        )

    def ontology_catalog(
        self, search: str = "", *, record: bool = True
    ) -> dict[str, Any]:
        needle = search.strip().lower()
        sections = {
            "entities": self.package.entities,
            "relationships": self.package.relationships,
            "metrics": self.package.metrics,
            "dimensions": self.package.dimensions,
            "rules": self.package.rules,
        }
        result: dict[str, Any] = {}
        for name, items in sections.items():
            matches = []
            for item in items:
                haystack = " ".join(
                    [item.id, item.name.en, item.name.zh or "", item.definition]
                ).lower()
                if needle and needle not in haystack:
                    continue
                matches.append(
                    {
                        "id": item.id,
                        "name": {"en": item.name.en, "zh": item.name.zh},
                        "definition": item.definition,
                        "status": item.status,
                        "sources": list(item.sources),
                        "decisions": list(item.decisions),
                    }
                )
                if len(matches) >= 20:
                    break
            result[name] = matches
        catalog = {
            "package_id": self.package.package_id,
            "version": self.package.version,
            "sample_period": {"start": str(_DATA_START), "end": str(_DATA_END)},
            "primary_metrics": dict(_PRIMARY_METRICS),
            "assets": result,
        }
        if not record:
            return catalog
        matched_assets = [
            asset for assets in result.values() for asset in assets
        ]
        return self._record_semantic(
            operation="inspect_ontology",
            topic=search or "active ontology package",
            result=catalog,
            source_ids=[
                source for asset in matched_assets for source in asset["sources"]
            ],
            decision_ids=[
                decision for asset in matched_assets for decision in asset["decisions"]
            ],
            metric_ids=[asset["id"] for asset in result["metrics"]],
        )

    def evidence_for(self, topic: str) -> dict[str, Any]:
        catalog = self.ontology_catalog(topic, record=False)
        result = {
            "topic": topic,
            "matching_assets": catalog["assets"],
            "assumptions": [
                {
                    "id": item.id,
                    "question": item.question,
                    "decision": item.decision,
                    "residual_assumption": item.residual_assumption,
                }
                for item in self.package.decisions
                if topic.lower() in (item.id + " " + item.question + " " + item.decision).lower()
            ][:20],
            "limitations": [
                "Constructed-synthetic data; not HKEX validated.",
                "Potential self-trade is a triage candidate, not a misconduct conclusion.",
                "Observed order lifecycles may be incomplete.",
            ],
        }
        matched_assets = [
            asset for assets in catalog["assets"].values() for asset in assets
        ]
        return self._record_semantic(
            operation="retrieve_evidence",
            topic=topic,
            result=result,
            source_ids=[
                source for asset in matched_assets for source in asset["sources"]
            ],
            decision_ids=[
                decision for asset in matched_assets for decision in asset["decisions"]
            ],
            metric_ids=[
                asset["id"] for asset in catalog["assets"]["metrics"]
            ],
        )


def _configured_model() -> BaseChatModel | None:
    key = os.environ.get("ONTOLOGY_QWEN_API_KEY")
    if not key:
        return None
    return _CashTradingQwenModel(
        model=os.environ.get("ONTOLOGY_ANALYTIC_AGENT_MODEL", _MODEL_NAME),
        api_key=key,
        base_url=os.environ.get("ONTOLOGY_QWEN_BASE_URL", _QWEN_DEFAULT_BASE_URL),
        temperature=0,
        timeout=60,
        max_retries=1,
    )


def _deepagent_tools(engine: CashTradingSemanticEngine) -> list[Any]:
    @tool
    def describe_capabilities() -> str:
        """Describe the questions, metrics, dimensions, period and boundaries supported by the active package and current role."""
        return json.dumps(engine.describe_capabilities(), ensure_ascii=False)

    @tool
    def inspect_ontology(search: str = "") -> str:
        """Search the active Ontology Package for entities, relations, metrics, dimensions, rules and definitions."""
        return json.dumps(engine.ontology_catalog(search), ensure_ascii=False)

    @tool
    def query_cash_metric(
        metric: str,
        start_date: str = "2026-08-03",
        end_date: str = "2026-08-07",
        group_by: list[str] | str | None = None,
        filters: dict[str, str] | str | None = None,
    ) -> str:
        """Compute one governed Cash Trading metric. Use M-01 through M-08 or an exact metric ID. Dates are YYYY-MM-DD. Optional group_by and filters accept ontology dimension names; JSON strings are also accepted."""
        normalized_group_by: list[str] | None
        if isinstance(group_by, str):
            try:
                parsed_group_by = json.loads(group_by)
            except json.JSONDecodeError:
                parsed_group_by = [item.strip() for item in group_by.split(",")]
            if not isinstance(parsed_group_by, list) or not all(
                isinstance(item, str) for item in parsed_group_by
            ):
                raise ValueError("group_by must be a list of ontology dimension names")
            normalized_group_by = parsed_group_by
        else:
            normalized_group_by = group_by

        normalized_filters: dict[str, str] | None
        if isinstance(filters, str):
            try:
                parsed_filters = json.loads(filters)
            except json.JSONDecodeError as exc:
                raise ValueError("filters must be a JSON object") from exc
            if not isinstance(parsed_filters, dict) or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in parsed_filters.items()
            ):
                raise ValueError("filters must map ontology dimensions to strings")
            normalized_filters = parsed_filters
        else:
            normalized_filters = filters
        return json.dumps(
            engine.query_metric(
                metric,
                start_date,
                end_date,
                normalized_group_by,
                normalized_filters,
            ),
            ensure_ascii=False,
        )

    @tool
    def retrieve_metric_evidence(topic: str) -> str:
        """Retrieve source, definition, decision, assumption and limitation evidence for a metric or ontology topic."""
        return json.dumps(engine.evidence_for(topic), ensure_ascii=False)

    return [
        describe_capabilities,
        inspect_ontology,
        query_cash_metric,
        retrieve_metric_evidence,
    ]


def _system_prompt(
    package: OntologyPackage,
    role: str,
    conversation_context: AnalyticConversationContextV1 | None = None,
) -> str:
    metric_lines = []
    metrics = {item.id: item for item in package.metrics}
    for code, metric_id in _PRIMARY_METRICS.items():
        item = metrics[metric_id]
        metric_lines.append(f"- {code}: {item.name.en} / {item.name.zh} ({metric_id})")
    inherited_context = (
        json.dumps(
            conversation_context.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
        )
        if conversation_context is not None
        else "null"
    )
    return f"""You are the Cash Trading analytic agent for the active Ontology Package.

Your job is to understand the user's question, inspect ontology when useful, select the shortest sufficient governed tool path, and explain the deterministic result clearly.

Hard boundaries:
- Never calculate a business number yourself and never invent SQL. Use query_cash_metric for every numeric claim.
- Treat tool results as facts and package definitions/decisions as semantics.
- Do not call a potential self-trade a violation or misconduct.
- Explicitly distinguish HKD native notional from USD pre-haircut notional.
- Never omit a limitation returned by query_cash_metric; incorporate it into the answer in the user's language.
- Mention that the data is constructed-synthetic once, briefly; do not repeat system architecture.
- Answer in the language used by the user.
- Use the metric name in the user's language. Do not mix prose languages except for exact IDs, field names and verbatim business terms.
- The product renders the governed result rows in a structured table below your answer. Do not repeat those rows as a Markdown table or row-by-row list.
- Use one concise answer paragraph. Add one short interpretation paragraph only when the user asks for a trend, comparison, explanation, anomaly or exploration.
- Current role: {role}.
- Available sample data: 2026-08-03 through 2026-08-07 (2026-08-05 is a non-trading day).
- For questions about what you can answer, call describe_capabilities.
- For definitions, relationships, evidence, assumptions or limitations, call inspect_ontology or retrieve_metric_evidence. These are valid answers and do not require a metric query.
- When a question names multiple metrics or concepts, retrieve and address every named asset before comparing them. Never return a partial semantic match as a complete answer.
- Stay within the active Cash Trading package. Refuse unrelated general-knowledge requests instead of pretending the package supports them.
- The governed parameters from the preceding turn are shown below. For an elliptical follow-up, inherit omitted metric, period, dimensions and filters. Replace only values the user explicitly changes. Conversation text is not evidence; every numeric follow-up must still call query_cash_metric.

Governed preceding-turn context:
{inherited_context}

Primary metrics:
{chr(10).join(metric_lines)}

For trends, group by business_date. For comparisons, query the relevant metrics; do not infer one metric from another. Keep the final answer concise and decision-useful.
"""


def _message_text(message: AIMessage | None) -> str:
    if message is None:
        return ""
    content = message.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "\n".join(
            str(item.get("text", "")) if isinstance(item, dict) else str(item)
            for item in content
        ).strip()
    return str(content).strip()


def _dates_from_question(
    question: str,
    context: AnalyticConversationContextV1 | None = None,
) -> tuple[str, str]:
    values = re.findall(r"20\d{2}-\d{2}-\d{2}", question)
    if len(values) >= 2:
        return values[0], values[1]
    if len(values) == 1:
        return values[0], values[0]
    if context is not None and context.start_date and context.end_date:
        weekday_terms = {
            0: ("monday", "周一", "星期一"),
            1: ("tuesday", "周二", "星期二"),
            2: ("wednesday", "周三", "星期三"),
            3: ("thursday", "周四", "星期四"),
            4: ("friday", "周五", "星期五"),
            5: ("saturday", "周六", "星期六"),
            6: ("sunday", "周日", "星期日", "星期天"),
        }
        lower = question.lower()
        requested_weekday = next(
            (
                weekday
                for weekday, terms in weekday_terms.items()
                if any(term in lower for term in terms)
            ),
            None,
        )
        if requested_weekday is not None:
            current = date.fromisoformat(context.start_date)
            end = date.fromisoformat(context.end_date)
            matches: list[date] = []
            while current <= end:
                if current.weekday() == requested_weekday:
                    matches.append(current)
                current += timedelta(days=1)
            if matches:
                return matches[0].isoformat(), matches[-1].isoformat()
        return context.start_date, context.end_date
    return str(_DATA_START), str(_DATA_END)


def _fallback_metric(
    question: str,
    context: AnalyticConversationContextV1 | None = None,
) -> str | None:
    lower = question.lower()
    for alias, metric_id in sorted(_METRIC_ALIASES.items(), key=lambda item: -len(item[0])):
        if alias in lower:
            return metric_id
    keyword_map = (
        (("reject", "拒绝"), _PRIMARY_METRICS["M-01"]),
        (("latency", "延迟"), _PRIMARY_METRICS["M-03"]),
        (("active client", "活跃客户"), _PRIMARY_METRICS["M-04"]),
        (("completion", "完成率", "完全成交"), _PRIMARY_METRICS["M-05"]),
        (("cancel", "撤单"), _PRIMARY_METRICS["M-06"]),
        (("order to trade", "订单成交比"), _PRIMARY_METRICS["M-07"]),
        (("self-trade", "self trade", "自成交"), _PRIMARY_METRICS["M-08"]),
        (("fill rate", "成交率"), _PRIMARY_METRICS["M-02"]),
    )
    resolved = next(
        (metric for words, metric in keyword_map if any(word in lower for word in words)),
        None,
    )
    return resolved or (context.metric_id if context is not None else None)


def _explicit_dimensions(question: str) -> list[str]:
    lower = question.lower()
    candidates = (
        (
            (
                "business date",
                "by day",
                "each day",
                "per day",
                "daily",
                "trend",
                "over time",
                "time series",
                "time-series",
                "按日",
                "每日",
                "趋势",
                "走势",
                "时序",
            ),
            "business_date",
        ),
        (("participant type", "参与者类型"), "participant_type"),
        (("participant", "参与者", "客户"), "participant"),
        (("market segment", "市场板块", "市场分部"), "market_segment"),
        (("instrument", "security", "证券", "标的"), "instrument"),
        (("venue", "交易场所"), "venue"),
        (("order type", "订单类型"), "order_type"),
        (("trading session", "session", "交易时段"), "trading_session"),
    )
    explicit: list[str] = []
    for terms, dimension in candidates:
        if any(term in lower for term in terms) and dimension not in explicit:
            explicit.append(dimension)
    return explicit[:2]


def _fallback_dimensions(
    question: str,
    context: AnalyticConversationContextV1 | None = None,
) -> list[str]:
    lower = question.lower()
    if any(token in lower for token in ("overall", "aggregate", "整体", "汇总")):
        return []
    explicit = _explicit_dimensions(question)
    if explicit:
        return explicit
    return list(context.dimensions) if context is not None else []


def _localized_metric_name(question: str, result: dict[str, Any]) -> str:
    if _is_chinese(question):
        return str(result.get("metric_name_zh") or result.get("metric_name") or result["metric_code"])
    return str(result.get("metric_name_en") or result.get("metric_name") or result["metric_code"])


def _format_metric_value(value: Any, unit: str, *, chinese: bool) -> str:
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        number = float(value)
        if abs(number - round(number)) < 1e-9:
            formatted = f"{int(round(number)):,}"
        else:
            formatted = f"{number:,.2f}".rstrip("0").rstrip(".")
    else:
        formatted = str(value)
    normalized_unit = unit.upper()
    if normalized_unit == "PERCENT":
        return f"{formatted}%"
    labels = {
        "HKD_MN": " 百万港元" if chinese else " million HKD",
        "MILLISECOND": " 毫秒" if chinese else " ms",
        "MILLISECONDS": " 毫秒" if chinese else " ms",
        "SHARE": " 股" if chinese else " shares",
    }
    return formatted + labels.get(normalized_unit, f" {unit}" if unit else "")


def _localized_limitations(question: str, result: dict[str, Any]) -> str:
    limitations = result.get("limitations") or []
    if not limitations:
        return ""
    chinese = _is_chinese(question)
    code = result.get("metric_code")
    if chinese and code in {"M-02", "M-05"}:
        return "当前样例的 EXECUTE 事件无法可靠关联到 NEW 订单生命周期，因此该结果受输入关系缺口影响，不能解释为市场没有成交。"
    if chinese and code == "M-08":
        return "该结果只表示潜在自成交排查候选，不是违规或市场操纵结论。"
    if chinese:
        return "该结果存在已登记的口径限制，请查看下方计算证据。"
    return " ".join(str(item) for item in limitations)


def _fallback_answer(question: str, result: dict[str, Any]) -> str:
    chinese = _is_chinese(question)
    rows = result["rows"]
    if not rows:
        return "所选范围没有可计算记录。" if chinese else "No calculable records were found in the selected range."
    name = _localized_metric_name(question, result)
    period = result["period"]
    unit = str(result.get("unit") or "")
    synthetic = "数据为构造型样例。" if chinese else "The data is constructed-synthetic."
    limitation = _localized_limitations(question, result)
    ending = " ".join(item for item in (synthetic, limitation) if item)
    if result["dimensions"]:
        values = [row.get("value") for row in rows]
        numeric_values = [
            float(value)
            for value in values
            if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)
        ]
        is_daily = "dimension.business_date" in result["dimensions"]
        if is_daily and len(numeric_values) == len(rows):
            first = _format_metric_value(numeric_values[0], unit, chinese=chinese)
            last = _format_metric_value(numeric_values[-1], unit, chinese=chinese)
            if max(numeric_values) - min(numeric_values) < 1e-9:
                summary = (
                    f"{period['start']} 至 {period['end']} 的 {len(rows)} 个交易日内，{name}保持在 {first}。"
                    if chinese
                    else f"{name} remained flat at {first} across {len(rows)} trading days from {period['start']} to {period['end']}."
                )
            else:
                delta = numeric_values[-1] - numeric_values[0]
                delta_value = _format_metric_value(abs(delta), unit, chinese=chinese)
                direction = ("上升" if delta > 0 else "下降") if chinese else ("increased" if delta > 0 else "decreased")
                summary = (
                    f"{period['start']} 至 {period['end']}，{name}从 {first} {direction}至 {last}，变动 {delta_value}。"
                    if chinese
                    else f"{name} {direction} from {first} to {last} between {period['start']} and {period['end']}, a change of {delta_value}."
                )
        else:
            summary = (
                f"{period['start']} 至 {period['end']}，{name}返回 {len(rows)} 条分组结果；明细见下方受治理结果表。"
                if chinese
                else f"{name} returned {len(rows)} grouped results from {period['start']} to {period['end']}; the governed result table below contains the breakdown."
            )
        return f"{summary} {ending}".strip()
    row = rows[0]
    value = _format_metric_value(row.get("value"), unit, chinese=chinese)
    return (
        f"{period['start']} 至 {period['end']}，{name}为 {value}。{ending}"
        if chinese
        else f"From {period['start']} to {period['end']}, {name} was {value}. {ending}"
    )


def _is_chinese(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", value))


def _answer_matches_question_language(question: str, answer: str) -> bool:
    if not answer.strip():
        return False
    answer_has_chinese = _is_chinese(answer)
    return answer_has_chinese if _is_chinese(question) else not answer_has_chinese


def _requires_interpretation(question: str) -> bool:
    lower = question.lower()
    return any(
        token in lower
        for token in (
            "trend",
            "compare",
            "comparison",
            "change",
            "increase",
            "decrease",
            "why",
            "explain",
            "analy",
            "explore",
            "insight",
            "anomal",
            "summar",
            "趋势",
            "走势",
            "比较",
            "对比",
            "变化",
            "上升",
            "下降",
            "为什么",
            "解释",
            "分析",
            "探索",
            "洞察",
            "异常",
            "总结",
        )
    )


def _strip_markdown_result_tables(answer: str) -> str:
    """Remove model-rendered row tables; governed rows render separately in the UI."""

    lines = answer.splitlines()
    kept: list[str] = []
    index = 0
    separator = re.compile(
        r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$"
    )
    while index < len(lines):
        if (
            index + 1 < len(lines)
            and "|" in lines[index]
            and separator.match(lines[index + 1])
        ):
            index += 2
            while index < len(lines) and "|" in lines[index]:
                index += 1
            while index < len(lines) and not lines[index].strip():
                index += 1
            continue
        kept.append(lines[index])
        index += 1
    return "\n".join(kept).strip()


def _has_unresolved_grouping_request(question: str) -> bool:
    lower = question.lower()
    grouping_cue = any(
        token in lower
        for token in (" by ", " per ", "each ", "break down", "breakdown", "按", "分组", "拆分")
    )
    return grouping_cue and not _explicit_dimensions(question)


def _normalize_single_metric_trace(
    engine: CashTradingSemanticEngine,
    question: str,
    context: AnalyticConversationContextV1 | None,
) -> bool:
    """Reconcile one model-selected query with the explicit conversational contract.

    The model remains free to understand intent and choose tools.  Once a metric,
    period and supported grain are explicit, those parameters are deterministic and
    cannot vary between provider attempts.
    """

    if len(engine.traces) != 1 or _has_unresolved_grouping_request(question):
        return False
    current = engine.traces[0]
    metric_id = _fallback_metric(question, context)
    if metric_id is None:
        return False
    start, end = _dates_from_question(question, context)
    group_by = _fallback_dimensions(question, context)
    expected_dimensions = tuple(_DIMENSIONS[item].dimension_id for item in group_by)
    if (
        current.metric_id == metric_id
        and current.start_date == start
        and current.end_date == end
        and current.dimensions == expected_dimensions
    ):
        return False
    filters = dict(current.filters)
    engine.traces.clear()
    engine.query_metric(metric_id, start, end, group_by, filters)
    return True


def _present_metric_answer(
    *,
    question: str,
    result: dict[str, Any],
    model_answer: str,
    model_error: str | None,
    trace_normalized: bool,
) -> str:
    if model_error is not None or trace_normalized or not _requires_interpretation(question):
        return _fallback_answer(question, result)
    concise_answer = _strip_markdown_result_tables(model_answer)
    if not _answer_matches_question_language(question, concise_answer):
        return _fallback_answer(question, result)
    return concise_answer


def _capability_question(question: str) -> bool:
    lower = question.lower()
    return any(
        token in lower
        for token in (
            "what can you answer",
            "what questions can",
            "what can i ask",
            "your capabilities",
            "supported questions",
            "supported analyses",
            "能回答什么",
            "可以问什么",
            "能问什么",
            "支持哪些问题",
            "支持什么分析",
            "你的能力",
        )
    )


def _definition_question(question: str) -> bool:
    lower = question.lower()
    return any(
        token in lower
        for token in (
            "defined",
            "definition",
            "what does",
            "what is the meaning",
            "calculation logic",
            "formula",
            "ontology package",
            "ontology definition",
            "如何定义",
            "定义是什么",
            "什么意思",
            "计算口径",
            "计算逻辑",
            "公式",
            "本体定义",
            "ontology 是什么",
        )
    )


def _semantic_comparison_question(question: str) -> bool:
    lower = question.lower()
    return any(
        token in lower
        for token in (
            "compare",
            "comparison",
            "different",
            "difference",
            "versus",
            " vs ",
            "区别",
            "差异",
            "不同",
            "对比",
            "比较",
        )
    )


def _evidence_question(question: str) -> bool:
    lower = question.lower()
    return any(
        token in lower
        for token in (
            "evidence",
            "source",
            "provenance",
            "assumption",
            "limitation",
            "why is this defined",
            "证据",
            "来源",
            "假设",
            "限制",
            "为什么这样定义",
        )
    )


def _mentioned_metric_ids(
    engine: CashTradingSemanticEngine, question: str
) -> tuple[str, ...]:
    """Return every explicitly named governed metric in textual order."""

    lower = question.lower()
    positions: dict[str, int] = {}

    def register(term: str, metric_id: str) -> None:
        position = lower.find(term.lower())
        if position >= 0:
            positions[metric_id] = min(position, positions.get(metric_id, position))

    for alias, metric_id in _METRIC_ALIASES.items():
        register(alias, metric_id)
    keyword_terms = {
        _PRIMARY_METRICS["M-01"]: ("reject", "拒绝"),
        _PRIMARY_METRICS["M-02"]: ("fill rate", "成交率"),
        _PRIMARY_METRICS["M-03"]: ("latency", "延迟"),
        _PRIMARY_METRICS["M-04"]: ("active client", "活跃客户"),
        _PRIMARY_METRICS["M-05"]: ("completion", "完成率", "完全成交"),
        _PRIMARY_METRICS["M-06"]: ("cancel", "撤单"),
        _PRIMARY_METRICS["M-07"]: ("order to trade", "order-to-trade", "订单成交比"),
        _PRIMARY_METRICS["M-08"]: ("self-trade", "self trade", "自成交"),
    }
    for metric_id, terms in keyword_terms.items():
        for term in terms:
            register(term, metric_id)
    for metric in engine.package.metrics:
        for term in (metric.id, metric.name.en, metric.name.zh or ""):
            if term:
                register(term, metric.id)
    return tuple(metric_id for metric_id, _ in sorted(positions.items(), key=lambda item: item[1]))


def _record_metric_semantic_trace(
    engine: CashTradingSemanticEngine,
    question: str,
    metric_ids: Sequence[str],
) -> SemanticTrace:
    metrics_by_id = {item.id: item for item in engine.package.metrics}
    metrics = [metrics_by_id[item] for item in metric_ids if item in metrics_by_id]
    assets = [
        {
            "id": item.id,
            "name": {"en": item.name.en, "zh": item.name.zh},
            "definition": item.definition,
            "status": item.status,
            "sources": list(item.sources),
            "decisions": list(item.decisions),
        }
        for item in metrics
    ]
    engine._record_semantic(
        operation="inspect_ontology",
        topic=question,
        result={
            "package_id": engine.package.package_id,
            "version": engine.package.version,
            "assets": {
                "entities": [],
                "relationships": [],
                "metrics": assets,
                "dimensions": [],
                "rules": [],
            },
        },
        source_ids=[source for item in metrics for source in item.sources],
        decision_ids=[decision for item in metrics for decision in item.decisions],
        metric_ids=[item.id for item in metrics],
    )
    return engine.semantic_traces[-1]


def _semantic_answer_covers_metrics(
    answer: str,
    trace: SemanticTrace,
    metric_ids: Sequence[str],
) -> bool:
    lower = answer.lower()
    assets = trace.result.get("assets", {}).get("metrics", [])
    by_id = {str(item.get("id")): item for item in assets}
    for metric_id in metric_ids:
        asset = by_id.get(metric_id)
        if asset is None:
            return False
        names = asset.get("name") or {}
        identifiers = (
            metric_id,
            str(names.get("en") or ""),
            str(names.get("zh") or ""),
        )
        if not any(identifier and identifier.lower() in lower for identifier in identifiers):
            return False
    return True


def _semantic_topic(engine: CashTradingSemanticEngine, question: str) -> str:
    metric_id = _fallback_metric(question)
    if metric_id:
        return metric_id
    lower = question.lower()
    matches: list[tuple[int, str]] = []
    assets = (
        *engine.package.entities,
        *engine.package.relationships,
        *engine.package.dimensions,
        *engine.package.rules,
        *engine.package.properties,
    )
    for asset in assets:
        for candidate in (asset.id, asset.name.en, asset.name.zh or ""):
            normalized = candidate.strip().lower()
            if normalized and normalized in lower:
                matches.append((len(normalized), asset.id))
    return max(matches)[1] if matches else ""


def _fallback_semantic_trace(
    engine: CashTradingSemanticEngine, question: str
) -> SemanticTrace | None:
    if _capability_question(question):
        engine.describe_capabilities()
    elif _evidence_question(question):
        engine.evidence_for(_semantic_topic(engine, question))
    elif _definition_question(question):
        engine.ontology_catalog(_semantic_topic(engine, question))
    elif any(
        token in question.lower()
        for token in (
            "ontology",
            "entity",
            "relationship",
            "dimension",
            "metric catalog",
            "本体",
            "实体",
            "关系",
            "维度",
            "指标目录",
        )
    ):
        engine.ontology_catalog(_semantic_topic(engine, question))
    return engine.semantic_traces[-1] if engine.semantic_traces else None


def _semantic_fallback_answer(question: str, trace: SemanticTrace) -> str:
    chinese = _is_chinese(question)
    if trace.operation == "describe_capabilities":
        metrics = trace.result["metrics"]
        metric_lines = [
            f"- {item['code']}：{item['name'].get('zh') or item['name']['en']}"
            if chinese
            else f"- {item['code']}: {item['name']['en']}"
            for item in metrics
        ]
        dimensions = ", ".join(item["name"] for item in trace.result["dimensions"])
        if chinese:
            return (
                "我可以基于当前 Cash Trading Ontology Package 回答以下八项受治理指标，"
                "并支持总体值、按日趋势和最多两个维度的拆分：\n"
                + "\n".join(metric_lines)
                + f"\n可用维度：{dimensions}。数据期间为 {_DATA_START} 至 {_DATA_END}。"
                "我也可以解释对象、关系、指标定义、来源证据、假设与已知限制。"
            )
        return (
            "I can answer the following eight governed Cash Trading metrics, including "
            "aggregate values, daily trends and breakdowns by up to two dimensions:\n"
            + "\n".join(metric_lines)
            + f"\nAvailable dimensions: {dimensions}. The bound data period is {_DATA_START} to {_DATA_END}. "
            "I can also explain ontology objects, relationships, metric definitions, source evidence, assumptions and known limitations."
        )
    asset_groups = trace.result.get("assets") or trace.result.get("matching_assets") or {}
    assets = [asset for group in asset_groups.values() for asset in group]
    if assets:
        lines = []
        for asset in assets[:8]:
            name = (
                asset["name"].get("zh") or asset["name"].get("en")
                if chinese
                else asset["name"].get("en") or asset["name"].get("zh")
            )
            lines.append(f"- {name} (`{asset['id']}`): {asset['definition']}")
        metric_ids = {str(asset.get("id")) for asset in asset_groups.get("metrics", [])}
        if len(metric_ids) >= 2 and _semantic_comparison_question(question):
            if {
                _PRIMARY_METRICS["M-01"],
                _PRIMARY_METRICS["M-02"],
            }.issubset(metric_ids):
                distinction = (
                    "关键区别：订单成交率是基于成交数量与提交数量的数量口径；订单拒绝率是基于被拒绝与已提交的不同订单生命周期数量的事件口径。二者衡量不同阶段，并非互补指标。"
                    if chinese
                    else "Key difference: Order Fill Rate is quantity-based, using executed versus submitted quantity; Order Rejection Rate is lifecycle-count-based, using rejected versus submitted distinct order lifecycles. They measure different stages and are not complementary metrics."
                )
            else:
                distinction = (
                    "关键区别在于各自受治理定义中的业务事件、分子与分母；除非 Ontology 明确定义关系，否则不能从其中一个指标推导另一个。"
                    if chinese
                    else "The distinction lies in the governed business event, numerator and denominator defined for each metric; one must not be inferred from another unless the ontology explicitly defines that relationship."
                )
            introduction = "当前生效 Ontology 中的指标定义：" if chinese else "Metric definitions in the active ontology:"
            return introduction + "\n" + "\n".join(lines) + "\n\n" + distinction
        introduction = "当前生效 Ontology 中的匹配定义：" if chinese else "Matching definitions in the active ontology:"
        return introduction + "\n" + "\n".join(lines)
    if trace.operation == "retrieve_evidence":
        return (
            "当前 Ontology Package 没有找到更精确的来源锚点；可确认的限制包括：构造型样例数据、订单生命周期可能不完整、自成交结果仅用于排查。"
            if chinese
            else "The active ontology has no more specific source anchor for that topic. Confirmed limitations are that the data is constructed-synthetic, order lifecycles may be incomplete, and self-trade results are triage signals only."
        )
    return (
        "请指定要查看的对象、关系、指标、维度或规则名称。"
        if chinese
        else "Please name the object, relationship, metric, dimension or rule you want to inspect."
    )


def _preflight_boundary(question: str, role: str) -> QueryBoundary | None:
    lower = question.lower()
    dates = [date.fromisoformat(item) for item in re.findall(r"20\d{2}-\d{2}-\d{2}", question)]
    if any(item < _DATA_START or item > _DATA_END for item in dates):
        return QueryBoundary(
            status="CLARIFY",
            code="DATE_OUT_OF_RANGE",
            answer_en=f"The bound demo data covers {_DATA_START} through {_DATA_END}. Please use a date within that range.",
            answer_zh=f"当前绑定的演示数据覆盖 {_DATA_START} 至 {_DATA_END}，请使用该范围内的日期。",
        )
    misconduct_terms = (
        "market manipulation",
        "market abuse",
        "misconduct",
        "violation",
        "违法",
        "违规",
        "操纵市场",
        "市场操纵",
    )
    conclusion_terms = ("prove", "committed", "confirm", "conclude", "证明", "认定", "确认")
    if any(item in lower for item in misconduct_terms) and any(
        item in lower for item in conclusion_terms
    ):
        return QueryBoundary(
            status="REFUSED",
            code="UNSUPPORTED_MISCONDUCT_CONCLUSION",
            answer_en="This ontology can identify potential self-trade triage candidates, but it cannot prove or conclude misconduct or market abuse.",
            answer_zh="该 Ontology 可以识别潜在自成交排查候选，但不能证明或认定违规、市场操纵或市场滥用。",
        )
    if role == "MarketsDemo" and any(
        item in lower for item in ("participant id", "participant_id", "参与者id", "参与者 id")
    ) and any(item in lower for item in ("list", "timeline", "raw", "明细", "列表", "时间线")):
        return QueryBoundary(
            status="REFUSED",
            code="DETAIL_GRAIN_DENIED",
            answer_en="The Markets role cannot access participant-level detail. Use an aggregate market or instrument dimension instead.",
            answer_zh="Markets 角色无权访问参与者级明细，请改用市场或证券等聚合维度。",
        )
    outside_terms = (
        "weather",
        "president",
        "latest news",
        "write code",
        "write a poem",
        "天气",
        "总统",
        "最新新闻",
        "写代码",
        "写首诗",
    )
    if any(item in lower for item in outside_terms):
        return QueryBoundary(
            status="REFUSED",
            code="OUTSIDE_ACTIVE_ONTOLOGY",
            answer_en="That question is outside the active Cash Trading ontology and its bound data.",
            answer_zh="该问题超出当前 Cash Trading Ontology 及其绑定数据的范围。",
        )
    return None


def _boundary_response(
    snapshot: VerifiedSnapshot,
    question: str,
    boundary: QueryBoundary,
    turn: AnalyticTurnLeaseV1 | None = None,
) -> AnalysisResponse:
    return AnalysisResponse(
        status=boundary.status,
        answer=boundary.answer_zh if _is_chinese(question) else boundary.answer_en,
        snapshot_checksum=snapshot.snapshot_checksum,
        boundary_code=boundary.code,
        **(turn.response_fields() if turn is not None else {}),
    )


def _agent_run(
    *,
    engine: CashTradingSemanticEngine,
    question: str,
    model: BaseChatModel,
) -> tuple[str, int]:
    graph = create_deep_agent(
        model=model,
        tools=_deepagent_tools(engine),
        system_prompt=_system_prompt(
            engine.package, engine.role, engine.conversation_context
        ),
        checkpointer=(
            _CASH_CONVERSATION_CHECKPOINTER if engine.conversation_id else None
        ),
        name="cash_trading_analytic_agent",
    )
    config: dict[str, Any] = {"recursion_limit": 18}
    if engine.conversation_id:
        config["configurable"] = {"thread_id": engine.conversation_id}
    output = graph.invoke(
        {"messages": [{"role": "user", "content": question}]},
        # Three domain tools support the complete analytic path.  This ceiling
        # catches genuine model loops while leaving room for ontology lookup,
        # metric execution, evidence retrieval and answer composition.
        config=config,
    )
    messages = list(output.get("messages", ()))
    assistant_messages = [item for item in messages if isinstance(item, AIMessage)]
    final_message = assistant_messages[-1] if assistant_messages else None
    return _message_text(final_message), len(assistant_messages)


def _agent_execution_metadata(
    *, selected_model: Any | None, model_calls: int, model_error: str | None
) -> dict[str, Any]:
    if selected_model is None:
        execution_status = "DETERMINISTIC_ONLY"
        fallback_used = False
        reason = "MODEL_NOT_CONFIGURED"
        mode = "OFF"
    elif model_error is not None:
        execution_status = "FALLBACK"
        fallback_used = True
        reason = f"DEEPAGENT_{model_error.upper()}"
        mode = "ACTIVE"
    else:
        execution_status = "GROUNDED"
        fallback_used = False
        reason = None
        mode = "ACTIVE"
    return {
        "contract": "solution-llm-execution/v1",
        "mode": mode,
        "status": execution_status,
        "provider": "qwen",
        "requested_model": _MODEL_NAME,
        "model_called": model_calls > 0,
        "provider_call_count": min(model_calls, 12),
        "fallback_used": fallback_used,
        "reason_code": reason,
        "profile_checksum": None,
        "activation_id": (
            "cash-trading.deepagent.v1" if selected_model is not None else None
        ),
    }


def _build_semantic_response(
    *,
    snapshot: VerifiedSnapshot,
    trace: SemanticTrace,
    question: str,
    role: str,
    answer: str,
    execution_dir: Path,
    agent_execution: dict[str, Any],
    turn: AnalyticTurnLeaseV1 | None = None,
) -> AnalysisResponse:
    policy = next(item for item in snapshot.package.policies if role in item.allowed_roles)
    execution_id = "exec." + uuid.uuid4().hex
    policy_decision_id = "policy-decision." + sha256_value(
        {
            "policy": policy.id,
            "role": role,
            "question": question,
            "snapshot": snapshot.snapshot_checksum,
        }
    )[:16]
    plan_payload = {
        "intent": "ontology_assistance",
        "question": question,
        "snapshot_checksum": snapshot.snapshot_checksum,
        "steps": [],
    }
    plan_hash = sha256_value(plan_payload)
    plan = AnalysisPlan(
        plan_id="plan." + plan_hash[:16],
        plan_hash=plan_hash,
        **plan_payload,
    )
    step = StepExecution(
        step_id="semantic-lookup",
        status="PASS",
        rows=(
            {
                "operation": trace.operation,
                "topic": trace.topic,
                "trace_hash": trace.trace_hash,
            },
        ),
    )
    metric_versions = {
        item.id: item.version for item in snapshot.package.metrics
    }
    evidence = EvidenceRecord(
        claim_id="claim.cash.semantic." + trace.trace_hash[:16],
        claim_type="definition",
        claim=f"{trace.operation} is grounded in the active ontology package.",
        result_path="/facts/semantic/result",
        value=json.dumps(trace.result, ensure_ascii=False, sort_keys=True),
        display_value=f"{trace.operation}: {trace.topic}",
        execution_id=execution_id,
        snapshot_checksum=snapshot.snapshot_checksum,
        plan_hash=plan_hash,
        dataset_checksum=snapshot.dataset_checksum,
        policy_id=policy.id,
        policy_decision_id=policy_decision_id,
        query_or_operator_hashes=(trace.trace_hash,),
        metric_ids=trace.metric_ids,
        metric_versions=tuple(
            metric_versions[item]
            for item in trace.metric_ids
            if item in metric_versions
        ),
        mapping_ids=(),
        source_ids=trace.source_ids,
        step_ids=(step.step_id,),
    )
    context_after = (
        turn.context_before.model_copy(
            update={"role": role, "last_execution_id": execution_id}
        )
        if turn is not None
        else None
    )
    response = AnalysisResponse(
        status="ANSWERED",
        answer=answer,
        execution_id=execution_id,
        snapshot_checksum=snapshot.snapshot_checksum,
        plan=plan,
        steps=(step,),
        facts={
            "semantic": {
                "operation": trace.operation,
                "topic": trace.topic,
                "result": trace.result,
            },
            "_agent_execution": agent_execution,
            **(
                {"_conversation_context": context_after.model_dump(mode="json")}
                if context_after is not None
                else {}
            ),
        },
        evidence=(evidence,),
        **(turn.response_fields() if turn is not None else {}),
    )
    write_json(execution_dir / f"{execution_id}.json", response.model_dump(mode="json"))
    return response


def _build_response(
    *,
    snapshot: VerifiedSnapshot,
    engine: CashTradingSemanticEngine,
    question: str,
    role: str,
    answer: str,
    execution_dir: Path,
    agent_execution: dict[str, Any],
    turn: AnalyticTurnLeaseV1 | None = None,
) -> AnalysisResponse:
    policy = next(item for item in snapshot.package.policies if role in item.allowed_roles)
    execution_id = "exec." + uuid.uuid4().hex
    steps: list[StepExecution] = []
    plan_steps: list[PlanStep] = []
    evidence: list[EvidenceRecord] = []
    policy_decision_id = "policy-decision." + sha256_value(
        {"policy": policy.id, "role": role, "question": question, "snapshot": snapshot.snapshot_checksum}
    )[:16]
    for index, trace in enumerate(engine.traces):
        step_id = f"metric-query-{index + 1}"
        period_id = f"{trace.start_date}..{trace.end_date}"
        contract_payload = {
            "operation": "cash.query_metric",
            "operator_version": "2.0.0",
            "analysis_pattern": "analysis.cash_metric_query",
            "scenario_id": snapshot.package.scenario.id,
            "metric": trace.metric_id,
            "periods": (period_id,),
            "period_bounds": (
                PeriodDefinition(
                    id=period_id,
                    start=date.fromisoformat(trace.start_date),
                    end=date.fromisoformat(trace.end_date),
                    inclusive=True,
                ),
            ),
            "dimensions": trace.dimensions,
            "result_grain": trace.dimensions or ("aggregate",),
            "filters": tuple(f"{key}={value}" for key, value in trace.filters.items()),
            "source_ids": trace.source_ids,
            "population_id": f"{snapshot.package.scenario.id}:{snapshot.package.scenario.market_id}",
            "market_id": snapshot.package.scenario.market_id,
            "timezone": snapshot.package.scenario.timezone,
            "policy_id": policy.id,
            "policy_decision_id": policy_decision_id,
            "role": role,
            "snapshot_checksum": snapshot.snapshot_checksum,
        }
        contract = AtomicQueryContract(
            contract_id="aqc." + sha256_value(contract_payload)[:16],
            **contract_payload,
        )
        plan_steps.append(
            PlanStep(step_id=step_id, operation="cash.query_metric", contract=contract)
        )
        steps.append(
            StepExecution(
                step_id=step_id,
                status="PASS",
                sql=trace.sql,
                params=trace.params,
                sql_hash=trace.sql_hash,
                rows=tuple(trace.rows),
            )
        )
    plan_payload = {
        "intent": "cash_metric_analysis",
        "question": question,
        "snapshot_checksum": snapshot.snapshot_checksum,
        "steps": [item.model_dump(mode="json") for item in plan_steps],
    }
    plan_hash = sha256_value(plan_payload)
    plan = AnalysisPlan(
        plan_id="plan." + plan_hash[:16], plan_hash=plan_hash, **plan_payload
    )
    metrics = {item.id: item for item in snapshot.package.metrics}
    for index, trace in enumerate(engine.traces):
        metric = metrics[trace.metric_id]
        evidence.append(
            EvidenceRecord(
                claim_id=f"claim.cash.{trace.metric_code.lower()}.{index + 1}",
                claim_type="numeric",
                claim=f"{metric.name.en} deterministic result",
                result_path=f"/facts/queries/{index}/rows",
                value=json.dumps(trace.rows, ensure_ascii=False, sort_keys=True),
                display_value=f"{len(trace.rows)} result row(s)",
                unit=trace.unit,
                execution_id=execution_id,
                snapshot_checksum=snapshot.snapshot_checksum,
                plan_hash=plan_hash,
                dataset_checksum=snapshot.dataset_checksum,
                policy_id=policy.id,
                policy_decision_id=policy_decision_id,
                query_or_operator_hashes=(trace.sql_hash,),
                metric_ids=(trace.metric_id,),
                metric_versions=(metric.version,),
                mapping_ids=trace.mapping_ids,
                source_ids=trace.source_ids,
                step_ids=(f"metric-query-{index + 1}",),
            )
        )
    facts = {
        "queries": [trace.public_result() for trace in engine.traces],
        "visualization": {
            "kind": "line" if any(trace.dimensions for trace in engine.traces) else "kpi",
            "x": "business_date" if any(trace.dimensions for trace in engine.traces) else None,
            "y": "value",
        },
        "limitations": [
            "Constructed-synthetic data; not HKEX validated.",
            "Observed order lifecycles may be incomplete.",
        ],
        "_agent_execution": agent_execution,
    }
    if turn is not None and engine.traces:
        final_trace = engine.traces[-1]
        facts["_conversation_context"] = AnalyticConversationContextV1(
            metric_id=final_trace.metric_id,
            start_date=final_trace.start_date,
            end_date=final_trace.end_date,
            dimensions=final_trace.dimensions,
            filters=final_trace.filters,
            role=role,
            last_execution_id=execution_id,
        ).model_dump(mode="json")
    response = AnalysisResponse(
        status="ANSWERED",
        answer=answer,
        execution_id=execution_id,
        snapshot_checksum=snapshot.snapshot_checksum,
        plan=plan,
        steps=tuple(steps),
        facts=facts,
        evidence=tuple(evidence),
        **(turn.response_fields() if turn is not None else {}),
    )
    write_json(execution_dir / f"{execution_id}.json", response.model_dump(mode="json"))
    return response


def analyze_cash_deepagent_snapshot(
    snapshot: VerifiedSnapshot,
    *,
    question: str,
    role: str,
    execution_dir: Path,
    model: BaseChatModel | None = None,
    turn: AnalyticTurnLeaseV1 | None = None,
) -> AnalysisResponse:
    try:
        verify_snapshot_handle(snapshot)
    except PublicationError:
        return AnalysisResponse(
            status="FAILED",
            answer="The active Cash Trading package failed integrity verification.",
            boundary_code="SNAPSHOT_VERIFICATION_FAILED",
            **(turn.response_fields() if turn is not None else {}),
        )
    if role not in _ALLOWED_ROLES:
        return AnalysisResponse(
            status="REFUSED",
            answer=(
                f"角色 {role} 无权分析该解决方案。"
                if _is_chinese(question)
                else f"Role {role} is not permitted to analyze this solution."
            ),
            boundary_code="ROLE_DENIED",
            **(turn.response_fields() if turn is not None else {}),
        )
    preflight_boundary = _preflight_boundary(question, role)
    if preflight_boundary is not None:
        return _boundary_response(snapshot, question, preflight_boundary, turn)
    engine = CashTradingSemanticEngine(
        snapshot.package,
        snapshot.resource_paths,
        role,
        conversation_id=(turn.conversation_id if turn is not None else None),
        conversation_context=(turn.context_before if turn is not None else None),
    )
    selected_model = model or _configured_model()
    answer = ""
    model_calls = 0
    model_error: str | None = None
    if selected_model is not None:
        try:
            answer, model_calls = _agent_run(
                engine=engine, question=question, model=selected_model
            )
        except Exception as exc:  # provider/tool failure falls back to the same semantic engine
            model_calls = 1
            model_error = type(exc).__name__
    if engine.boundary is not None:
        return _boundary_response(snapshot, question, engine.boundary, turn)
    if (
        selected_model is not None
        and model_error is None
        and not engine.traces
        and not engine.semantic_traces
    ):
        model_error = "UNGROUNDED_RESPONSE"
    agent_execution = _agent_execution_metadata(
        selected_model=selected_model,
        model_calls=model_calls,
        model_error=model_error,
    )
    mentioned_metric_ids = _mentioned_metric_ids(engine, question)
    if len(mentioned_metric_ids) >= 2 and _semantic_comparison_question(question):
        trace = _record_metric_semantic_trace(
            engine,
            question,
            mentioned_metric_ids,
        )
        if (
            model_error is not None
            or not _answer_matches_question_language(question, answer)
            or not _semantic_answer_covers_metrics(answer, trace, mentioned_metric_ids)
        ):
            answer = _semantic_fallback_answer(question, trace)
        return _build_semantic_response(
            snapshot=snapshot,
            trace=trace,
            question=question,
            role=role,
            answer=answer,
            execution_dir=execution_dir,
            agent_execution=agent_execution,
            turn=turn,
        )
    if engine.traces:
        try:
            trace_normalized = _normalize_single_metric_trace(
                engine,
                question,
                turn.context_before if turn is not None else None,
            )
        except CashTradingQueryBoundary as exc:
            return _boundary_response(snapshot, question, exc.boundary, turn)
        result = engine.traces[-1].public_result()
        answer = _present_metric_answer(
            question=question,
            result=result,
            model_answer=answer,
            model_error=model_error,
            trace_normalized=trace_normalized,
        )
        return _build_response(
            snapshot=snapshot,
            engine=engine,
            question=question,
            role=role,
            answer=answer,
            execution_dir=execution_dir,
            agent_execution=agent_execution,
            turn=turn,
        )
    if engine.semantic_traces:
        trace = engine.semantic_traces[-1]
        if not _answer_matches_question_language(question, answer):
            answer = _semantic_fallback_answer(question, trace)
        return _build_semantic_response(
            snapshot=snapshot,
            trace=trace,
            question=question,
            role=role,
            answer=answer,
            execution_dir=execution_dir,
            agent_execution=agent_execution,
            turn=turn,
        )

    semantic_trace = _fallback_semantic_trace(engine, question)
    if semantic_trace is not None:
        return _build_semantic_response(
            snapshot=snapshot,
            trace=semantic_trace,
            question=question,
            role=role,
            answer=_semantic_fallback_answer(question, semantic_trace),
            execution_dir=execution_dir,
            agent_execution=agent_execution,
            turn=turn,
        )

    conversation_context = turn.context_before if turn is not None else None
    metric_id = _fallback_metric(question, conversation_context)
    if metric_id is not None:
        start, end = _dates_from_question(question, conversation_context)
        group_by = _fallback_dimensions(question, conversation_context)
        filters = (
            dict(conversation_context.filters)
            if conversation_context is not None
            else None
        )
        try:
            result = engine.query_metric(metric_id, start, end, group_by, filters)
        except CashTradingQueryBoundary as exc:
            return _boundary_response(snapshot, question, exc.boundary, turn)
        return _build_response(
            snapshot=snapshot,
            engine=engine,
            question=question,
            role=role,
            answer=_fallback_answer(question, result),
            execution_dir=execution_dir,
            agent_execution=agent_execution,
            turn=turn,
        )

    return AnalysisResponse(
        status="CLARIFY",
        answer=(
            "我可以计算 M-01 至 M-08，或解释当前 Ontology 中的对象、关系、指标、维度、证据和限制。请说明你想了解哪一项。"
            if _is_chinese(question)
            else "I can calculate M-01 through M-08 or explain objects, relationships, metrics, dimensions, evidence and limitations in the active ontology. Please specify the topic."
        ),
        snapshot_checksum=snapshot.snapshot_checksum,
        boundary_code="INTENT_NOT_RESOLVED",
        **(turn.response_fields() if turn is not None else {}),
    )
