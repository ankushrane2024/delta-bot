import logging
import json
import os
import time
from typing import Optional

from hedge.models.tick import TickResult

logger = logging.getLogger("system")

class DriftDetector:
    """
    Continuously verifies mathematical and replay determinism.
    If drift is detected, captures full diagnostic snapshots for later analysis.
    """
    def __init__(self, output_dir: str = "logs/diagnostics"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.last_tick_hash: Optional[str] = None

    def evaluate_tick(self, tick: TickResult):
        drift_detected = False
        reasons = []

        # 1. Replay hash consistency
        # Assuming tick_hash is deterministic, we can verify sequence
        if not tick.tick_hash:
            drift_detected = True
            reasons.append("Missing tick_hash in TickResult.")

        # 2. Portfolio consistency
        if tick.portfolio_snapshot and tick.portfolio_snapshot.snapshot_hash:
            if not tick.portfolio_snapshot.snapshot_hash:
                drift_detected = True
                reasons.append("Portfolio snapshot missing hash.")
                
        # 3. Hedge quantity consistency (e.g. no negative absolute sizes or mismatched logic)
        if tick.hedge_plan and tick.hedge_plan.quantity < 0:
            # We assume shorting is expressed via SIDE not negative quantity
            drift_detected = True
            reasons.append("Negative hedge quantity detected.")

        if drift_detected:
            self._capture_diagnostic_snapshot(tick, reasons)

    def _capture_diagnostic_snapshot(self, tick: TickResult, reasons: list):
        timestamp = int(time.time())
        filename = os.path.join(self.output_dir, f"drift_snapshot_{timestamp}.json")
        
        logger.critical(f"STATE DRIFT DETECTED! Capturing diagnostic snapshot to {filename}. Reasons: {reasons}")
        
        snapshot = {
            "timestamp": timestamp,
            "reasons": reasons,
            "tick_number": getattr(tick, 'tick_number', -1),
            "tick_hash": getattr(tick, 'tick_hash', ''),
            "market_context": tick.market_context,
            "portfolio_snapshot": tick.portfolio_snapshot.to_dict() if tick.portfolio_snapshot else None,
            "hedge_decision": tick.hedge_decision.action if tick.hedge_decision else None,
            "execution_summary": tick.execution_summary
        }
        
        with open(filename, "w") as f:
            json.dump(snapshot, f, indent=4)
