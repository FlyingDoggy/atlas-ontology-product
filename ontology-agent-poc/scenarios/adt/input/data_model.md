# Synthetic ADT data model

This attachment is machine-readable evidence for the reference case, not a transcription-template field.

```text
trade_fact (one source trade event)
  N ── trade_date ──> 1 trading_calendar (one market/date)
  N ── instrument_id ──> 1 instrument_dim (one instrument)
                                    └── segment_id / segment_name
```

## Tables and keys

| Table | Grain | Primary key | Relevant foreign keys |
|---|---|---|---|
| `trade_fact` | one synthetic source event | `trade_id` | `trade_date` → calendar; `instrument_id` → instrument |
| `instrument_dim` | one instrument | `instrument_id` | segment is represented as governed attributes in this compact fixture |
| `trading_calendar` | one market and calendar date | `(market_id, calendar_date)` | none |

Both joins are expected `N:1`. A duplicate on the right side is a blocking fan-out defect, not an instruction to deduplicate automatically.

