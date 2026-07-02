from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class PortfolioContext:
    total_margin: float = 0.0
    used_margin: float = 0.0
    free_margin: float = 0.0
    unrealized_pnl: float = 0.0
    active_positions: Dict[str, Any] = field(default_factory=dict)
