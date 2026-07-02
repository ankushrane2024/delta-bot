from dataclasses import dataclass
from typing import Optional, Dict, Any
from .enums import DecisionAction

@dataclass
class Decision:
    action: DecisionAction
    confidence: float
    reason: str
    metadata: Dict[str, Any]
    target_size: Optional[float] = None
    target_price: Optional[float] = None
