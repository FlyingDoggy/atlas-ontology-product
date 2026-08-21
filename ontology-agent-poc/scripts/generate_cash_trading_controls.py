from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from ontology_agent.io import canonical_bytes, file_checksum


GENERATOR_ID = "cash-trading-independent-control-generator"
GENERATOR_VERSION = "1.0.0"


def _read_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("contract") != "typed-tabular-dataset-manifest/v1":
        raise RuntimeError("Unsupported dataset manifest")
    return payload


def _verified_rows(data_dir: Path, manifest: dict[str, Any], table_name: str) -> list[dict[str, Any]]:
    matches = [item for item in manifest["tables"] if item["table"] == table_name]
    if len(matches) != 1:
        raise RuntimeError(f"Dataset manifest must contain exactly one {table_name}")
    item = matches[0]
    path = data_dir / item["path"]
    if file_checksum(path) != item["sha256"] or path.stat().st_size != item["size_bytes"]:
        raise RuntimeError(f"Dataset identity mismatch for {table_name}")
    table = pq.read_table(path)
    if table.num_rows != item["row_count"] or table.num_columns != item["column_count"]:
        raise RuntimeError(f"Dataset shape mismatch for {table_name}")
    return table.to_pylist()


def _nearest_rank(values: list[int], percentile: Decimal) -> int:
    if not values:
        raise RuntimeError("Cannot calculate a percentile on an empty population")
    ordered = sorted(values)
    rank = max(1, math.ceil(float(percentile) * len(ordered)))
    return ordered[rank - 1]


