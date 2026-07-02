from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from ..engines.base_engine import AbstractBaseEngine

@dataclass
class ReplayFrame:
    timestamp: str
    market_context: Dict[str, Any]
    portfolio_context: Dict[str, Any]

@dataclass
class ReplayResult:
    scenario_id: str
    pnl: float
    events: List[Any]

@dataclass
class ReplaySession:
    session_id: str
    frames: List[ReplayFrame]
    results: Optional[ReplayResult] = None

class ReplayEngine(AbstractBaseEngine):

    def initialize(self) -> None:
        pass
        
    def evaluate(self, *args, **kwargs) -> Any:
        pass
        
    def reset(self) -> None:
        pass
        
    def health(self) -> bool:
        return True
        
    def metadata(self) -> Dict[str, Any]:
        return {"name": "ReplayEngine"}
