from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from .enums import MarketRegime

@dataclass
class TransitionRecord:
    previous_regime: Optional[MarketRegime]
    requested_regime: MarketRegime
    accepted: bool
    reason: str
    confidence: float
    timestamp: str

@dataclass
class MarketRegimeResult:
    evaluation_id: str
    current_regime: MarketRegime
    previous_regime: Optional[MarketRegime]
    confidence: float
    transition_reason: str
    transition_allowed: bool
    regime_duration: float
    regime_strength: float
    stability_score: float
    timestamp: str
    debug_information: Dict[str, Any] = field(default_factory=dict)
