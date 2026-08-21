"""Installed scenario adapters.

The registry is product composition, not business logic. Each adapter owns its draft
schema and translation while Studio consumes only the common editor/operation contract.
"""

from .adt_studio import ADT_STUDIO_ADAPTER_ID, ADTStudioAdapter
from .cash_trading_studio import (
    CASH_TRADING_STUDIO_ADAPTER_ID,
    CashTradingStudioAdapter,
)


__all__ = [
    "ADT_STUDIO_ADAPTER_ID",
    "ADTStudioAdapter",
    "CASH_TRADING_STUDIO_ADAPTER_ID",
    "CashTradingStudioAdapter",
]
