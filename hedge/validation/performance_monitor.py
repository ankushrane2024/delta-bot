import logging
import time
from typing import Dict, Any, List
import statistics

logger = logging.getLogger("system")

class PerformanceMonitor:
    """
    Tracks and produces rolling statistics for pipeline latency.
    """
    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self.latencies: List[float] = []
        self.max_latency = 0.0

    def record_tick_latency(self, latency_ms: float):
        self.latencies.append(latency_ms)
        if latency_ms > self.max_latency:
            self.max_latency = latency_ms
            
        if len(self.latencies) > self.window_size:
            self.latencies.pop(0)

    def get_statistics(self) -> Dict[str, float]:
        if not self.latencies:
            return {
                "average_latency_ms": 0.0,
                "max_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
                "p99_latency_ms": 0.0
            }
            
        sorted_lats = sorted(self.latencies)
        p95_idx = int(len(sorted_lats) * 0.95)
        p99_idx = int(len(sorted_lats) * 0.99)
        
        return {
            "average_latency_ms": statistics.mean(self.latencies),
            "max_latency_ms": self.max_latency,
            "p95_latency_ms": sorted_lats[p95_idx] if p95_idx < len(sorted_lats) else sorted_lats[-1],
            "p99_latency_ms": sorted_lats[p99_idx] if p99_idx < len(sorted_lats) else sorted_lats[-1]
        }
