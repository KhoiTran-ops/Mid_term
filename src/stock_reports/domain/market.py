"""Market-data contracts extracted from the source project."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OHLCVBar:
    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class MarketPrice:
    symbol: str
    price: float
    timestamp: datetime
    reference_price: float | None = None
