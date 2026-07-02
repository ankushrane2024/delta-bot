from dataclasses import dataclass, field
from typing import Dict, Any, List
from .shared import SignalEvidence

@dataclass
class VolumeResult:
    evaluation_id: str
    volume_level: float
    volume_strength: float
    volume_expansion: float
    volume_contraction: float
    participation_strength: float
    breakout_confirmation: float
    exhaustion_probability: float
    continuation_confirmation: float
    confidence: float
    timestamp: str
    started_at: float
    completed_at: float
    execution_time_ms: float
    explanation: str
    supporting_evidence: List[SignalEvidence] = field(default_factory=list)
    debug_information: Dict[str, Any] = field(default_factory=dict)
