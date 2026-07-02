from dataclasses import dataclass, field
from .thresholds import Thresholds
from .weights import Weights
from typing import Dict, Any

@dataclass
class HedgeConfig:
    thresholds: Thresholds = field(default_factory=Thresholds)
    weights: Weights = field(default_factory=Weights)
    risk_limits: Dict[str, float] = field(default_factory=dict)
    analytics_settings: Dict[str, Any] = field(default_factory=dict)
    replay_settings: Dict[str, Any] = field(default_factory=dict)
