from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Iterator
import json
import math

@dataclass
class ReplayMarketData:
    timestamp: float
    spot_price: float
    mark_price: float
    call_greeks: Dict[str, float]
    put_greeks: Dict[str, float]
    iv: float
    volume: float
    funding: float
    open_interest: float
    metadata: Dict[str, Any] = field(default_factory=dict)

class ReplayDataProvider(ABC):
    @abstractmethod
    def __iter__(self) -> Iterator[ReplayMarketData]:
        pass

class SyntheticReplayProvider(ReplayDataProvider):
    """
    Generates synthetic market data curves for mathematical and state testing.
    Scenarios: flash_crash, slow_bleed, sideways, high_iv, low_iv, gap_open, whipsaw
    """
    def __init__(self, scenario: str = "sideways", start_time: float = 1000.0, steps: int = 1440):
        self.scenario = scenario
        self.start_time = start_time
        self.steps = steps # Default 1440 steps = 1 day if 1 step = 1 min
        
    def __iter__(self) -> Iterator[ReplayMarketData]:
        current_time = self.start_time
        base_price = 60000.0
        
        for i in range(self.steps):
            t_ratio = i / max(1, (self.steps - 1))
            
            # Scenario Pathing
            if self.scenario == "sideways":
                price = base_price + (math.sin(i * 0.1) * 200.0)
                iv = 0.5 + (math.cos(i * 0.05) * 0.05)
            elif self.scenario == "flash_crash":
                if t_ratio > 0.4 and t_ratio < 0.45:
                    price = base_price * (1.0 - ((t_ratio - 0.4) / 0.05) * 0.2) # 20% drop
                    iv = 1.2
                elif t_ratio >= 0.45:
                    price = base_price * 0.8 + ((t_ratio - 0.45) / 0.55) * (base_price * 0.15) # Recover partially
                    iv = 0.8 - (t_ratio - 0.45) * 0.3
                else:
                    price = base_price + math.sin(i * 0.1) * 100.0
                    iv = 0.5
            elif self.scenario == "slow_bleed":
                price = base_price * (1.0 - (t_ratio * 0.3)) # 30% drop over time
                iv = 0.6 + t_ratio * 0.2
            elif self.scenario == "high_iv":
                price = base_price + math.sin(i * 0.2) * 500.0
                iv = 1.5
            elif self.scenario == "low_iv":
                price = base_price + math.sin(i * 0.02) * 50.0
                iv = 0.2
            elif self.scenario == "gap_open":
                if t_ratio > 0.5:
                    price = base_price * 1.1 # 10% gap up instantly
                    iv = 0.8
                else:
                    price = base_price
                    iv = 0.5
            elif self.scenario == "whipsaw":
                price = base_price + math.sin(i * 0.5) * 1500.0
                iv = 1.0
            else:
                price = base_price
                iv = 0.5
                
            # Mocking simplistic Greeks (Delta changes based on price movement vs base)
            # A simplistic delta behavior for testing
            mock_call_delta = 0.5 + ((price - base_price) / base_price)
            mock_call_delta = max(0.01, min(0.99, mock_call_delta))
            
            yield ReplayMarketData(
                timestamp=current_time + (i * 60.0), # 1 minute steps
                spot_price=price,
                mark_price=price,
                call_greeks={"delta": mock_call_delta, "gamma": 0.05, "vega": 10.0, "theta": -5.0},
                put_greeks={"delta": mock_call_delta - 1.0, "gamma": 0.05, "vega": 10.0, "theta": -5.0},
                iv=iv,
                volume=100.0 + math.sin(i) * 50.0,
                funding=0.0001,
                open_interest=1000.0,
                metadata={"scenario": self.scenario, "step": i}
            )

class JsonReplayProvider(ReplayDataProvider):
    """
    Reads historical market data from local JSON files.
    Preferred validation source once Delta Exchange history is available.
    """
    def __init__(self, file_path: str):
        self.file_path = file_path
        
    def __iter__(self) -> Iterator[ReplayMarketData]:
        with open(self.file_path, 'r') as f:
            data = json.load(f)
            for row in data:
                yield ReplayMarketData(
                    timestamp=row.get("timestamp", 0.0),
                    spot_price=row.get("spot_price", 0.0),
                    mark_price=row.get("mark_price", 0.0),
                    call_greeks=row.get("call_greeks", {"delta": 0.0}),
                    put_greeks=row.get("put_greeks", {"delta": 0.0}),
                    iv=row.get("iv", 0.0),
                    volume=row.get("volume", 0.0),
                    funding=row.get("funding", 0.0),
                    open_interest=row.get("open_interest", 0.0),
                    metadata=row.get("metadata", {})
                )
