from dataclasses import dataclass, field
from typing import Dict, Any, List

@dataclass
class PositionContext:
    # Market
    futures_price: float = 0.0
    mark_price: float = 0.0
    last_traded_price: float = 0.0
    
    # Options
    short_call_strike: float = 0.0
    short_put_strike: float = 0.0
    call_mark_price: float = 0.0
    put_mark_price: float = 0.0
    call_bid: float = 0.0
    put_bid: float = 0.0
    call_delta: float = 0.0
    put_delta: float = 0.0
    call_gamma: float = 0.0
    put_gamma: float = 0.0
    call_theta: float = 0.0
    put_theta: float = 0.0
    call_vega: float = 0.0
    put_vega: float = 0.0
    call_iv: float = 0.0
    put_iv: float = 0.0
    
    # Position
    total_lots: int = 1
    call_leg_pnl: float = 0.0
    put_leg_pnl: float = 0.0
    total_pnl: float = 0.0
    position_size: float = 0.0
    
    # Account
    available_margin: float = 0.0
    wallet_balance: float = 0.0
    
    # Market Data
    open_interest: float = 0.0
    volume: float = 0.0

    # System
    is_valid: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
