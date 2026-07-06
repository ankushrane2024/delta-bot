from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional
import hashlib
import json
import math

class InvalidPortfolioStateError(Exception):
    pass

@dataclass(frozen=True)
class PortfolioSnapshot:
    timestamp: str
    version: int
    
    futures_position_qty: float
    futures_average_price: float
    
    net_options_delta: float
    
    realized_pnl: float
    unrealized_pnl: float
    
    margin_used: float
    available_balance: float
    
    active_orders: List[str]
    open_orders: List[str]
    
    hedge_status: str
    
    metadata: Dict[str, Any]
    
    snapshot_hash: str = field(init=False)
    
    def __post_init__(self):
        # 1. Validation
        self._validate()
        
        # 2. Hash generation
        # Frozen dataclasses require object.__setattr__ to modify fields in post_init
        object.__setattr__(self, 'snapshot_hash', self._generate_hash())
        
    def _validate(self):
        # Check NaNs and Infinites
        numeric_fields = [
            self.futures_position_qty, self.futures_average_price, 
            self.net_options_delta, self.realized_pnl, self.unrealized_pnl,
            self.margin_used, self.available_balance
        ]
        for val in numeric_fields:
            if math.isnan(val) or math.isinf(val):
                raise InvalidPortfolioStateError(f"NaN or Inf detected in portfolio state: {val}")
                
        # Impossible quantities
        if abs(self.futures_position_qty) > 10000.0:  # arbitrary sanity check bound
            raise InvalidPortfolioStateError(f"Impossible position quantity: {self.futures_position_qty}")
            
    def _generate_hash(self) -> str:
        # Create a deterministic dictionary of state to hash
        state = {
            "version": self.version,
            "qty": self.futures_position_qty,
            "avg_px": self.futures_average_price,
            "realized": self.realized_pnl,
            "active_orders": sorted(self.active_orders)
        }
        state_str = json.dumps(state, sort_keys=True)
        return hashlib.sha256(state_str.encode()).hexdigest()

    # Derived Properties
    @property
    def net_futures_delta(self) -> float:
        # In BTCUSD perps, 1 qty = 1 delta if it's BTC margined, but we simplify to 1:1 for this domain
        return self.futures_position_qty

    @property
    def combined_delta(self) -> float:
        return self.net_options_delta + self.net_futures_delta
        
    @property
    def gross_delta(self) -> float:
        return abs(self.net_options_delta) + abs(self.net_futures_delta)
        
    @property
    def hedged_delta(self) -> float:
        return abs(self.net_futures_delta)
        
    @property
    def hedge_ratio(self) -> float:
        if abs(self.net_options_delta) == 0:
            return 0.0
        # How much of the options delta is covered by futures
        ratio = abs(self.net_futures_delta) / abs(self.net_options_delta)
        if ratio > 10.0:
            # Overhedged beyond 1000% is considered a state error or extreme corner case, but we return ratio safely
            return round(ratio, 4)
        return round(ratio, 4)
        
    @property
    def hedge_efficiency(self) -> float:
        # 1.0 means perfectly delta neutral
        if abs(self.net_options_delta) == 0:
            return 1.0
        return 1.0 - (abs(self.combined_delta) / abs(self.net_options_delta))

    @property
    def position_direction(self) -> str:
        if self.futures_position_qty > 0:
            return "LONG"
        elif self.futures_position_qty < 0:
            return "SHORT"
        return "FLAT"

    @property
    def total_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl
