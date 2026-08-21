from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from ontology_agent.io import file_checksum, package_checksum
from ontology_agent.models import OntologyPackage
from ontology_agent.validation import failed_checks, validate_semantic_package


DOMAIN_OWNER = "actor.cash_trading_domain_owner"
DATA_STEWARD = "actor.cash_trading_data_steward"


def _governed(
    identifier: str,
    en: str,
    zh: str,
    definition: str,
    *,
    owner: str = DOMAIN_OWNER,
    sources: list[str] | None = None,
    decisions: list[str] | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "status": "confirmed",
        "name": {"en": en, "zh": zh},
        "definition": definition,
        "owner": owner,
        "sources": sources or ["source.assumption_register"],
        "decisions": decisions or [],
        "tags": tags or ["constructed_synthetic", "cash_trading"],
    }


def _field_type(arrow_type: str) -> str:
    if arrow_type == "string":
        return "string"
    if arrow_type.startswith("int"):
        return "integer"
    if arrow_type.startswith("decimal"):
        return "decimal"
    if arrow_type.startswith("date32"):
        return "date"
    if arrow_type.startswith("timestamp"):
        return "datetime"
    if arrow_type == "bool":
        return "boolean"
    raise RuntimeError(f"Unsupported Arrow type in schema manifest: {arrow_type}")


def _raw_unit(table: str, field: str) -> str | None:
    exact = {
        ("trading_activity", "trade_quantity"): "SHARE",
        ("trading_activity", "trade_notional"): "HKD",
        ("trading_activity", "base_notional_before_haircut"): "USD",
        ("trading_activity", "base_notional_after_haircut"): "USD",
        ("trading_activity", "haircut_rate"): "RATIO",
        ("trading_activity", "fx_rate_to_base"): "USD_PER_HKD",
        ("order_activity", "order_quantity"): "SHARE",
        ("order_activity", "executed_quantity"): "SHARE",
        ("order_activity", "cumulative_executed_quantity"): "SHARE",
        ("order_activity", "unfilled_quantity"): "SHARE",
        ("exchange_rate", "exchange_rate"): "TO_CURRENCY_PER_FROM_CURRENCY",
        ("exchange_rate", "haircut_rate"): "RATIO",
    }
    return exact.get((table, field))


def _property(
    identifier: str,
    en: str,
    zh: str,
    definition: str,
    *,
    entity: str,
    data_type: str,
    required: bool,
    unit: str | None = None,
    sources: list[str] | None = None,
    decisions: list[str] | None = None,
    enum_values: list[str] | None = None,
) -> dict[str, Any]:
    value = _governed(
        identifier,
        en,
        zh,
        definition,
        owner=DATA_STEWARD,
        sources=sources or ["source.data_dictionary"],
        decisions=decisions,
    )
    value.update(
        {
            "entity": entity,
            "data_type": data_type,
            "required": required,
            "unit": unit,
            "enum_values": enum_values or [],
        }
    )
    return value


def _binding(
    identifier: str,
    logical_target: str,
    column: str,
    data_type: str,
    *,
    unit: str | None = None,
    transformation: str = "identity",
    source: str = "source.cash_trade_analytics",
    table: str = "cash_trade_analytics",
) -> dict[str, Any]:
    value = _governed(
        identifier,
        f"Binding for {logical_target}",
        f"{logical_target}绑定",
        f"Synthetic runtime binding for {logical_target}.",
        owner=DATA_STEWARD,
        sources=["source.data_dictionary", "source.assumption_register"],
    )
    value.update(
        {
            "logical_target": logical_target,
            "source": source,
            "table": table,
            "column": column,
            "data_type": data_type,
            "unit": unit,
            "transformation": transformation,
        }
    )
    return value


