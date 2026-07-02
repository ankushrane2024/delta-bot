from dataclasses import dataclass, field
from typing import Dict, Any, List
from .shared import SignalEvidence

@dataclass
class OptionStressResult:
    evaluation_id: str
    call_stress_score: float
    put_stress_score: float
    portfolio_stress_score: float
    stress_velocity: float
    recovery_probability: float
    confidence: float
    explanation: str
    timestamp: str
    started_at: float
    completed_at: float
    execution_time_ms: float
    supporting_evidence: List[SignalEvidence] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    debug_information: Dict[str, Any] = field(default_factory=dict)
