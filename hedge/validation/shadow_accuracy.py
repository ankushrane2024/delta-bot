import logging
from typing import Dict, Any

from hedge.models.tick import TickResult

logger = logging.getLogger("system")

class ShadowAccuracyAnalyzer:
    """
    Generates quality metrics for simulated hedges vs expected math.
    Strictly read-only. No trading decisions are modified.
    """
    def __init__(self):
        self.stats = {
            "total_simulated_hedges": 0,
            "perfect_efficiency_count": 0,
            "average_slippage_bps": 0.0,
            "slippage_sum": 0.0
        }

    def evaluate_tick(self, tick: TickResult):
        if not tick.hedge_plan or not tick.portfolio_snapshot:
            return
            
        if tick.hedge_plan.action == "HOLD":
            return
            
        # We only evaluate ticks where a hedge was commanded
        # In a shadow environment, execution_summary should contain the simulated fills
        self.stats["total_simulated_hedges"] += 1
        
        expected_qty = tick.hedge_plan.quantity
        
        # Calculate simulated slippage if filled
        if tick.execution_summary and "filled_quantity" in tick.execution_summary:
            actual_qty = tick.execution_summary["filled_quantity"]
            if abs(expected_qty - actual_qty) < 1e-6:
                self.stats["perfect_efficiency_count"] += 1
                
            # If we had a requested price vs average fill price
            if "requested_price" in tick.execution_summary and "average_fill_price" in tick.execution_summary:
                req = tick.execution_summary["requested_price"]
                fill = tick.execution_summary["average_fill_price"]
                if req and fill and req > 0:
                    slippage = abs(req - fill) / req * 10000 # in bps
                    self.stats["slippage_sum"] += slippage
                    self.stats["average_slippage_bps"] = self.stats["slippage_sum"] / self.stats["total_simulated_hedges"]

    def get_statistics(self) -> Dict[str, Any]:
        return self.stats.copy()
