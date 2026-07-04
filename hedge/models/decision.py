from dataclasses import dataclass, field
from typing import Dict, Any, List
from .enums import AresDecision
from .shared import SignalEvidence

@dataclass
class DecisionResult:
    evaluation_id: str
    decision: AresDecision
    confidence: float
    urgency: float
    explanation: str
    timestamp: str
    started_at: float
    completed_at: float
    execution_time_ms: float
    supporting_evidence: List[SignalEvidence] = field(default_factory=list)
    debug_information: Dict[str, Any] = field(default_factory=dict)

from enum import Enum
import time

class HedgeAction(Enum):
    NO_ACTION = "NO_ACTION"
    MONITOR = "MONITOR"
    PREPARE_HEDGE = "PREPARE_HEDGE"
    PARTIAL_HEDGE = "PARTIAL_HEDGE"
    FULL_HEDGE = "FULL_HEDGE"
    EMERGENCY_HEDGE = "EMERGENCY_HEDGE"
    DEHEDGE = "DEHEDGE"

@dataclass
class HedgeDecision:
    action: HedgeAction
    urgency: float
    hedge_ratio: float
    reason: str
    dominant_cluster: str
    dominant_factor: str
    timestamp: float = field(default_factory=time.time)
    ema_stress: float = 0.0
    raw_stress: float = 0.0
    debug_information: Dict[str, Any] = field(default_factory=dict)
