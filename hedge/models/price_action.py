from dataclasses import dataclass, field
from typing import Dict, Any, List
from .enums import TrendDirection
import uuid
import time

@dataclass
class PriceActionEvidence:
    source: str
    score: float
    confidence: float
    quality: float
    explanation: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    debug_information: Dict[str, Any] = field(default_factory=dict)

@dataclass
class PriceActionResult:
    evaluation_id: str
    direction: TrendDirection
    movement_strength: float
    momentum_strength: float
    impulse_strength: float
    pullback_strength: float
    breakout_quality: float
    rejection_strength: float
    continuation_bias: float
    reversal_bias: float
    confidence: float
    timestamp: str
    started_at: float
    completed_at: float
    execution_time_ms: float
    explanation: str
    supporting_evidence: List[PriceActionEvidence] = field(default_factory=list)
    debug_information: Dict[str, Any] = field(default_factory=dict)

@dataclass
class AnalyzerHealth:
    loaded_evaluators: int
    failed_evaluators: int
    warnings: List[str]
    replay_mode: bool
    last_execution_time: float
