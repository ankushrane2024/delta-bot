from dataclasses import dataclass, field
from typing import Dict, Any, List
from .enums import TrendDirection
from .shared import SignalEvidence

@dataclass
class MarketStructureResult:
    evaluation_id: str
    structure_direction: TrendDirection
    structure_strength: float
    breakout_strength: float
    trend_integrity: float
    higher_high_quality: float
    lower_low_quality: float
    change_of_character_strength: float
    support_resistance_quality: float
    continuation_bias: float
    reversal_bias: float
    confidence: float
    timestamp: str
    started_at: float
    completed_at: float
    execution_time_ms: float
    explanation: str
    supporting_evidence: List[SignalEvidence] = field(default_factory=list)
    debug_information: Dict[str, Any] = field(default_factory=dict)
