from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class MarketContext:
    current_price: float = 0.0
    orderbook_imbalance: float = 0.0
    funding_rate: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
