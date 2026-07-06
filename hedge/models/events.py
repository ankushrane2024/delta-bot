from dataclasses import dataclass
from typing import Any
from .execution import ExecutionOrder

@dataclass
class ExecutionEvent:
    order: ExecutionOrder
    timestamp: str

@dataclass
class OrderSubmitted(ExecutionEvent):
    pass

@dataclass
class OrderAcknowledged(ExecutionEvent):
    pass

@dataclass
class OrderPartiallyFilled(ExecutionEvent):
    filled_amount: float
    price: float

@dataclass
class OrderFilled(ExecutionEvent):
    pass

@dataclass
class OrderCancelled(ExecutionEvent):
    reason: str

@dataclass
class OrderRejected(ExecutionEvent):
    reason: str

@dataclass
class PortfolioReconciled(ExecutionEvent):
    diff_reason: str

@dataclass
class ManualPositionDetected(ExecutionEvent):
    position_diff: float
    price_diff: float

@dataclass
class RecoveryCompleted(ExecutionEvent):
    pass

import threading

class EventBus:
    """Synchronous event bus with thread safety."""
    def __init__(self):
        self._subscribers = {}
        self._lock = threading.RLock()
        
    def subscribe(self, event_type: type, handler: callable):
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            if handler not in self._subscribers[event_type]:
                self._subscribers[event_type].append(handler)
        
    def publish(self, event: Any):
        event_type = type(event)
        
        # Copy under lock to prevent iteration issues if modified during handling
        with self._lock:
            handlers = list(self._subscribers.get(event_type, []))
            
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                # Log but do not crash the engine
                import logging
                logging.getLogger("ARES.EventBus").error(f"Error in event handler for {event_type.__name__}: {e}", exc_info=True)

# Global event bus instance for the engine

