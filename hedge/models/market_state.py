from dataclasses import dataclass
from typing import Dict, Any
from .enums import MarketState as MarketStateEnum

@dataclass
class MarketState:
    state: MarketStateEnum
    confidence: float
    metadata: Dict[str, Any]
