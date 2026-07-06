import json
import os
from dataclasses import asdict
from enum import Enum
from hedge.models.events import (
    EventBus, OrderSubmitted, OrderAcknowledged, OrderPartiallyFilled,
    OrderFilled, OrderCancelled, OrderRejected, ManualPositionDetected,
    PortfolioReconciled, RecoveryCompleted
)

class EventEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Enum):
            return obj.name
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        return str(obj)

class AuditLogger:
    def __init__(self, event_bus: EventBus, log_file: str = "audit.ndjson"):
        self.event_bus = event_bus
        self.log_file = log_file
        self._subscribe_all()
        
    def _subscribe_all(self):
        events = [
            OrderSubmitted, OrderAcknowledged, OrderPartiallyFilled,
            OrderFilled, OrderCancelled, OrderRejected, ManualPositionDetected,
            PortfolioReconciled, RecoveryCompleted
        ]
        for event_type in events:
            self.event_bus.subscribe(event_type, self._log_event)
            
    def _log_event(self, event):
        try:
            event_dict = {
                "event_type": event.__class__.__name__,
                "payload": event.__dict__
            }
            with open(self.log_file, "a") as f:
                f.write(json.dumps(event_dict, cls=EventEncoder) + "\n")
        except Exception:
            pass
