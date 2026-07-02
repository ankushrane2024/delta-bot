from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class HedgeContext:
    is_active: bool = False
    net_exposure: float = 0.0
    active_hedges: Dict[str, Any] = field(default_factory=dict)