def _iso(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    scenario_root = project_root / "scenarios" / "cash_trading"
    data_dir = scenario_root / "data"
    manifest_path = data_dir / "manifest.json"
    manifest = _read_manifest(manifest_path)
    trades = _verified_rows(data_dir, manifest, "trading_activity")
    orders = _verified_rows(data_dir, manifest, "order_activity")

    corrected_original_ids = {
        row["reference_trading_activity_id"]
        for row in trades
        if str(row.get("is_correction") or "N").strip().upper()
        in {"Y", "TRUE", "1"}
        and row.get("reference_trading_activity_id") is not None
    }
    eligible = [
        row
        for row in trades
        if row["activity_type"] == "TRADE"
        and row["trade_status"] == "ACTIVE"
        and str(row.get("is_correction") or "N").strip().upper()
        not in {"Y", "TRUE", "1"}
        and row["buy_participant_id"] is not None
        and row["sell_participant_id"] is not None
        and row["reference_trading_activity_id"] is None
        and row["trading_activity_id"] not in corrected_original_ids
    ]
    candidates = [
        row
        for row in eligible
        if str(row["buy_participant_id"]).strip().upper()
        == str(row["sell_participant_id"]).strip().upper()
    ]
    if not eligible:
        raise RuntimeError("Self-trade denominator is empty")
    daily: dict[date, dict[str, int]] = defaultdict(lambda: {"eligible": 0, "candidate": 0})
    candidate_ids = {row["trading_activity_id"] for row in candidates}
    candidate_participants: Counter[str] = Counter()
    for row in eligible:
        daily[row["business_date"]]["eligible"] += 1
    for row in candidates:
        daily[row["business_date"]]["candidate"] += 1
        candidate_participants[str(row["buy_participant_id"])] += 1

    latencies: list[int] = []
    negative_latency_count = 0
    for row in eligible:
        transaction_timestamp = row["transaction_timestamp"]
        receive_timestamp = row["receive_timestamp"]
        if transaction_timestamp is None or receive_timestamp is None:
            continue
        delta_ms = round((receive_timestamp - transaction_timestamp).total_seconds() * 1000)
        if delta_ms < 0:
            negative_latency_count += 1
        else:
            latencies.append(delta_ms)

    candidate_order_ids = {
        order_id
        for row in candidates
        for order_id in (row["buy_order_id"], row["sell_order_id"])
        if order_id is not None
    }
    linked_candidate_order_events = [
        row for row in orders if row["order_id"] in candidate_order_ids
    ]
    lifecycle_events: dict[tuple[object, object, object], list[dict[str, Any]]] = defaultdict(list)
    for row in orders:
        key = (row["venue_code"], row["trading_date"], row["order_id"])
        lifecycle_events[key].append(row)
    lifecycles_with_new = sum(
        any(row["activity_type"] == "NEW" for row in rows)
        for rows in lifecycle_events.values()
    )
    all_trade_order_ids = {
        order_id
        for row in eligible
        for order_id in (row["buy_order_id"], row["sell_order_id"])
        if order_id is not None
    }
    trade_linked_without_new = sum(
        1
        for key, rows in lifecycle_events.items()
        if key[2] in all_trade_order_ids
        and not any(row["activity_type"] == "NEW" for row in rows)
    )

    script_path = Path(__file__).resolve()
    oracle = {
        "contract": "cash-trading-independent-oracle/v1",
        "oracle_id": "cash-trading.synthetic.self-trade-latency.v1",
        "classification": "constructed_synthetic",
        "dataset_manifest": {
            "path": "data/manifest.json",
            "sha256": file_checksum(manifest_path),
            "build_id": manifest["build_id"],
        },
        "assumption_register_checksum": manifest["assumption_register_checksum"],
        "generator": {
            "id": GENERATOR_ID,
            "version": GENERATOR_VERSION,
            "implementation_sha256": file_checksum(script_path),
            "method": "Python/PyArrow row computation independent of the DuckDB runtime SQL",
        },
        "controls": {
            "potential_self_trade": {
                "decision_ids": ["CT-ASM-005", "CT-ASM-006", "CT-ASM-007"],
                "eligible_trade_count": len(eligible),
                "candidate_trade_count": len(candidates),
                "candidate_rate_ratio": str(Decimal(len(candidates)) / Decimal(len(eligible))),
                "candidate_rate_percent": str(
                    Decimal(100) * Decimal(len(candidates)) / Decimal(len(eligible))
                ),
                "candidate_participant_count": len(candidate_participants),
                "candidate_participants": [
                    {"participant_id": participant_id, "candidate_trade_count": count}
                    for participant_id, count in sorted(candidate_participants.items())
                ],
                "candidate_trading_activity_ids": sorted(candidate_ids),
                "candidate_linked_order_id_count": len(candidate_order_ids),
                "candidate_linked_order_event_count": len(linked_candidate_order_events),
                "daily": [
                    {
                        "business_date": _iso(business_date),
                        "eligible_trade_count": counts["eligible"],
                        "candidate_trade_count": counts["candidate"],
                        "candidate_rate_percent": str(
                            Decimal(100)
                            * Decimal(counts["candidate"])
                            / Decimal(counts["eligible"])
                        ),
                    }
                    for business_date, counts in sorted(daily.items())
                ],
            },
            "trade_capture_latency": {
                "decision_ids": ["CT-ASM-008", "CT-ASM-020"],
                "eligible_latency_count": len(latencies),
                "negative_latency_count": negative_latency_count,
                "minimum_ms": min(latencies),
                "p50_ms": _nearest_rank(latencies, Decimal("0.50")),
                "p95_ms": _nearest_rank(latencies, Decimal("0.95")),
                "p99_ms": _nearest_rank(latencies, Decimal("0.99")),
                "maximum_ms": max(latencies),
                "percentile_method": "nearest_rank",
                "sla_threshold": None,
            },
            "observed_order_lifecycle_quality": {
                "decision_ids": ["CT-ASM-003", "CT-ASM-004"],
                "observed_lifecycle_count": len(lifecycle_events),
                "lifecycle_with_new_count": lifecycles_with_new,
                "lifecycle_without_new_count": len(lifecycle_events) - lifecycles_with_new,
                "trade_linked_order_id_count": len(all_trade_order_ids),
                "trade_linked_order_without_new_count": trade_linked_without_new,
            },
        },
        "limitations": [
            "Internally derived from the constructed-synthetic packet; not a Deloitte/HKEX known-correct control",
            "Potential self-trade is a deterministic triage candidate and not a market-abuse conclusion",
            "No latency SLA or breach classification is assumed",
            "Order timelines are observed-event timelines and may be incomplete",
        ],
    }
    output_path = scenario_root / "golden" / "oracle.json"
    output_path.write_bytes(canonical_bytes(oracle) + b"\n")
    print(
        json.dumps(
            {
                "oracle_path": str(output_path),
                "oracle_sha256": file_checksum(output_path),
                "self_trade_candidates": len(candidates),
                "eligible_trades": len(eligible),
                "latency_p95_ms": oracle["controls"]["trade_capture_latency"]["p95_ms"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
