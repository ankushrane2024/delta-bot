from dataclasses import dataclass, field
from typing import Dict, Any, List
from .shared import SignalEvidence

@dataclass
class VolatilityResult:
    evaluation_id: str
    volatility_level: float
    volatility_strength: float
    volatility_expansion: float
    volatility_compression: float
    volatility_acceleration: float
    breakout_probability: float
    panic_probability: float
    stability_score: float
    confidence: float
    timestamp: str
    started_at: float
    completed_at: float
    execution_time_ms: float
    explanation: str
    supporting_evidence: List[SignalEvidence] = field(default_factory=list)
    debug_information: Dict[str, Any] = field(default_factory=dict)
