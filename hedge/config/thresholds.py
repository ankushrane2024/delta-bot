from dataclasses import dataclass

@dataclass
class Thresholds:
    trend_exhaustion: float = 80.0
    volatility_spike: float = 1.5
    margin_warning: float = 0.7
    margin_critical: float = 0.85
