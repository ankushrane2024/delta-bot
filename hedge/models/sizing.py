from dataclasses import dataclass, field
from typing import Dict, Any, List
import time

@dataclass
class HedgeSizingResult:
    target_delta: float
    current_delta: float
    delta_to_hedge: float
    hedge_side: str # "BUY", "SELL", "NONE"
    hedge_quantity: float
    current_hedge_quantity: float
    additional_quantity: float
    estimated_post_hedge_delta: float
    hedge_reason: str
    confidence: float
    warnings: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
