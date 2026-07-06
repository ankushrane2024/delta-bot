from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import hashlib
import json

from hedge.context.market_context import MarketContext
from hedge.models.trend import TrendResult
from hedge.models.regime import MarketRegimeResult
from hedge.models.position import PositionRiskResult
from hedge.models.decision import HedgeDecision
from hedge.models.sizing import HedgeSizingResult
from hedge.models.hedge import HedgePlan
from hedge.models.portfolio import PortfolioSnapshot

@dataclass(frozen=True)
class TickResult:
    """
    Canonical immutable snapshot of a single pipeline evaluation tick.
    Once created, this acts as the foundational record for analytics, reporting, and shadow validation.
    """
    timestamp: float
    tick_number: int
    schema_version: str = "1.0.0"
    
    # Contexts and Results
    market_context: Optional[MarketContext] = None
    trend_result: Optional[TrendResult] = None
    regime_result: Optional[MarketRegimeResult] = None
    risk_result: Optional[PositionRiskResult] = None
    hedge_decision: Optional[HedgeDecision] = None
    hedge_sizing: Optional[HedgeSizingResult] = None
    hedge_plan: Optional[HedgePlan] = None
    execution_summary: Optional[Dict[str, Any]] = None
    portfolio_snapshot: Optional[PortfolioSnapshot] = None
    provider_health: Optional[str] = None
    pipeline_latency: float = 0.0

    # Computed deterministically during initialization
    tick_hash: str = field(init=False)

    def __post_init__(self):
        # Deterministic hashing of the tick contents
        hash_components = {
            "timestamp": self.timestamp,
            "tick_number": self.tick_number,
            "schema_version": self.schema_version,
            "market_hash": str(self.market_context.metadata) if self.market_context else None,
            "risk_stress": self.risk_result.overall_risk_score if self.risk_result else None,
            "decision": self.hedge_decision.action.name if self.hedge_decision else None,
            "portfolio_hash": self.portfolio_snapshot.snapshot_hash if self.portfolio_snapshot else None,
        }
        
        # Serialize safely for hashing
        hash_str = json.dumps(hash_components, sort_keys=True)
        tick_hash = hashlib.sha256(hash_str.encode('utf-8')).hexdigest()
        
        # Bypass frozen constraint to set the hash
        object.__setattr__(self, 'tick_hash', tick_hash)
