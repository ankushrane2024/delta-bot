from dataclasses import dataclass

@dataclass
class Weights:
    trend_weight: float = 0.4
    volatility_weight: float = 0.3
    structure_weight: float = 0.3
