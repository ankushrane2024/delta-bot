from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import time

class Clock(ABC):
    """Abstract time source for deterministic replay support."""
    @abstractmethod
    def now(self) -> float:
        pass
        
    @abstractmethod
    def now_iso(self) -> str:
        pass

class SystemClock(Clock):
    def now(self) -> float:
        return time.time()
        
    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

class ReplayClock(Clock):
    def __init__(self, start_time: float = 0.0):
        self._current_time = start_time
        
    def set_time(self, timestamp: float):
        self._current_time = timestamp
        
    def tick(self, seconds: float = 1.0):
        self._current_time += seconds

    def now(self) -> float:
        return self._current_time
        
    def now_iso(self) -> str:
        return datetime.fromtimestamp(self._current_time, tz=timezone.utc).isoformat()


class ExecutionStore(ABC):
    """
    Interface for idempotency and state persistence.
    Future implementations can be SQLite, Redis, PostgreSQL.
    """
    @abstractmethod
    def save_order(self, order: Any) -> None:
        pass
        
    @abstractmethod
    def get_order(self, order_id: str) -> Optional[Any]:
        pass
        
    @abstractmethod
    def get_order_by_plan(self, plan_id: str) -> Optional[Any]:
        pass
        
    @abstractmethod
    def get_active_orders(self) -> List[Any]:
        pass

class InMemoryExecutionStore(ExecutionStore):
    def __init__(self):
        self._orders_by_id = {}
        self._orders_by_plan = {}
        
    def save_order(self, order: Any) -> None:
        self._orders_by_id[order.client_order_id] = order
        if order.plan_id:
            self._orders_by_plan[order.plan_id] = order
            
    def get_order(self, order_id: str) -> Optional[Any]:
        return self._orders_by_id.get(order_id)
        
    def get_order_by_plan(self, plan_id: str) -> Optional[Any]:
        return self._orders_by_plan.get(plan_id)
        
    def get_active_orders(self) -> List[Any]:
        # Active means not terminal state
        terminal_states = ["FILLED", "CANCELLED", "REJECTED", "FAILED", "EXPIRED"]
        return [
            order for order in self._orders_by_id.values() 
            if getattr(order.state, 'name', str(order.state)) not in terminal_states
        ]

class AbstractMarketDataProvider(ABC):
    """
    Interface for providing market data to the ARES pipeline.
    """
    @abstractmethod
    def get_latest_data(self) -> Any:
        pass
