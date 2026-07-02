from dataclasses import dataclass, field
from typing import Dict, Any, List
from .enums import TrendDirection
from .shared import SignalEvidence

@dataclass
class TrendResult:
    evaluation_id: str
    trend_direction: TrendDirection
    trend_strength: float
    trend_confidence: float
    trend_persistence: float
    trend_acceleration: float
    continuation_probability: float
    reversal_probability: float
    whipsaw_probability: float
    signal_reliability: float
    timestamp: str
    started_at: float
    completed_at: float
    execution_time_ms: float
    explanation: str
    supporting_signals: Dict[str, Any] = field(default_factory=dict)
    analyzer_health_summary: Dict[str, Any] = field(default_factory=dict)
    debug_information: Dict[str, Any] = field(default_factory=dict)
