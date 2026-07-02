from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from .enums import AresDecision, HedgeSide, HedgeState

@dataclass
class HedgePlan:
    hedge_action: AresDecision
    hedge_side: HedgeSide
    hedge_ratio: float
    hedge_quantity: float
    hedge_reason: str
    urgency: float
    confidence: float
    execution_priority: int
    hedge_id: str
    linked_position_id: Optional[str]
    timestamp: str
    explanation: str
    started_at: float
    completed_at: float
    execution_time_ms: float
    debug_information: Dict[str, Any] = field(default_factory=dict)
