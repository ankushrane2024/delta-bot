from dataclasses import dataclass, field
from typing import Dict, Any, List

@dataclass
class PositionContext:
    total_lots: int = 1
    call_position_size: float = 0.0
    put_position_size: float = 0.0
    call_pnl: float = 0.0
    put_pnl: float = 0.0
    call_delta: float = 0.0
    put_delta: float = 0.0
    call_gamma: float = 0.0
    put_gamma: float = 0.0
    call_vega: float = 0.0
    put_vega: float = 0.0
    call_theta: float = 0.0
    put_theta: float = 0.0
    is_valid: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
