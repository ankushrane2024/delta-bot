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
