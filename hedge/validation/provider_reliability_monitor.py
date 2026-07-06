import logging
from typing import Dict, Any

from hedge.models.tick import TickResult

logger = logging.getLogger("system")

class ProviderReliabilityMonitor:
    """
    Evaluates exchange connectivity stability by aggregating provider health signals.
    """
    def __init__(self):
        self.stats = {
            "ws_reconnects": 0,
            "rest_failures": 0,
            "heartbeat_failures": 0,
            "sequence_gaps": 0,
            "circuit_breaker_trips": 0,
            "recovery_attempts": 0,
            "recovery_successes": 0
        }
        self.last_status = "GREEN"

    def record_tick(self, tick: TickResult):
        # We infer some reliability from TickResult.provider_health and CB logic
        current_status = tick.provider_health
        
        if current_status == "RED" and self.last_status != "RED":
            self.stats["circuit_breaker_trips"] += 1
            
        if tick.execution_summary:
            errors = tick.execution_summary.get("errors", [])
            for err in errors:
                if "gap" in err.lower():
                    self.stats["sequence_gaps"] += 1
                elif "rest" in err.lower():
                    self.stats["rest_failures"] += 1
                elif "ws" in err.lower():
                    self.stats["ws_reconnects"] += 1
                elif "heartbeat" in err.lower():
                    self.stats["heartbeat_failures"] += 1

        self.last_status = current_status

    def record_recovery(self, success: bool):
        self.stats["recovery_attempts"] += 1
        if success:
            self.stats["recovery_successes"] += 1

    def get_statistics(self) -> Dict[str, Any]:
        return self.stats.copy()
