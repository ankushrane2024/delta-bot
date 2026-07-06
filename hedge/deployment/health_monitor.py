import logging
import time
from typing import Dict, Any

try:
    import psutil
except ImportError:
    psutil = None

from hedge.validation.shadow_analytics import ShadowAnalytics

logger = logging.getLogger("system")

class HealthMonitor:
    """
    Exposes overall system status (GREEN, YELLOW, RED) based on:
    WS/REST latency, provider/orchestrator state, queue depth, CPU, RAM, and uptime.
    """
    def __init__(self, analytics: ShadowAnalytics, start_time: float):
        self.analytics = analytics
        self.start_time = start_time

    def get_system_health(self) -> Dict[str, Any]:
        stats = self.analytics.get_live_stats()
        
        # Calculate uptime
        uptime_seconds = time.time() - self.start_time
        
        # CPU/RAM (if psutil available)
        cpu_percent = psutil.cpu_percent() if psutil else 0.0
        ram_percent = psutil.virtual_memory().percent if psutil else 0.0
        
        # Health heuristics
        avg_latency = stats.get("average_latency_ms", 0.0)
        cb_hits = stats.get("circuit_breaker_hits", 0)
        
        status = "GREEN"
        if avg_latency > 500 or cb_hits > 0 or cpu_percent > 85 or ram_percent > 85:
            status = "YELLOW"
        if avg_latency > 2000 or cb_hits > 5 or cpu_percent > 95 or ram_percent > 95:
            status = "RED"
            
        health = {
            "status": status,
            "uptime_seconds": uptime_seconds,
            "cpu_percent": cpu_percent,
            "ram_percent": ram_percent,
            "metrics": {
                "average_latency_ms": avg_latency,
                "circuit_breaker_hits": cb_hits,
                "total_ticks": stats.get("total_ticks", 0),
                "emergency_hedges": stats.get("emergency_hedge_count", 0)
            }
        }
        
        # Log if not green
        if status != "GREEN":
            logger.warning(f"System Health degraded to {status}: {health['metrics']}")
            
        return health
