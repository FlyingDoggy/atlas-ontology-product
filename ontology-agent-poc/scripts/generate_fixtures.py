from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal, ROUND_DOWN
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DIR = PROJECT_ROOT / "scenarios" / "adt"
DATA_DIR = SCENARIO_DIR / "data"
MARKET_ID = "SYNTH-CASH"

SEGMENTS = {
    "MB": ("INST-MB", "Main Board"),
    "ETF": ("INST-ETF", "Exchange Traded Funds"),
    "STRUCT": ("INST-STRUCT", "Structured Products"),
    "OTHER": ("INST-OTHER", "Other Securities"),
}

TARGETS = {
    "2025-Q3": {
        "MB": Decimal("6200000.00"),
        "ETF": Decimal("1100000.00"),
        "STRUCT": Decimal("610000.00"),
        "OTHER": Decimal("300000.00"),
    },
    "2025-Q4": {
        "MB": Decimal("5000000.00"),
        "ETF": Decimal("940000.00"),
        "STRUCT": Decimal("560000.00"),
        "OTHER": Decimal("240000.00"),
    },
}

PERIODS = {
    "2025-Q3": (date(2025, 7, 1), date(2025, 9, 30), 63),
    "2025-Q4": (date(2025, 10, 1), date(2025, 12, 31), 61),
}


def _date_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _distributed_values(total: Decimal, count: int) -> list[Decimal]:
    base = (total / count).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    values = [base for _ in range(count)]
    values[-1] += total - sum(values)
    assert sum(values) == total
    return values


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    calendar_rows: list[dict[str, object]] = []
    trading_dates: dict[str, list[date]] = {}
    for period_id, (start, end, target_days) in PERIODS.items():
        dates = _date_range(start, end)
        weekdays = [value for value in dates if value.weekday() < 5]
        approved = set(weekdays[:target_days])
        trading_dates[period_id] = sorted(approved)
        for calendar_date in dates:
            calendar_rows.append(
                {
                    "market_id": MARKET_ID,
                    "calendar_date": calendar_date.isoformat(),
                    "period_id": period_id,
                    "is_trading_day": str(calendar_date in approved).lower(),
                }
            )

    instrument_rows = [
        {
            "instrument_id": instrument_id,
            "segment_id": segment_id,
            "segment_name": segment_name,
        }
        for segment_id, (instrument_id, segment_name) in SEGMENTS.items()
    ]

    trade_rows: list[dict[str, object]] = []
    sequence = 1
    for period_id, segment_totals in TARGETS.items():
        dates = trading_dates[period_id]
        for segment_offset, (segment_id, total) in enumerate(segment_totals.items()):
            instrument_id = SEGMENTS[segment_id][0]
            for row_offset, amount in enumerate(_distributed_values(total, 12)):
                order_value = (amount * Decimal("1.17") + Decimal("500.00")).quantize(Decimal("0.01"))
                trade_rows.append(
                    {
                        "trade_id": f"T{sequence:04d}",
                        "market_id": MARKET_ID,
                        "trade_date": dates[(row_offset * 5 + segment_offset) % len(dates)].isoformat(),
                        "instrument_id": instrument_id,
                        "executed_value_hkd_mn": f"{amount:.2f}",
                        "order_value_hkd_mn": f"{order_value:.2f}",
                        "status": "EXECUTED",
                        "cancellation_flag": "false",
                    }
                )
                sequence += 1

        # Sentinels make omitted filters materially wrong while leaving the oracle unchanged.
        for status, cancelled, amount in [
            ("REJECTED", False, Decimal("777777.77")),
            ("EXECUTED", True, Decimal("888888.88")),
        ]:
            trade_rows.append(
                {
                    "trade_id": f"T{sequence:04d}",
                    "market_id": MARKET_ID,
                    "trade_date": dates[-1].isoformat(),
                    "instrument_id": "INST-MB",
                    "executed_value_hkd_mn": f"{amount:.2f}",
                    "order_value_hkd_mn": f"{amount * Decimal('1.31'):.2f}",
                    "status": status,
                    "cancellation_flag": str(cancelled).lower(),
                }
            )
            sequence += 1

    files = {
        "trade_fact.csv": (
            [
                "trade_id",
                "market_id",
                "trade_date",
                "instrument_id",
                "executed_value_hkd_mn",
                "order_value_hkd_mn",
                "status",
                "cancellation_flag",
            ],
            trade_rows,
        ),
        "instrument_dim.csv": (
            ["instrument_id", "segment_id", "segment_name"],
            instrument_rows,
        ),
        "trading_calendar.csv": (
            ["market_id", "calendar_date", "period_id", "is_trading_day"],
            calendar_rows,
        ),
    }
    for filename, (fieldnames, rows) in files.items():
        _write_csv(DATA_DIR / filename, fieldnames, rows)

    manifest = {
        "dataset_id": "adt-fixture-v1",
        "synthetic": True,
        "market_id": MARKET_ID,
        "files": {
            filename: {
                "sha256": _sha256(DATA_DIR / filename),
                "rows": len(rows),
            }
            for filename, (_, rows) in files.items()
        },
    }
    (DATA_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    generate()

