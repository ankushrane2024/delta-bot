from dataclasses import dataclass, field
from typing import Dict, Any, List
from .shared import SignalEvidence

@dataclass
class IVResult:
    evaluation_id: str
    iv_level: float
    iv_strength: float
    iv_expansion: float
    iv_contraction: float
    iv_acceleration: float
    iv_panic_probability: float
    iv_mean_reversion_probability: float
    confidence: float
    timestamp: str
    started_at: float
    completed_at: float
    execution_time_ms: float
    explanation: str
    supporting_evidence: List[SignalEvidence] = field(default_factory=list)
    debug_information: Dict[str, Any] = field(default_factory=dict)