def _source_ref(
    identifier: str,
    source_type: str,
    title: str,
    locator: str,
    trust: str,
    notes: str,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "source_type": source_type,
        "title": title,
        "locator": locator,
        "owner": "Deloitte HK" if "Deloitte" in title else "PoC Product & Domain Team",
        "captured_on": "2026-08-20",
        "trust": trust,
        "notes": notes,
    }


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    scenario_root = project_root / "scenarios" / "cash_trading"
    schema_path = scenario_root / "data" / "schema.json"
    data_manifest_path = scenario_root / "data" / "manifest.json"
    source_manifest_path = scenario_root / "intake" / "source-manifest.json"
    assumption_path = scenario_root / "governance" / "assumption-register.json"
    oracle_path = scenario_root / "golden" / "oracle.json"
    sql_path = scenario_root / "sql" / "reference_controls.sql"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    data_manifest = json.loads(data_manifest_path.read_text(encoding="utf-8"))
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))

    raw_data_sources: list[dict[str, Any]] = []
    raw_tables: dict[str, dict[str, Any]] = {}
    for table in schema["tables"]:
        table_name = table["table"]
        field_definitions = [
            {
                "name": field["name"],
                "data_type": _field_type(field["arrow_type"]),
                "nullable": field["nullable"],
                "description": field["description"],
                "unit": _raw_unit(table_name, field["name"]),
            }
            for field in table["fields"]
        ]
        table_definition = {
            "name": table_name,
            "grain": f"one constructed-synthetic {table_name} row",
            "primary_key": table["primary_key"],
            "fields": field_definitions,
        }
        raw_tables[table_name] = table_definition
        source = _governed(
            f"source.{table_name}",
            table_name.replace("_", " ").title(),
            table_name,
            f"Typed Parquet projection of the supplied constructed-synthetic {table_name} worksheet.",
            owner=DATA_STEWARD,
            sources=["source.data_dictionary", "source.sample_data"],
            decisions=["decision.source_classification"],
            tags=["constructed_synthetic", "parquet", "raw_projection"],
        )
        source.update({"protocol": "tabular/v1", "tables": [table_definition]})
        raw_data_sources.append(source)

    analytic_fields = [
        ("trading_activity_id", "string", False, "Stable trade-activity identifier.", None),
        ("business_date", "date", False, "Venue-calendar business date.", None),
        ("venue_code", "string", False, "Normalized venue code.", None),
        ("market_segment", "string", True, "Cash-market segment.", None),
        ("instrument_id", "string", False, "Instrument identifier.", None),
        ("participant_id", "string", True, "Associated participant identifier.", None),
        ("buy_participant_id", "string", True, "Normalized buying participant identifier.", None),
        ("sell_participant_id", "string", True, "Normalized selling participant identifier.", None),
        ("trade_quantity", "decimal", False, "Executed quantity.", "SHARE"),
        ("trade_notional_hkd", "decimal", False, "Native executed notional in HKD.", "HKD"),
        ("base_notional_usd", "decimal", False, "Converted notional before haircut in USD.", "USD"),
        ("transaction_timestamp", "datetime", False, "Matching-engine transaction timestamp in UTC.", None),
        ("receive_timestamp", "datetime", False, "Platform receive timestamp in UTC.", None),
        ("is_eligible_trade", "boolean", False, "True when the provisional eligible-trade rule passes.", None),
        ("is_active_client", "boolean", False, "True when participant_id resolves to an effective CLIENT reference row.", None),
        ("has_both_participant_ids", "boolean", False, "True when both side participant IDs are populated.", None),
        ("is_potential_self_trade", "boolean", False, "True when both normalized side participant IDs are equal.", None),
        ("is_nonnegative_latency", "boolean", False, "True when capture latency is non-negative.", None),
        ("capture_latency_ms", "integer", True, "Receive time minus transaction time in milliseconds.", "MILLISECOND"),
    ]
    analytic_source = _governed(
        "source.cash_trade_analytics",
        "Cash Trade Analytic View",
        "现金交易分析视图",
        "Adapter-owned deterministic view over the exact trading-activity Parquet source.",
        owner=DATA_STEWARD,
        sources=["source.data_dictionary", "source.assumption_register", "source.compiler_sql"],
        decisions=[
            "decision.self_trade_candidate",
            "decision.trade_eligibility",
            "decision.latency_convention",
            "decision.notional_currency",
        ],
        tags=["constructed_synthetic", "adapter_view", "executable"],
    )
    analytic_source.update(
        {
            "protocol": "tabular/v1",
            "tables": [
                {
                    "name": "cash_trade_analytics",
                    "grain": "one normalized trading activity row",
                    "primary_key": ["trading_activity_id"],
                    "fields": [
                        {
                            "name": name,
                            "data_type": data_type,
                            "nullable": nullable,
                            "description": description,
                            "unit": unit,
                        }
                        for name, data_type, nullable, description, unit in analytic_fields
                    ],
                }
            ],
        }
    )

    order_analytic_fields = [
        ("lifecycle_key", "string", False, "Stable venue + trading date + order identifier.", None),
        ("trading_date", "date", False, "Business date assigned to the observed lifecycle.", None),
        ("venue_code", "string", False, "Normalized venue code.", None),
        ("market_segment", "string", True, "Cash-market segment from the latest observed state.", None),
        ("instrument_id", "string", False, "Instrument identifier from the latest observed state.", None),
        ("participant_id", "string", True, "Participant identifier from the latest observed state.", None),
        ("is_client", "boolean", False, "True when the effective participant reference is classified CLIENT.", None),
        ("is_submitted", "boolean", False, "True when the lifecycle contains a NEW or REJECT submission attempt.", None),
        ("is_rejected", "boolean", False, "True when any observed event rejects the submission.", None),
        ("is_eligible_client_order", "boolean", False, "True for a submitted client lifecycle with no observed rejection.", None),
        ("is_fully_filled", "boolean", False, "True when the latest valid observed state is FILLED.", None),
        ("is_canceled", "boolean", False, "True when the lifecycle contains an eligible cancel event.", None),
        ("final_order_quantity", "integer", False, "Order quantity at the latest valid observed state.", "SHARE"),
        ("final_cumulative_executed_quantity", "integer", False, "Cumulative executed quantity at the latest valid observed state.", "SHARE"),
    ]
    order_analytic_source = _governed(
        "source.cash_order_lifecycle_analytics",
        "Cash Order Lifecycle Analytic View",
        "现金订单生命周期分析视图",
        "Adapter-owned deterministic lifecycle view over exact order events and effective participant reference data.",
        owner=DATA_STEWARD,
        sources=["source.data_dictionary", "source.assumption_register", "source.compiler_sql"],
        decisions=[
            "decision.order_lifecycle",
            "decision.submitted_order",
            "decision.rejected_order",
            "decision.client_classification",
            "decision.cancel_ratio",
        ],
        tags=["constructed_synthetic", "adapter_view", "ontology_ready"],
    )
    order_analytic_source.update(
        {
            "protocol": "tabular/v1",
            "tables": [
                {
                    "name": "cash_order_lifecycle_analytics",
                    "grain": "one normalized observed order lifecycle",
                    "primary_key": ["lifecycle_key"],
                    "fields": [
                        {
                            "name": name,
                            "data_type": data_type,
                            "nullable": nullable,
                            "description": description,
                            "unit": unit,
                        }
                        for name, data_type, nullable, description, unit in order_analytic_fields
                    ],
                }
            ],
        }
    )

    actors = [
        (
            DOMAIN_OWNER,
            "Cash Trading Demo Domain Owner",
            "现金交易演示业务负责人",
            "Accountable owner for provisional synthetic definitions and demo claims.",
            ["DomainOwner", "SemanticApprover"],
        ),
        (
            DATA_STEWARD,
            "Cash Trading Data Steward",
            "现金交易数据管理员",
            "Owner of typed schema, mappings and data-quality evidence.",
            ["DataSteward"],
        ),
        (
            "actor.market_surveillance_user",
            "Market Surveillance User",
            "市场监察用户",
            "Reviews potential self-trade candidates and their synthetic evidence.",
            ["MarketSurveillanceDemo"],
        ),
        (
            "actor.trading_user",
            "Trading User",
            "交易用户",
            "Reviews synthetic trading operations and latency analytics.",
            ["TradingDemo"],
        ),
        (
            "actor.markets_user",
            "Markets User",
            "市场业务用户",
            "Consumes aggregate market trends with participant identifiers redacted.",
            ["MarketsDemo"],
        ),
        (
            "actor.ontology_agent",
            "Ontology Analytic Agent",
            "本体分析智能体",
            "Deterministic and LLM-assisted service constrained by the active scenario package.",
            ["SystemExecutor"],
        ),
        (
            "actor.external_user",
            "External User",
            "外部用户",
            "A principal denied access to scenario data and evidence.",
            ["ExternalUser"],
        ),
    ]
    actor_objects = []
    for identifier, en, zh, definition, roles in actors:
        actor = _governed(
            identifier,
            en,
            zh,
            definition,
            sources=["source.requirements"],
        )
        actor["roles"] = roles
        actor_objects.append(actor)

    entities = []
    for identifier, en, zh, definition, primary_key, grain, lifecycle, sources in [
        ("entity.trade_activity", "Trade Activity", "成交活动", "A normalized cash trade or execution activity.", "property.trade.trading_activity_id", "one trade activity event", "append-only event with correction references", ["source.data_dictionary"]),
        ("entity.order_activity", "Order Activity", "订单活动", "An observed order-lifecycle event in the supplied reporting window.", "property.order.activity_id", "one observed order activity event", "event sequence may be incomplete in the sample", ["source.data_dictionary", "source.sample_data"]),
        ("entity.order_lifecycle", "Observed Order Lifecycle", "已观测订单生命周期", "A deterministic grouping of supplied order events by venue, trading date and order ID; completeness outside the extract is not inferred.", "property.order_lifecycle.lifecycle_key", "one observed order lifecycle", "derived from the latest valid observed event plus lifecycle flags", ["source.data_dictionary", "source.sample_data", "source.assumption_register"]),
        ("entity.participant", "Participant", "参与者", "A participant, member, client or account-level party in the synthetic reference.", "property.participant.participant_id", "one participant reference row", "effective-dated reference", ["source.data_dictionary"]),
        ("entity.instrument", "Instrument", "证券", "A cash-market instrument in the synthetic reference.", "property.instrument.instrument_id", "one instrument reference row", "effective-dated reference", ["source.data_dictionary"]),
        ("entity.trading_day", "Trading Day", "交易日", "A venue calendar date and trading-day designation.", "property.calendar.calendar_key", "one calendar and business-date row", "versioned calendar record", ["source.data_dictionary"]),
        ("entity.market_segment", "Market Segment", "市场板块", "A normalized market-segment member used for analysis.", "property.market_segment.code", "one segment code", "controlled classification", ["source.data_dictionary"]),
    ]:
        entity = _governed(identifier, en, zh, definition, sources=sources)
        entity.update({"primary_key": primary_key, "grain": grain, "lifecycle": lifecycle})
        entities.append(entity)

    properties = [
        _property("property.trade.trading_activity_id", "Trading Activity ID", "成交活动ID", "Stable normalized trade-activity identifier.", entity="entity.trade_activity", data_type="string", required=True),
        _property("property.trade.business_date", "Business Date", "业务日期", "Venue-calendar business date for the trade.", entity="entity.trade_activity", data_type="date", required=True, decisions=["decision.time_convention"]),
        _property("property.trade.venue_code", "Venue Code", "交易场所代码", "Normalized venue identifier.", entity="entity.trade_activity", data_type="string", required=True),
        _property("property.trade.market_segment", "Market Segment", "市场板块", "Normalized market segment.", entity="entity.trade_activity", data_type="string", required=False),
        _property("property.trade.instrument_id", "Instrument ID", "证券ID", "Instrument join key.", entity="entity.trade_activity", data_type="string", required=True),
        _property("property.trade.participant_id", "Participant ID", "参与者ID", "Associated participant identifier where available.", entity="entity.trade_activity", data_type="string", required=False),
        _property("property.trade.buy_participant_id", "Buy Participant ID", "买方参与者ID", "Normalized buying participant identifier.", entity="entity.trade_activity", data_type="string", required=False),
        _property("property.trade.sell_participant_id", "Sell Participant ID", "卖方参与者ID", "Normalized selling participant identifier.", entity="entity.trade_activity", data_type="string", required=False),
        _property("property.trade.trade_quantity", "Trade Quantity", "成交数量", "Executed trade quantity.", entity="entity.trade_activity", data_type="decimal", required=True, unit="SHARE"),
        _property("property.trade.trade_notional_hkd", "Native Trade Notional", "原币成交名义金额", "Native trade notional reported in HKD for the supplied sample.", entity="entity.trade_activity", data_type="decimal", required=True, unit="HKD", decisions=["decision.notional_currency"]),
        _property("property.trade.base_notional_usd", "Converted Base Notional", "转换后基础名义金额", "Base notional before haircut reported in USD for the supplied sample.", entity="entity.trade_activity", data_type="decimal", required=True, unit="USD", decisions=["decision.notional_currency"]),
        _property("property.trade.transaction_timestamp", "Transaction Timestamp", "交易时间戳", "Matching-engine timestamp normalized to UTC.", entity="entity.trade_activity", data_type="datetime", required=True, decisions=["decision.time_convention"]),
        _property("property.trade.receive_timestamp", "Receive Timestamp", "接收时间戳", "Platform receive timestamp normalized to UTC.", entity="entity.trade_activity", data_type="datetime", required=True, decisions=["decision.time_convention"]),
        _property("property.trade.is_eligible_trade", "Eligible Trade Flag", "合格成交标志", "Adapter-derived flag for the provisional active-trade population.", entity="entity.trade_activity", data_type="boolean", required=True, sources=["source.assumption_register", "source.compiler_sql"], decisions=["decision.trade_eligibility"]),
        _property("property.trade.is_active_client", "Active Client Trade Flag", "活跃客户成交标志", "True when the associated participant resolves to an effective CLIENT reference record for the trade timestamp.", entity="entity.trade_activity", data_type="boolean", required=True, sources=["source.data_dictionary", "source.assumption_register", "source.compiler_sql"], decisions=["decision.client_classification"]),
        _property("property.trade.has_both_participant_ids", "Both Participants Available", "双方参与者可用", "True when both normalized side participant identifiers are present.", entity="entity.trade_activity", data_type="boolean", required=True, sources=["source.assumption_register", "source.compiler_sql"], decisions=["decision.self_trade_candidate"]),
        _property("property.trade.is_potential_self_trade", "Potential Self-Trade Flag", "潜在自成交标志", "Deterministic triage flag; not a misconduct conclusion.", entity="entity.trade_activity", data_type="boolean", required=True, sources=["source.metric_logic", "source.assumption_register", "source.compiler_sql"], decisions=["decision.self_trade_candidate"]),
        _property("property.trade.is_nonnegative_latency", "Valid Latency Flag", "有效延迟标志", "True when capture latency is non-negative.", entity="entity.trade_activity", data_type="boolean", required=True, sources=["source.metric_logic", "source.assumption_register"], decisions=["decision.latency_convention"]),
        _property("property.trade.capture_latency_ms", "Capture Latency", "捕获延迟", "Receive timestamp minus transaction timestamp in milliseconds.", entity="entity.trade_activity", data_type="integer", required=False, unit="MILLISECOND", sources=["source.metric_logic", "source.assumption_register"], decisions=["decision.latency_convention"]),
        _property("property.order.activity_id", "Order Activity ID", "订单活动ID", "Stable order-event identifier.", entity="entity.order_activity", data_type="string", required=True),
        _property("property.order.order_id", "Order ID", "订单ID", "Order identifier within venue and trading date.", entity="entity.order_activity", data_type="string", required=True, decisions=["decision.order_lifecycle"]),
        _property("property.order.trading_date", "Order Trading Date", "订单交易日", "Trading date of the observed order event.", entity="entity.order_activity", data_type="date", required=True, decisions=["decision.time_convention"]),
        _property("property.order.order_status", "Order Status", "订单状态", "Canonical post-event status using CANCELED spelling.", entity="entity.order_activity", data_type="enum", required=True, enum_values=["NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "REPLACED", "REJECTED", "EXPIRED", "SUSPENDED", "PENDING", "UNKNOWN"], decisions=["decision.cancel_spelling"]),
        _property("property.order.transaction_timestamp", "Order Transaction Timestamp", "订单交易时间戳", "Observed order-event transaction timestamp.", entity="entity.order_activity", data_type="datetime", required=True, decisions=["decision.time_convention"]),
        _property("property.order_lifecycle.lifecycle_key", "Order Lifecycle Key", "订单生命周期键", "Venue code, trading date and order ID composed into one stable observed-lifecycle key.", entity="entity.order_lifecycle", data_type="string", required=True, sources=["source.assumption_register", "source.compiler_sql"], decisions=["decision.order_lifecycle"]),
        _property("property.order_lifecycle.trading_date", "Lifecycle Trading Date", "生命周期交易日", "Business date assigned to the observed order lifecycle.", entity="entity.order_lifecycle", data_type="date", required=True, decisions=["decision.time_convention"]),
        _property("property.order_lifecycle.venue_code", "Lifecycle Venue", "生命周期交易场所", "Normalized venue of the observed order lifecycle.", entity="entity.order_lifecycle", data_type="string", required=True),
        _property("property.order_lifecycle.market_segment", "Lifecycle Market Segment", "生命周期市场板块", "Market segment from the latest valid observed order state.", entity="entity.order_lifecycle", data_type="string", required=False),
        _property("property.order_lifecycle.instrument_id", "Lifecycle Instrument", "生命周期证券", "Instrument from the latest valid observed order state.", entity="entity.order_lifecycle", data_type="string", required=True),
        _property("property.order_lifecycle.participant_id", "Lifecycle Participant", "生命周期参与者", "Participant from the latest valid observed order state.", entity="entity.order_lifecycle", data_type="string", required=False),
        _property("property.order_lifecycle.is_client", "Client Lifecycle Flag", "客户订单标志", "True when the effective participant reference is classified CLIENT.", entity="entity.order_lifecycle", data_type="boolean", required=True, sources=["source.data_dictionary", "source.assumption_register", "source.compiler_sql"], decisions=["decision.client_classification"]),
        _property("property.order_lifecycle.is_submitted", "Submitted Lifecycle Flag", "已提交订单标志", "True when an observed lifecycle contains a NEW or REJECT submission attempt.", entity="entity.order_lifecycle", data_type="boolean", required=True, sources=["source.metric_logic", "source.assumption_register", "source.compiler_sql"], decisions=["decision.submitted_order"]),
        _property("property.order_lifecycle.is_rejected", "Rejected Lifecycle Flag", "已拒绝订单标志", "True when any observed event in the lifecycle is REJECT or has REJECTED status.", entity="entity.order_lifecycle", data_type="boolean", required=True, sources=["source.metric_logic", "source.assumption_register", "source.compiler_sql"], decisions=["decision.rejected_order"]),
        _property("property.order_lifecycle.is_eligible_client_order", "Eligible Client Order Flag", "合格客户订单标志", "True for a submitted client lifecycle with no observed rejection.", entity="entity.order_lifecycle", data_type="boolean", required=True, sources=["source.metric_logic", "source.assumption_register", "source.compiler_sql"], decisions=["decision.client_completion"]),
        _property("property.order_lifecycle.is_fully_filled", "Fully Filled Lifecycle Flag", "完全成交订单标志", "True when the latest valid observed order state is FILLED.", entity="entity.order_lifecycle", data_type="boolean", required=True, sources=["source.metric_logic", "source.compiler_sql"], decisions=["decision.order_lifecycle"]),
        _property("property.order_lifecycle.is_canceled", "Canceled Lifecycle Flag", "已撤销订单标志", "True when the lifecycle contains an eligible CANCEL event after CANCELLED-to-CANCELED normalization.", entity="entity.order_lifecycle", data_type="boolean", required=True, sources=["source.metric_logic", "source.assumption_register", "source.compiler_sql"], decisions=["decision.cancel_spelling", "decision.cancel_ratio"]),
        _property("property.order_lifecycle.final_order_quantity", "Final Order Quantity", "最终订单数量", "Order quantity at the latest valid observed lifecycle state.", entity="entity.order_lifecycle", data_type="integer", required=True, unit="SHARE", sources=["source.metric_logic", "source.compiler_sql"], decisions=["decision.order_lifecycle"]),
        _property("property.order_lifecycle.final_cumulative_executed_quantity", "Final Cumulative Executed Quantity", "最终累计成交数量", "Cumulative executed quantity at the latest valid observed lifecycle state.", entity="entity.order_lifecycle", data_type="integer", required=True, unit="SHARE", sources=["source.metric_logic", "source.compiler_sql"], decisions=["decision.order_lifecycle"]),
        _property("property.participant.participant_id", "Participant ID", "参与者ID", "Stable synthetic participant identifier.", entity="entity.participant", data_type="string", required=True),
        _property("property.participant.participant_name", "Participant Name", "参与者名称", "Synthetic participant display name.", entity="entity.participant", data_type="string", required=True),
        _property("property.participant.participant_type", "Participant Type", "参与者类型", "Controlled participant classification.", entity="entity.participant", data_type="enum", required=True, enum_values=["BROKER", "DEALER", "BANK", "MARKET_MAKER", "CLIENT", "FUND", "INTERNAL_DESK", "CLEARING_MEMBER", "OTHER"]),
        _property("property.instrument.instrument_id", "Instrument ID", "证券ID", "Stable synthetic instrument identifier.", entity="entity.instrument", data_type="string", required=True),
        _property("property.instrument.instrument_name", "Instrument Name", "证券名称", "Synthetic instrument display name.", entity="entity.instrument", data_type="string", required=True),
        _property("property.instrument.primary_symbol", "Primary Symbol", "主要代码", "Primary venue symbol.", entity="entity.instrument", data_type="string", required=True),
        _property("property.calendar.calendar_key", "Calendar Key", "日历键", "Logical calendar_code + business_date key.", entity="entity.trading_day", data_type="string", required=True, decisions=["decision.calendar_key"]),
        _property("property.calendar.business_date", "Calendar Business Date", "日历业务日期", "Business date represented by the calendar row.", entity="entity.trading_day", data_type="date", required=True),
        _property("property.calendar.is_trading_day", "Is Trading Day", "是否交易日", "Trading-day indicator.", entity="entity.trading_day", data_type="enum", required=True, enum_values=["Y", "N"]),
        _property("property.market_segment.code", "Market Segment Code", "市场板块代码", "Normalized market-segment code.", entity="entity.market_segment", data_type="string", required=True),
        _property("property.market_segment.name", "Market Segment Name", "市场板块名称", "Display label for the market segment.", entity="entity.market_segment", data_type="string", required=True),
    ]

    relationships = []
    for identifier, en, zh, definition, from_entity, to_entity, predicate, cardinality in [
        ("relationship.trade_instrument", "Trade has instrument", "成交对应证券", "A trade activity references one instrument.", "entity.trade_activity", "entity.instrument", "hasInstrument", "N:1"),
        ("relationship.trade_participant", "Trade has participant", "成交对应参与者", "A trade activity may reference an associated participant.", "entity.trade_activity", "entity.participant", "hasParticipant", "N:1"),
        ("relationship.order_participant", "Order has participant", "订单对应参与者", "An order activity may reference a participant.", "entity.order_activity", "entity.participant", "hasParticipant", "N:1"),
        ("relationship.order_lifecycle_participant", "Order lifecycle has participant", "订单生命周期对应参与者", "An observed order lifecycle may resolve to one effective participant.", "entity.order_lifecycle", "entity.participant", "hasParticipant", "N:1"),
        ("relationship.order_lifecycle_instrument", "Order lifecycle has instrument", "订单生命周期对应证券", "An observed order lifecycle references one instrument.", "entity.order_lifecycle", "entity.instrument", "hasInstrument", "N:1"),
        ("relationship.order_lifecycle_day", "Order lifecycle occurs on day", "订单生命周期发生于交易日", "An observed order lifecycle is assigned to one trading date.", "entity.order_lifecycle", "entity.trading_day", "occursOn", "N:1"),
        ("relationship.trade_day", "Trade occurs on day", "成交发生于交易日", "A trade activity is assigned to one business date.", "entity.trade_activity", "entity.trading_day", "occursOn", "N:1"),
    ]:
        item = _governed(identifier, en, zh, definition, sources=["source.data_dictionary"])
        item.update({"from_entity": from_entity, "to_entity": to_entity, "predicate": predicate, "cardinality": cardinality})
        relationships.append(item)

    dimensions = []
    for identifier, en, zh, definition, entity, key, label, hierarchy in [
        ("dimension.business_date", "Business Date", "业务日期", "Daily reporting dimension.", "entity.trading_day", "property.calendar.business_date", "property.calendar.business_date", []),
        ("dimension.instrument", "Instrument", "证券", "Instrument reporting dimension.", "entity.instrument", "property.instrument.instrument_id", "property.instrument.instrument_name", []),
        ("dimension.participant", "Participant", "参与者", "Synthetic participant reporting dimension subject to role projection.", "entity.participant", "property.participant.participant_id", "property.participant.participant_name", ["property.participant.participant_type"]),
        ("dimension.market_segment", "Market Segment", "市场板块", "Market-segment reporting dimension.", "entity.market_segment", "property.market_segment.code", "property.market_segment.name", []),
    ]:
        item = _governed(identifier, en, zh, definition, sources=["source.requirements", "source.data_dictionary"])
        item.update({"entity": entity, "key_property": key, "label_property": label, "hierarchy": hierarchy, "member_resolution": "exact"})
        dimensions.append(item)

    rules = []
    for identifier, en, zh, definition, conditions, decisions in [
        ("rule.eligible_trade", "Eligible Trade", "合格成交", "Include only active TRADE rows that are not corrected originals.", [{"property": "property.trade.is_eligible_trade", "op": "is_true"}], ["decision.trade_eligibility"]),
        ("rule.active_client_trade", "Active Client Trade", "活跃客户成交", "An eligible trade whose associated participant resolves to an effective CLIENT reference row.", [{"property": "property.trade.is_eligible_trade", "op": "is_true"}, {"property": "property.trade.is_active_client", "op": "is_true"}], ["decision.trade_eligibility", "decision.client_classification"]),
        ("rule.self_trade_eligible", "Self-Trade Eligible Population", "自成交合格总体", "An eligible trade with both normalized side participant identifiers available.", [{"property": "property.trade.has_both_participant_ids", "op": "is_true"}], ["decision.self_trade_denominator"]),
        ("rule.potential_self_trade", "Potential Self-Trade Candidate", "潜在自成交候选", "Both normalized side participant IDs are present and equal.", [{"property": "property.trade.is_potential_self_trade", "op": "is_true"}], ["decision.self_trade_candidate"]),
        ("rule.nonnegative_latency", "Non-Negative Capture Latency", "非负捕获延迟", "Exclude negative latency observations from KPI values and count them as exceptions.", [{"property": "property.trade.is_nonnegative_latency", "op": "is_true"}], ["decision.latency_convention"]),
        ("rule.submitted_order", "Submitted Order Lifecycle", "已提交订单生命周期", "An observed lifecycle containing a NEW or REJECT submission attempt.", [{"property": "property.order_lifecycle.is_submitted", "op": "is_true"}], ["decision.submitted_order"]),
        ("rule.rejected_order", "Rejected Order Lifecycle", "已拒绝订单生命周期", "A submitted lifecycle containing a REJECT event or REJECTED state.", [{"property": "property.order_lifecycle.is_rejected", "op": "is_true"}], ["decision.rejected_order"]),
        ("rule.eligible_client_order", "Eligible Client Order", "合格客户订单", "A submitted client lifecycle with no observed rejection.", [{"property": "property.order_lifecycle.is_eligible_client_order", "op": "is_true"}], ["decision.client_classification", "decision.client_completion"]),
        ("rule.fully_filled_client_order", "Fully Filled Client Order", "完全成交客户订单", "An eligible client order whose latest valid observed state is FILLED.", [{"property": "property.order_lifecycle.is_eligible_client_order", "op": "is_true"}, {"property": "property.order_lifecycle.is_fully_filled", "op": "is_true"}], ["decision.client_completion"]),
        ("rule.canceled_order", "Canceled Order Lifecycle", "已撤销订单生命周期", "An observed lifecycle containing an eligible CANCEL event after spelling normalization.", [{"property": "property.order_lifecycle.is_canceled", "op": "is_true"}], ["decision.cancel_ratio"]),
    ]:
        item = _governed(identifier, en, zh, definition, sources=["source.assumption_register", "source.metric_logic"], decisions=decisions)
        item.update({"rule_type": "eligibility", "all": conditions, "failure_behavior": "exclude"})
        rules.append(item)

    all_dimensions = [
        "dimension.business_date",
        "dimension.instrument",
        "dimension.participant",
        "dimension.market_segment",
    ]

    def base_metric(
        identifier: str,
        en: str,
        zh: str,
        definition: str,
        *,
        entity: str,
        source: str,
        measure: str,
        period: str,
        population: str,
        filters: list[str],
        unit: str,
        value_type: str,
        formula_op: str,
        decisions: list[str],
        dimensions: list[str] | None = None,
        tags: list[str] | None = None,
        null_policy: str = "fail_validation",
        aggregation: str = "additive",
    ) -> dict[str, Any]:
        return {
            **_governed(
                identifier,
                en,
                zh,
                definition,
                sources=["source.metric_logic", "source.assumption_register", "source.compiler_sql"],
                decisions=decisions,
                tags=tags or ["constructed_synthetic", "cash_trading", "supporting_metric"],
            ),
            "metric_type": "base",
            "base_entity": entity,
            "result_grain": ["dimension.business_date"],
            "value_type": value_type,
            "unit": unit,
            "aggregation_semantics": aggregation,
            "formula": {"op": formula_op, "args": [{"op": "field_ref", "ref": measure}]} if formula_op in {"sum", "count_distinct"} else {"op": "field_ref", "ref": measure},
            "query": {
                "base_source": source,
                "measure_property": measure,
                "period_property": period,
                "date_property": period,
                "population_property": population,
                "required_joins": [],
                "filters": filters,
            },
            "allowed_dimensions": dimensions or all_dimensions,
            "null_policy": null_policy,
            "zero_denominator_policy": "refuse",
        }

    def derived_metric(
        identifier: str,
        en: str,
        zh: str,
        definition: str,
        *,
        entity: str,
        unit: str,
        value_type: str,
        formula: dict[str, Any],
        decisions: list[str],
        dimensions: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            **_governed(
                identifier,
                en,
                zh,
                definition,
                sources=["source.metric_logic", "source.assumption_register", "source.compiler_sql"],
                decisions=decisions,
                tags=tags or ["constructed_synthetic", "cash_trading", "supporting_metric"],
            ),
            "metric_type": "derived",
            "base_entity": entity,
            "result_grain": ["dimension.business_date"],
            "value_type": value_type,
            "unit": unit,
            "aggregation_semantics": "derived_non_additive",
            "formula": formula,
            "query": {},
            "allowed_dimensions": dimensions or all_dimensions,
            "null_policy": "fail_validation",
            "zero_denominator_policy": "refuse",
        }

    metrics = [
        base_metric("metric.submitted_order_count", "Submitted Order Count", "已提交订单数", "Distinct observed order lifecycles containing a NEW or REJECT submission attempt.", entity="entity.order_lifecycle", source="source.cash_order_lifecycle_analytics", measure="property.order_lifecycle.lifecycle_key", period="property.order_lifecycle.trading_date", population="property.order_lifecycle.is_submitted", filters=["rule.submitted_order"], unit="ORDER", value_type="integer", formula_op="count_distinct", decisions=["decision.order_lifecycle", "decision.submitted_order"]),
        base_metric("metric.rejected_order_count", "Rejected Order Count", "已拒绝订单数", "Distinct submitted order lifecycles containing an observed rejection.", entity="entity.order_lifecycle", source="source.cash_order_lifecycle_analytics", measure="property.order_lifecycle.lifecycle_key", period="property.order_lifecycle.trading_date", population="property.order_lifecycle.is_rejected", filters=["rule.submitted_order", "rule.rejected_order"], unit="ORDER", value_type="integer", formula_op="count_distinct", decisions=["decision.submitted_order", "decision.rejected_order"]),
        derived_metric("metric.order_rejection_rate", "Order Rejection Rate", "订单拒绝率", "Rejected distinct submitted order lifecycles divided by submitted distinct order lifecycles for the same cohort.", entity="entity.order_lifecycle", unit="PERCENT", value_type="percentage", formula={"op": "divide", "args": [{"op": "metric_ref", "ref": "metric.rejected_order_count"}, {"op": "metric_ref", "ref": "metric.submitted_order_count"}]}, decisions=["decision.submitted_order", "decision.rejected_order"], tags=["constructed_synthetic", "cash_trading", "source_metric:M-01", "ontology_reviewed"]),
        base_metric("metric.submitted_order_quantity", "Submitted Order Quantity", "已提交订单数量", "Sum of final order quantity across distinct submitted observed lifecycles.", entity="entity.order_lifecycle", source="source.cash_order_lifecycle_analytics", measure="property.order_lifecycle.final_order_quantity", period="property.order_lifecycle.trading_date", population="property.order_lifecycle.is_submitted", filters=["rule.submitted_order"], unit="SHARE", value_type="decimal", formula_op="sum", decisions=["decision.order_lifecycle", "decision.submitted_order"]),
        base_metric("metric.executed_order_quantity", "Executed Order Quantity", "订单累计成交数量", "Sum of final cumulative executed quantity across the same submitted lifecycle population.", entity="entity.order_lifecycle", source="source.cash_order_lifecycle_analytics", measure="property.order_lifecycle.final_cumulative_executed_quantity", period="property.order_lifecycle.trading_date", population="property.order_lifecycle.is_submitted", filters=["rule.submitted_order"], unit="SHARE", value_type="decimal", formula_op="sum", decisions=["decision.order_lifecycle", "decision.submitted_order"]),
        derived_metric("metric.order_fill_rate", "Order Fill Rate", "订单成交率", "Final cumulative executed quantity divided by final submitted order quantity across the same lifecycle cohort.", entity="entity.order_lifecycle", unit="PERCENT", value_type="percentage", formula={"op": "divide", "args": [{"op": "metric_ref", "ref": "metric.executed_order_quantity"}, {"op": "metric_ref", "ref": "metric.submitted_order_quantity"}]}, decisions=["decision.order_lifecycle", "decision.submitted_order"], tags=["constructed_synthetic", "cash_trading", "source_metric:M-02", "ontology_reviewed"]),
        base_metric("metric.eligible_trade_count", "Eligible Trade Count", "合格成交笔数", "Distinct active TRADE rows after correction-lineage exclusions.", entity="entity.trade_activity", source="source.cash_trade_analytics", measure="property.trade.trading_activity_id", period="property.trade.business_date", population="property.trade.is_eligible_trade", filters=["rule.eligible_trade"], unit="TRADE", value_type="integer", formula_op="count_distinct", decisions=["decision.trade_eligibility"]),
        base_metric("metric.trade_capture_latency_ms", "Trade Capture Latency", "成交捕获延迟", "Per-trade receive minus transaction latency; the current runtime reports count, min, nearest-rank p50/p95/p99, max and negative exceptions.", entity="entity.trade_activity", source="source.cash_trade_analytics", measure="property.trade.capture_latency_ms", period="property.trade.business_date", population="property.trade.is_nonnegative_latency", filters=["rule.eligible_trade", "rule.nonnegative_latency"], unit="MILLISECOND", value_type="integer", formula_op="field_ref", decisions=["decision.latency_convention"], dimensions=["dimension.business_date", "dimension.instrument", "dimension.market_segment"], tags=["constructed_synthetic", "cash_trading", "source_metric:M-03", "ontology_reviewed", "agent_runtime_supported"], null_policy="exclude", aggregation="non_additive"),
        base_metric("metric.active_client_trade_quantity", "Active Client Trade Quantity", "活跃客户成交数量", "Gross executed quantity for eligible trades whose associated participant resolves to an effective CLIENT record.", entity="entity.trade_activity", source="source.cash_trade_analytics", measure="property.trade.trade_quantity", period="property.trade.business_date", population="property.trade.is_active_client", filters=["rule.active_client_trade"], unit="SHARE", value_type="decimal", formula_op="sum", decisions=["decision.trade_eligibility", "decision.client_classification"]),
        base_metric("metric.active_client_trade_notional_hkd", "Active Client Trade Notional", "活跃客户成交金额", "Gross native notional in HKD before haircut for eligible active-client trades.", entity="entity.trade_activity", source="source.cash_trade_analytics", measure="property.trade.trade_notional_hkd", period="property.trade.business_date", population="property.trade.is_active_client", filters=["rule.active_client_trade"], unit="HKD", value_type="decimal", formula_op="sum", decisions=["decision.trade_eligibility", "decision.client_classification", "decision.notional_currency"]),
        derived_metric("metric.active_client_trading_volume", "Active Client Trading Volume", "活跃客户成交量", "Gross active-client trade notional in HKD millions; active-client quantity remains available as a companion measure.", entity="entity.trade_activity", unit="HKD_MN", value_type="decimal", formula={"op": "divide", "args": [{"op": "metric_ref", "ref": "metric.active_client_trade_notional_hkd"}, {"op": "literal", "value": 1000000}]}, decisions=["decision.trade_eligibility", "decision.client_classification", "decision.notional_currency"], tags=["constructed_synthetic", "cash_trading", "source_metric:M-04", "ontology_reviewed"]),
        base_metric("metric.eligible_client_order_count", "Eligible Client Order Count", "合格客户订单数", "Distinct submitted client lifecycles with no observed rejection.", entity="entity.order_lifecycle", source="source.cash_order_lifecycle_analytics", measure="property.order_lifecycle.lifecycle_key", period="property.order_lifecycle.trading_date", population="property.order_lifecycle.is_eligible_client_order", filters=["rule.eligible_client_order"], unit="ORDER", value_type="integer", formula_op="count_distinct", decisions=["decision.client_classification", "decision.client_completion"]),
        base_metric("metric.fully_filled_client_order_count", "Fully Filled Client Order Count", "完全成交客户订单数", "Distinct eligible client order lifecycles whose latest valid observed state is FILLED.", entity="entity.order_lifecycle", source="source.cash_order_lifecycle_analytics", measure="property.order_lifecycle.lifecycle_key", period="property.order_lifecycle.trading_date", population="property.order_lifecycle.is_fully_filled", filters=["rule.fully_filled_client_order"], unit="ORDER", value_type="integer", formula_op="count_distinct", decisions=["decision.client_classification", "decision.client_completion"]),
        derived_metric("metric.client_order_completion_rate", "Client Order Completion Rate", "客户订单完成率", "Fully filled eligible client order lifecycles divided by eligible submitted client order lifecycles.", entity="entity.order_lifecycle", unit="PERCENT", value_type="percentage", formula={"op": "divide", "args": [{"op": "metric_ref", "ref": "metric.fully_filled_client_order_count"}, {"op": "metric_ref", "ref": "metric.eligible_client_order_count"}]}, decisions=["decision.client_classification", "decision.client_completion"], tags=["constructed_synthetic", "cash_trading", "source_metric:M-05", "ontology_reviewed"]),
        base_metric("metric.canceled_order_count", "Canceled Order Count", "已撤销订单数", "Distinct observed order lifecycles containing an eligible cancel event.", entity="entity.order_lifecycle", source="source.cash_order_lifecycle_analytics", measure="property.order_lifecycle.lifecycle_key", period="property.order_lifecycle.trading_date", population="property.order_lifecycle.is_canceled", filters=["rule.canceled_order"], unit="ORDER", value_type="integer", formula_op="count_distinct", decisions=["decision.cancel_spelling", "decision.cancel_ratio"]),
        derived_metric("metric.cancel_to_trade_ratio", "Cancel-to-Trade Ratio", "撤单成交比", "Distinct canceled order lifecycles divided by distinct eligible active trades for the same cohort.", entity="entity.order_lifecycle", unit="PERCENT", value_type="percentage", formula={"op": "divide", "args": [{"op": "metric_ref", "ref": "metric.canceled_order_count"}, {"op": "metric_ref", "ref": "metric.eligible_trade_count"}]}, decisions=["decision.cancel_ratio", "decision.trade_eligibility"], tags=["constructed_synthetic", "cash_trading", "source_metric:M-06", "ontology_reviewed"]),
        derived_metric("metric.order_to_trade_denominator", "Order-to-Trade Denominator", "订单成交比折算分母", "Two trade sides per distinct eligible matched trade under the provisional two-sided matching convention.", entity="entity.trade_activity", unit="TRADE_SIDE", value_type="decimal", formula={"op": "multiply", "args": [{"op": "metric_ref", "ref": "metric.eligible_trade_count"}, {"op": "literal", "value": 2}]}, decisions=["decision.trade_eligibility", "decision.order_to_trade"]),
        derived_metric("metric.order_to_trade_ratio", "Order-to-Trade Ratio", "订单成交比", "Distinct submitted order lifecycles divided by two times distinct eligible active trades.", entity="entity.order_lifecycle", unit="PERCENT", value_type="percentage", formula={"op": "divide", "args": [{"op": "metric_ref", "ref": "metric.submitted_order_count"}, {"op": "metric_ref", "ref": "metric.order_to_trade_denominator"}]}, decisions=["decision.submitted_order", "decision.trade_eligibility", "decision.order_to_trade"], tags=["constructed_synthetic", "cash_trading", "source_metric:M-07", "ontology_reviewed"]),
        base_metric("metric.self_trade_eligible_trade_count", "Self-Trade Eligible Trade Count", "自成交合格成交笔数", "Distinct eligible active trades with both-side participant identifiers available.", entity="entity.trade_activity", source="source.cash_trade_analytics", measure="property.trade.trading_activity_id", period="property.trade.business_date", population="property.trade.has_both_participant_ids", filters=["rule.eligible_trade", "rule.self_trade_eligible"], unit="TRADE", value_type="integer", formula_op="count_distinct", decisions=["decision.trade_eligibility", "decision.self_trade_denominator"]),
        base_metric("metric.potential_self_trade_count", "Potential Self-Trade Candidate Count", "潜在自成交候选笔数", "Distinct eligible trades whose normalized buy and sell participant IDs are both present and equal.", entity="entity.trade_activity", source="source.cash_trade_analytics", measure="property.trade.trading_activity_id", period="property.trade.business_date", population="property.trade.is_potential_self_trade", filters=["rule.eligible_trade", "rule.self_trade_eligible", "rule.potential_self_trade"], unit="TRADE", value_type="integer", formula_op="count_distinct", decisions=["decision.self_trade_candidate"]),
        derived_metric("metric.potential_self_trade_rate", "Potential Self-Trade Rate", "潜在自成交率", "Potential self-trade candidate count divided by eligible active trades with both-side participant IDs; this is a triage measure, not a misconduct conclusion.", entity="entity.trade_activity", unit="PERCENT", value_type="percentage", formula={"op": "divide", "args": [{"op": "metric_ref", "ref": "metric.potential_self_trade_count"}, {"op": "metric_ref", "ref": "metric.self_trade_eligible_trade_count"}]}, decisions=["decision.self_trade_candidate", "decision.self_trade_denominator"], tags=["constructed_synthetic", "cash_trading", "source_metric:M-08", "ontology_reviewed", "agent_runtime_supported"]),
    ]

    bindings = [
        _binding("binding.trade.id", "property.trade.trading_activity_id", "trading_activity_id", "string"),
        _binding("binding.trade.business_date", "property.trade.business_date", "business_date", "date"),
        _binding("binding.trade.venue", "property.trade.venue_code", "venue_code", "string"),
        _binding("binding.trade.market_segment", "property.trade.market_segment", "market_segment", "string"),
        _binding("binding.trade.instrument", "property.trade.instrument_id", "instrument_id", "string"),
        _binding("binding.trade.participant", "property.trade.participant_id", "participant_id", "string"),
        _binding("binding.trade.buy_participant", "property.trade.buy_participant_id", "buy_participant_id", "string"),
        _binding("binding.trade.sell_participant", "property.trade.sell_participant_id", "sell_participant_id", "string"),
        _binding("binding.trade.quantity", "property.trade.trade_quantity", "trade_quantity", "decimal", unit="SHARE"),
        _binding("binding.trade.notional_hkd", "property.trade.trade_notional_hkd", "trade_notional_hkd", "decimal", unit="HKD"),
        _binding("binding.trade.base_notional_usd", "property.trade.base_notional_usd", "base_notional_usd", "decimal", unit="USD"),
        _binding("binding.trade.transaction_timestamp", "property.trade.transaction_timestamp", "transaction_timestamp", "datetime"),
        _binding("binding.trade.receive_timestamp", "property.trade.receive_timestamp", "receive_timestamp", "datetime"),
        _binding("binding.trade.eligible", "property.trade.is_eligible_trade", "is_eligible_trade", "boolean", transformation="activity_type=TRADE AND trade_status=ACTIVE AND not corrected original"),
        _binding("binding.trade.active_client", "property.trade.is_active_client", "is_active_client", "boolean", transformation="effective participant reference has participant_type=CLIENT"),
        _binding("binding.trade.has_both_participants", "property.trade.has_both_participant_ids", "has_both_participant_ids", "boolean", transformation="buy_participant_id and sell_participant_id are non-null"),
        _binding("binding.trade.self_trade", "property.trade.is_potential_self_trade", "is_potential_self_trade", "boolean", transformation="normalized buy_participant_id equals normalized sell_participant_id"),
        _binding("binding.trade.nonnegative_latency", "property.trade.is_nonnegative_latency", "is_nonnegative_latency", "boolean", transformation="capture_latency_ms >= 0"),
        _binding("binding.trade.capture_latency", "property.trade.capture_latency_ms", "capture_latency_ms", "integer", unit="MILLISECOND", transformation="receive_timestamp - transaction_timestamp in milliseconds"),
        _binding("binding.order_lifecycle.key", "property.order_lifecycle.lifecycle_key", "lifecycle_key", "string", source="source.cash_order_lifecycle_analytics", table="cash_order_lifecycle_analytics", transformation="venue_code + trading_date + order_id"),
        _binding("binding.order_lifecycle.trading_date", "property.order_lifecycle.trading_date", "trading_date", "date", source="source.cash_order_lifecycle_analytics", table="cash_order_lifecycle_analytics"),
        _binding("binding.order_lifecycle.venue", "property.order_lifecycle.venue_code", "venue_code", "string", source="source.cash_order_lifecycle_analytics", table="cash_order_lifecycle_analytics"),
        _binding("binding.order_lifecycle.market_segment", "property.order_lifecycle.market_segment", "market_segment", "string", source="source.cash_order_lifecycle_analytics", table="cash_order_lifecycle_analytics"),
        _binding("binding.order_lifecycle.instrument", "property.order_lifecycle.instrument_id", "instrument_id", "string", source="source.cash_order_lifecycle_analytics", table="cash_order_lifecycle_analytics"),
        _binding("binding.order_lifecycle.participant", "property.order_lifecycle.participant_id", "participant_id", "string", source="source.cash_order_lifecycle_analytics", table="cash_order_lifecycle_analytics"),
        _binding("binding.order_lifecycle.client", "property.order_lifecycle.is_client", "is_client", "boolean", source="source.cash_order_lifecycle_analytics", table="cash_order_lifecycle_analytics", transformation="effective participant_type=CLIENT"),
        _binding("binding.order_lifecycle.submitted", "property.order_lifecycle.is_submitted", "is_submitted", "boolean", source="source.cash_order_lifecycle_analytics", table="cash_order_lifecycle_analytics", transformation="any NEW or REJECT event"),
        _binding("binding.order_lifecycle.rejected", "property.order_lifecycle.is_rejected", "is_rejected", "boolean", source="source.cash_order_lifecycle_analytics", table="cash_order_lifecycle_analytics", transformation="any REJECT event or REJECTED state"),
        _binding("binding.order_lifecycle.eligible_client", "property.order_lifecycle.is_eligible_client_order", "is_eligible_client_order", "boolean", source="source.cash_order_lifecycle_analytics", table="cash_order_lifecycle_analytics", transformation="is_client AND is_submitted AND NOT is_rejected"),
        _binding("binding.order_lifecycle.fully_filled", "property.order_lifecycle.is_fully_filled", "is_fully_filled", "boolean", source="source.cash_order_lifecycle_analytics", table="cash_order_lifecycle_analytics", transformation="latest order_status=FILLED"),
        _binding("binding.order_lifecycle.canceled", "property.order_lifecycle.is_canceled", "is_canceled", "boolean", source="source.cash_order_lifecycle_analytics", table="cash_order_lifecycle_analytics", transformation="any CANCEL event after CANCELLED alias normalization"),
        _binding("binding.order_lifecycle.final_order_quantity", "property.order_lifecycle.final_order_quantity", "final_order_quantity", "integer", unit="SHARE", source="source.cash_order_lifecycle_analytics", table="cash_order_lifecycle_analytics", transformation="latest valid observed order_quantity"),
        _binding("binding.order_lifecycle.final_executed_quantity", "property.order_lifecycle.final_cumulative_executed_quantity", "final_cumulative_executed_quantity", "integer", unit="SHARE", source="source.cash_order_lifecycle_analytics", table="cash_order_lifecycle_analytics", transformation="latest valid observed cumulative_executed_quantity"),
    ]

    joins = []
    for identifier, en, zh, definition, left_source, left_table, right_source, right_table, keys in [
        ("join.trade_instrument", "Trade to Instrument", "成交关联证券", "Resolve each trade instrument.", "source.trading_activity", "trading_activity", "source.instrument_reference", "instrument_reference", [("instrument_id", "instrument_id")]),
        ("join.trade_buy_participant", "Trade to Buy Participant", "成交关联买方参与者", "Resolve the buying participant where available.", "source.trading_activity", "trading_activity", "source.account_reference", "account_reference", [("buy_participant_id", "participant_id")]),
        ("join.trade_sell_participant", "Trade to Sell Participant", "成交关联卖方参与者", "Resolve the selling participant where available.", "source.trading_activity", "trading_activity", "source.account_reference", "account_reference", [("sell_participant_id", "participant_id")]),
        ("join.trade_calendar", "Trade to Calendar", "成交关联日历", "Resolve a trade to its venue calendar date.", "source.trading_activity", "trading_activity", "source.trading_calendar", "trading_calendar", [("venue_code", "venue_code"), ("business_date", "business_date")]),
    ]:
        item = _governed(identifier, en, zh, definition, owner=DATA_STEWARD, sources=["source.data_dictionary"])
        item.update({"left_source": left_source, "left_table": left_table, "right_source": right_source, "right_table": right_table, "keys": [{"left_column": left, "right_column": right} for left, right in keys], "expected_cardinality": "N:1", "fanout_policy": "block"})
        joins.append(item)

    analyses = []
    for identifier, en, zh, definition, intent, operation, required_metrics, required_dimensions, output_fields, failure_conditions in [
        ("analysis.self_trade_summary", "Potential Self-Trade Summary", "潜在自成交汇总", "Return eligible count, candidate count, rate and top candidate dimensions.", "anomaly_triage", "cash.self_trade_summary", ["metric.self_trade_eligible_trade_count", "metric.potential_self_trade_count", "metric.potential_self_trade_rate"], [], ["eligible_trade_count", "candidate_trade_count", "candidate_rate_percent", "candidate_participants", "candidate_instruments", "limitations"], ["missing time range", "zero eligible population", "role denied"]),
        ("analysis.self_trade_trend", "Potential Self-Trade Trend", "潜在自成交趋势", "Return the candidate count and rate by business date.", "time_series", "cash.self_trade_daily_trend", ["metric.self_trade_eligible_trade_count", "metric.potential_self_trade_count", "metric.potential_self_trade_rate"], ["dimension.business_date"], ["business_date", "eligible_trade_count", "candidate_trade_count", "candidate_rate_percent"], ["missing time range", "role denied"]),
        ("analysis.self_trade_timeline", "Potential Self-Trade Evidence Timeline", "潜在自成交证据时间线", "Return the selected participant's candidate trades and linked observed order events in chronological order.", "timeline_evidence", "cash.self_trade_timeline", ["metric.potential_self_trade_count"], ["dimension.participant"], ["participant_id", "event_timestamp", "event_type", "trade_id", "order_id", "instrument_id", "observed_lifecycle_complete", "limitations"], ["participant missing", "participant not a candidate", "role denied"]),
        ("analysis.trade_latency_profile", "Trade Capture Latency Profile", "成交捕获延迟分布", "Return count, minimum, nearest-rank p50/p95/p99, maximum and negative-latency exceptions.", "latency_profile", "cash.trade_latency_profile", ["metric.trade_capture_latency_ms"], [], ["eligible_latency_count", "minimum_ms", "p50_ms", "p95_ms", "p99_ms", "maximum_ms", "negative_latency_count", "limitations"], ["missing time range", "empty eligible population", "role denied"]),
        ("analysis.cash_evidence_audit", "Cash Trading Evidence Audit", "现金交易证据审计", "Expose exact metric, decision, dataset, SQL and control references for an answer.", "evidence_audit", "cash.evidence_audit", ["metric.potential_self_trade_rate", "metric.trade_capture_latency_ms"], [], ["claim", "value", "metric_ids", "decision_ids", "dataset_checksum", "query_hash", "limitations"], ["unknown execution", "role denied"]),
    ]:
        item = _governed(identifier, en, zh, definition, sources=["source.requirements", "source.assumption_register"])
        item.update({"intent": intent, "operation": operation, "required_metrics": required_metrics, "required_dimensions": required_dimensions, "exactly_two_periods": False, "output_fields": output_fields, "failure_conditions": failure_conditions})
        analyses.append(item)

    policies = []
    for identifier, en, zh, definition, allowed_roles, denied_roles, grains, denied_fields, min_group in [
        ("policy.cash_surveillance_demo", "Cash Surveillance Demo Policy", "现金监察演示策略", "Allow synthetic row evidence for surveillance triage for at most three months.", ["MarketSurveillanceDemo", "TradingDemo"], ["MarketsDemo", "ExternalUser"], ["aggregate", "daily", "participant", "trade_event", "order_event"], [], 1),
        ("policy.cash_markets_demo", "Cash Markets Aggregate Demo Policy", "现金市场汇总演示策略", "Allow only aggregate synthetic trends with participant names and row evidence denied.", ["MarketsDemo"], ["ExternalUser"], ["aggregate", "daily", "instrument", "market_segment"], ["participant_id", "participant_name", "trading_activity_id", "order_id"], 3),
    ]:
        item = _governed(identifier, en, zh, definition, sources=["source.requirements", "source.assumption_register"], decisions=["decision.demo_policy"])
        item.update({"allowed_roles": allowed_roles, "denied_roles": denied_roles, "allowed_grains": grains, "denied_fields": denied_fields, "minimum_group_size": min_group})
        policies.append(item)

    questions = []
    for identifier, en, zh, definition, examples, pattern, inputs, expected in [
        ("question.self_trade_yesterday", "Self-Trades Yesterday", "昨日自成交分析", "Summarize potential self-trade candidates for a specified business date.", ["Analyze potential self-trades for 2026-08-07.", "What was the potential self-trade rate yesterday?"], "analysis.self_trade_summary", ["business_date"], "Eligible trade count, candidate count, rate, candidate participants/instruments and the triage-only limitation."),
        ("question.self_trade_weekly_trend", "Self-Trade Daily Trend", "自成交日趋势", "Show the potential self-trade trend over the selected week.", ["Show the daily potential self-trade trend for 2026-08-03 to 2026-08-07."], "analysis.self_trade_trend", ["start_date", "end_date"], "One row per business date with counts and percentage."),
        ("question.self_trade_participant_timeline", "Participant Evidence Timeline", "参与者证据时间线", "Show the observed timeline for one candidate participant.", ["Show the evidence timeline for PART001 on 2026-08-03."], "analysis.self_trade_timeline", ["participant_id", "business_date"], "Chronological candidate trade and linked observed order events, with lifecycle completeness disclosed."),
        ("question.trade_latency", "Trade Capture Latency", "成交捕获延迟", "Profile valid trade capture latency for a selected period.", ["What were p50, p95 and p99 trade capture latency for the sample week?"], "analysis.trade_latency_profile", ["start_date", "end_date"], "Count, min, p50, p95, p99, max and exception count in milliseconds; no SLA claim."),
        ("question.evidence", "Answer Evidence", "答案证据", "Explain the exact governed definitions and computations behind a prior answer.", ["Show the evidence behind that self-trade rate."], "analysis.cash_evidence_audit", ["execution_id"], "Claim-level links to metrics, decisions, dataset and query identity."),
    ]:
        item = _governed(identifier, en, zh, definition, sources=["source.requirements", "source.assumption_register"])
        item.update({"examples": examples, "analysis_pattern": pattern, "required_inputs": inputs, "expected_answer": expected})
        questions.append(item)

    process = _governed(
        "process.cash_trading_analysis",
        "Governed Cash Trading Analysis",
        "受治理现金交易分析",
        "From a natural-language question to a policy-scoped deterministic result and evidence-backed explanation.",
        sources=["source.requirements", "source.assumption_register"],
        decisions=["decision.demo_policy", "decision.source_classification"],
    )
    process.update(
        {
            "process_type": "analysis",
            "trigger": "An authorized demo user asks a supported self-trade, latency or evidence question.",
            "steps": [
                {"id": "authorize", "name": "Resolve role, time window and output grain", "actor": "actor.ontology_agent", "operation": "PolicyGate", "governed_refs": ["policy.cash_surveillance_demo", "policy.cash_markets_demo"], "output_artifacts": ["policy_decision"], "on_failure": "refuse"},
                {"id": "bind", "name": "Bind the question to a registered analysis pattern and metrics", "actor": "actor.ontology_agent", "operation": "SemanticBinding", "governed_refs": [item["id"] for item in analyses], "output_artifacts": ["analysis_plan"], "on_failure": "clarify"},
                {"id": "execute", "name": "Execute bounded DuckDB tools over verified Parquet", "actor": "actor.ontology_agent", "operation": "DeterministicExecution", "governed_refs": ["source.cash_trade_analytics", "rule.eligible_trade", "rule.self_trade_eligible", "rule.potential_self_trade", "rule.nonnegative_latency"], "output_artifacts": ["verified_fact_set"], "on_failure": "stop"},
                {"id": "evidence", "name": "Attach claims to metrics, decisions, data and query identities", "actor": "actor.ontology_agent", "operation": "EvidenceAssembly", "governed_refs": ["analysis.cash_evidence_audit"], "output_artifacts": ["answer", "claim_evidence", "limitation_disclosure"], "on_failure": "stop"},
            ],
            "exception_paths": ["ambiguous_time_to_clarify", "unsupported_suspicion_rule_to_clarify", "misconduct_conclusion_to_refuse", "unauthorized_detail_to_refuse", "validation_failure_to_no_answer"],
        }
    )

    decision_defs = [
        ("decision.source_classification", "What claim can be made from the supplied packet?", ["HKEX validated", "Deloitte confirmed", "Constructed synthetic only"], "Treat the case as constructed synthetic and illustrative only.", ["scenario.cash_trading_activity_monitoring", *[item["id"] for item in raw_data_sources]]),
        ("decision.cancel_spelling", "Which cancellation status spelling is canonical?", ["CANCELED", "CANCELLED"], "Use CANCELED and accept CANCELLED only as an input alias.", ["property.order.order_status"]),
        ("decision.order_lifecycle", "What is the observed order lifecycle key?", ["order_id", "venue/date/order", "activity_id"], "Use venue_code + trading_date + order_id and disclose incomplete observed timelines.", ["entity.order_activity", "property.order.order_id"]),
        ("decision.self_trade_candidate", "What constitutes the first demo self-trade candidate?", ["same normalized side participants", "same account", "business-defined surveillance model"], "Use same normalized buy and sell participant IDs as a triage candidate only.", ["property.trade.has_both_participant_ids", "property.trade.is_potential_self_trade", "rule.potential_self_trade", "metric.potential_self_trade_count", "metric.potential_self_trade_rate"]),
        ("decision.self_trade_denominator", "What is the potential self-trade rate denominator?", ["all trades", "eligible active trades with both participant IDs", "all order events"], "Use eligible active trades with both-side participant IDs.", ["rule.self_trade_eligible", "metric.self_trade_eligible_trade_count", "metric.potential_self_trade_rate"]),
        ("decision.trade_eligibility", "Which trade rows are eligible?", ["all rows", "active TRADE rows", "active rows excluding correction lineage"], "Use active TRADE rows and exclude cancel/bust/corrected originals.", ["property.trade.is_eligible_trade", "rule.eligible_trade", "metric.eligible_trade_count"]),
        ("decision.submitted_order", "What counts as a submitted order in an incomplete observed extract?", ["NEW events only", "NEW or REJECT lifecycle", "every observed lifecycle"], "Use one distinct venue + trading date + order ID lifecycle containing any NEW or REJECT event.", ["property.order_lifecycle.is_submitted", "rule.submitted_order", "metric.submitted_order_count", "metric.order_rejection_rate", "metric.order_to_trade_ratio"]),
        ("decision.rejected_order", "What counts as a rejected submitted order?", ["terminal state only", "any REJECT event", "any REJECT event or REJECTED state"], "Mark a submitted lifecycle rejected when any observed event is REJECT or has REJECTED state.", ["property.order_lifecycle.is_rejected", "rule.rejected_order", "metric.rejected_order_count", "metric.order_rejection_rate"]),
        ("decision.client_classification", "What constitutes a client for the constructed-synthetic case?", ["participant_type=CLIENT", "account_type=CLIENT", "beneficial owner mapping"], "Use the effective account_reference row with participant_type=CLIENT; exclude unresolved participants.", ["property.trade.is_active_client", "property.order_lifecycle.is_client", "rule.active_client_trade", "rule.eligible_client_order", "metric.active_client_trading_volume", "metric.client_order_completion_rate"]),
        ("decision.client_completion", "What is an eligible and completed client order?", ["latest FILLED among all client lifecycles", "latest FILLED among submitted non-rejected client lifecycles", "any fill event"], "Use submitted client lifecycles with no observed rejection as denominator and latest valid FILLED state as numerator.", ["property.order_lifecycle.is_eligible_client_order", "property.order_lifecycle.is_fully_filled", "metric.eligible_client_order_count", "metric.fully_filled_client_order_count", "metric.client_order_completion_rate"]),
        ("decision.cancel_ratio", "What is the cancel-to-trade numerator?", ["cancel events", "distinct lifecycles containing CANCEL", "terminal canceled lifecycles"], "Count distinct observed order lifecycles containing an eligible CANCEL event and divide by eligible active trades for the same cohort.", ["property.order_lifecycle.is_canceled", "rule.canceled_order", "metric.canceled_order_count", "metric.cancel_to_trade_ratio"]),
        ("decision.order_to_trade", "What denominator convention applies to order-to-trade?", ["distinct trades", "two times distinct active trades", "execution events"], "Use two times distinct eligible active trades to represent the two matched sides in this synthetic case.", ["metric.order_to_trade_denominator", "metric.order_to_trade_ratio"]),
        ("decision.latency_convention", "How is capture latency calculated and summarized?", ["average", "nearest-rank percentiles", "continuous percentiles"], "Use receive minus transaction timestamp in integer milliseconds, nearest-rank p50/p95/p99, and separate negative exceptions.", ["property.trade.capture_latency_ms", "property.trade.is_nonnegative_latency", "rule.nonnegative_latency", "metric.trade_capture_latency_ms", "analysis.trade_latency_profile"]),
        ("decision.notional_currency", "How are supplied notional fields labelled?", ["both HKD", "native HKD and converted USD", "USD only"], "Label trade_notional as HKD and base_notional_before_haircut as USD.", ["property.trade.trade_notional_hkd", "property.trade.base_notional_usd"]),
        ("decision.calendar_key", "What is the logical calendar key?", ["business_date", "calendar_code + business_date"], "Use calendar_code + business_date.", ["property.calendar.calendar_key"]),
        ("decision.time_convention", "How are source times interpreted?", ["already UTC", "Hong Kong wall time then UTC", "local only"], "Interpret source wall time as Asia/Hong_Kong, persist UTC, retain venue business date.", ["scenario.cash_trading_activity_monitoring", "property.trade.business_date", "property.trade.transaction_timestamp", "property.trade.receive_timestamp", "property.order.trading_date", "property.order.transaction_timestamp"]),
        ("decision.demo_policy", "What access policy applies before production IAM exists?", ["all users all rows", "demo role projection", "no access"], "Apply the explicit synthetic-demo role projection and make no production IAM claim.", ["policy.cash_surveillance_demo", "policy.cash_markets_demo", "process.cash_trading_analysis"]),
    ]
    decisions = [
        {
            "id": identifier,
            "question": question,
            "options": options,
            "decision": decision,
            "decided_by": DOMAIN_OWNER,
            "decided_on": "2026-08-20",
            "affects": affects,
            "residual_assumption": "Provisional synthetic decision; mapped to the versioned CT-ASM register and replaceable after external confirmation.",
        }
        for identifier, question, options, decision, affects in decision_defs
    ]

    source_file_index = {item["source_id"]: item for item in source_manifest["files"]}
    sources = [
        _source_ref("source.requirements", "requirement_transcription", "Deloitte HK requirements transcription", f"intake/source-manifest.json#SRC-REQ-001 sha256={source_file_index['SRC-REQ-001']['sha256']}", "secondary", "Transcribed business context; not an exported HKEX source document."),
        _source_ref("source.metric_logic", "metric_transcription", "Deloitte HK metric logic transcription", f"intake/source-manifest.json#SRC-REQ-001 sha256={source_file_index['SRC-REQ-001']['sha256']}", "secondary", "Common metric examples; definitions remain subject to confirmation."),
        _source_ref("source.data_dictionary", "data_dictionary", "Deloitte HK generated data dictionary", f"intake/source-manifest.json#SRC-DICT-001 sha256={source_file_index['SRC-DICT-001']['sha256']}", "secondary", "Generated and field-existence cross-checked; physical production names may differ."),
        _source_ref("source.sample_data", "sample_data", "Deloitte HK constructed-synthetic sample data", f"intake/source-manifest.json#SRC-SAMPLE-001 sha256={source_file_index['SRC-SAMPLE-001']['sha256']}", "assumption", "One-week constructed-synthetic sample; not HKEX production data."),
        _source_ref("source.assumption_register", "assumption_register", "PoC cash-trading assumption and decision register", f"governance/assumption-register.json sha256={file_checksum(assumption_path)}", "assumption", "Every correction, provisional definition and derived-control convention is versioned here."),
        _source_ref("source.derived_oracle", "derived_control", "Independent constructed-synthetic golden controls", f"golden/oracle.json sha256={file_checksum(oracle_path)}", "assumption", "Independently recomputed from typed Parquet; not Deloitte/HKEX known-correct evidence."),
        _source_ref("source.compiler_sql", "sql", "Compiler-generated Cash Trading reference SQL", f"sql/reference_controls.sql sha256={file_checksum(sql_path)}", "assumption", "Generated reference SQL; no existing SQL was supplied."),
    ]

    scenario = _governed(
        "scenario.cash_trading_activity_monitoring",
        "Cash Market Order and Trading Activity Monitoring",
        "现金市场订单与成交活动监控",
        "Constructed-synthetic cash-market scenario covering order lifecycle, client activity, execution, self-trade triage and trade-capture latency semantics.",
        sources=["source.requirements", "source.metric_logic", "source.assumption_register"],
        decisions=["decision.source_classification", "decision.time_convention", "decision.demo_policy"],
        tags=["constructed_synthetic", "cash_trading", "order_lifecycle", "client_activity", "surveillance_triage", "latency"],
    )
    scenario.update(
        {
            "timezone": "Asia/Hong_Kong",
            "market_id": "SYNTH-XHKG-CASH",
            "data_window_start": "2026-08-03",
            "data_window_end": "2026-08-09",
            "periods": [{"id": "sample-week-2026-08-03", "start": "2026-08-03", "end": "2026-08-09", "inclusive": True}],
            "default_role": "MarketSurveillanceDemo",
        }
    )

    package_payload = {
        "package_id": "ontology.exchange_analytics.cash_trading",
        "version": "0.2.0",
        "status": "confirmed",
        "created_at": "2026-08-20T12:00:00+08:00",
        "scenario": scenario,
        "actors": actor_objects,
        "processes": [process],
        "sources": sources,
        "decisions": decisions,
        "entities": entities,
        "properties": properties,
        "relationships": relationships,
        "dimensions": dimensions,
        "rules": rules,
        "metrics": metrics,
        "data_sources": [*raw_data_sources, analytic_source, order_analytic_source],
        "bindings": bindings,
        "joins": joins,
        "analysis_patterns": analyses,
        "policies": policies,
        "questions": questions,
    }
    package = OntologyPackage.model_validate(package_payload)
    report = validate_semantic_package(package)
    failures = list(failed_checks(report))
    if failures:
        raise RuntimeError(
            "Candidate package failed semantic validation: "
            + "; ".join(f"{item.check_id}: {item.details}" for item in failures)
        )
    output_path = scenario_root / "ontology" / "package.yaml"
    output_path.write_text(
        yaml.safe_dump(
            package.model_dump(mode="json", exclude_none=True),
            sort_keys=False,
            allow_unicode=True,
            width=120,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "package_path": str(output_path),
                "package_checksum": package_checksum(package),
                "file_sha256": file_checksum(output_path),
                "semantic_checks": len(report.checks),
                "data_manifest_sha256": file_checksum(data_manifest_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
