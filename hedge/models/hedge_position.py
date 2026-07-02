from dataclasses import dataclass
from typing import Optional

@dataclass
class HedgePosition:
    symbol: str
    size: float
    entry_price: float
    current_price: float
    pnl: float
    unrealized_pnl: float
