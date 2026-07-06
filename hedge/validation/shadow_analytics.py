import logging
import threading
from typing import Dict, Any

from hedge.models.events import ExecutionEvent, OrderFilled
from hedge.models.tick import TickResult

logger = logging.getLogger(__name__)

class ShadowAnalytics:
    """
    In-memory view of active pipeline performance.
    Used by the read-only Dashboard API to serve live statistics.
    Never recalculates portfolio mathematics. Only aggregates existing values.
    """
    def __init__(self):
        self._lock = threading.RLock()
        
        self.live_stats = {
            "total_ticks": 0,
            "total_fills": 0,
            "average_latency_ms": 0.0,
            "emergency_hedge_count": 0,
            "circuit_breaker_hits": 0,
            "current_portfolio_delta": 0.0,
            "max_drawdown": 0.0,
            "daily_pnl": 0.0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "margin_utilization": 0.0
        }
        self.latency_sum = 0.0
        
    def get_live_stats(self) -> Dict[str, Any]:
        """Thread-safe access to live stats for the dashboard."""
        with self._lock:
            return self.live_stats.copy()

    def on_tick_result(self, tick: TickResult):
        with self._lock:
            self.live_stats["total_ticks"] += 1
            
            # Latency aggregator
            self.latency_sum += tick.pipeline_latency
            self.live_stats["average_latency_ms"] = (self.latency_sum / self.live_stats["total_ticks"]) * 1000.0
            
            if tick.hedge_decision and tick.hedge_decision.action.name == "EMERGENCY_HEDGE":
                self.live_stats["emergency_hedge_count"] += 1
                
            if tick.provider_health != "GREEN":
                self.live_stats["circuit_breaker_hits"] += 1
                
            if tick.portfolio_snapshot:
                # Do not recalculate - just read from synchronizer's snapshot
                snap = tick.portfolio_snapshot
                self.live_stats["current_portfolio_delta"] = snap.net_options_delta
                self.live_stats["daily_pnl"] = snap.realized_pnl + snap.unrealized_pnl # Naive mapping for now
                self.live_stats["realized_pnl"] = snap.realized_pnl
                self.live_stats["unrealized_pnl"] = snap.unrealized_pnl
                if snap.available_balance > 0:
                    self.live_stats["margin_utilization"] = snap.margin_used / snap.available_balance

    def on_execution_event(self, event: ExecutionEvent):
        if isinstance(event, OrderFilled):
            with self._lock:
                self.live_stats["total_fills"] += 1
