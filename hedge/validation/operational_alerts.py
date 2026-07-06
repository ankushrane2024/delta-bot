import logging
from typing import Dict, Any, List

logger = logging.getLogger("system")

class OperationalAlerts:
    """
    Generates read-only operational alerts.
    """
    def __init__(self):
        self.active_alerts: List[str] = []

    def evaluate(self, perf_stats: Dict[str, float], res_warnings: List[str], rel_stats: Dict[str, Any]):
        self.active_alerts.clear()
        
        # Latency thresholds
        if perf_stats.get("average_latency_ms", 0) > 1000:
            self.active_alerts.append(f"High Average Latency: {perf_stats['average_latency_ms']} ms")
        if perf_stats.get("p99_latency_ms", 0) > 3000:
            self.active_alerts.append(f"High P99 Latency: {perf_stats['p99_latency_ms']} ms")
            
        # Resource leaks
        for w in res_warnings:
            self.active_alerts.append(w)
            
        # Provider instability
        if rel_stats.get("ws_reconnects", 0) > 10:
            self.active_alerts.append(f"Excessive WS Reconnects: {rel_stats['ws_reconnects']}")
        if rel_stats.get("circuit_breaker_trips", 0) > 3:
            self.active_alerts.append(f"Frequent Circuit Breaker Trips: {rel_stats['circuit_breaker_trips']}")
            
        # Emit alerts
        for alert in self.active_alerts:
            logger.warning(f"OPERATIONAL ALERT: {alert}")

    def get_active_alerts(self) -> List[str]:
        return self.active_alerts.copy()
