from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class RiskScore:
    overall_risk: float
    components: Dict[str, float]
    
@dataclass
class VolatilityScore:
    current_iv: float
    historical_volatility: float
    iv_rank: float
    
@dataclass
class StructureScore:
    support_proximity: float
    resistance_proximity: float
    breakout_probability: float

@dataclass
class PositionHeat:
    symbol: str
    heat_index: float
    pnl_pct: float
