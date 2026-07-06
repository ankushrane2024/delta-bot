import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from hedge.models.decision import HedgeDecision, HedgeAction
from hedge.context.position_context import PositionContext
from hedge.models.hedge import HedgePlan
from hedge.models.sizing import HedgeSizingResult

logger = logging.getLogger(__name__)

import hashlib

class HedgeManager:
    def __init__(self):
        self._warnings: List[str] = []

    def evaluate(self, decision: HedgeDecision, sizing: HedgeSizingResult,
                 context: PositionContext, existing_hedge_qty: float,
                 pending_orders: List[Dict[str, Any]],
                 tick_number: int = 0, portfolio_hash: str = "") -> Optional[HedgePlan]:
        
        self._warnings.clear()
        
        # 1. No action required
        if decision.action in (HedgeAction.NO_ACTION, HedgeAction.MONITOR, HedgeAction.PREPARE_HEDGE):
            return None
            
        # 2. Check duplicate / pending orders
        # If there are active pending orders, we should not send a new HedgePlan immediately
        # unless it's an EMERGENCY_HEDGE overriding a normal order.
        if pending_orders:
            if decision.action != HedgeAction.EMERGENCY_HEDGE:
                self._warnings.append(f"Pending orders exist ({len(pending_orders)}). Halting execution to prevent duplicates.")
                return None
            else:
                self._warnings.append("Emergency Hedge triggered. Bypassing pending order checks.")
                # We would normally cancel pending orders here, but ExecutionEngine handles order replacement/cancellation.
                
        # 3. Check if sizing is zero (already hedged)
        if sizing.additional_quantity == 0.0:
            return None
            
        # 4. Formulate Execution Priority
        priority = 1
        if decision.action == HedgeAction.EMERGENCY_HEDGE:
            priority = 10
        elif decision.action == HedgeAction.FULL_HEDGE:
            priority = 5
        elif decision.action == HedgeAction.DEHEDGE:
            priority = 2
            
        # 5. Formulate Execution Style
        # Usually MARKET to guarantee delta execution, but could be LIMIT if partial
        execution_style = "MARKET"
        if decision.action == HedgeAction.PARTIAL_HEDGE and decision.urgency < 0.6:
            execution_style = "LIMIT_POST_ONLY"

        # 6. Generate Deterministic ID
        id_str = f"{portfolio_hash}_{tick_number}_{decision.action.name}_{sizing.additional_quantity}"
        hedge_id = hashlib.sha256(id_str.encode()).hexdigest()[:16]

        plan = HedgePlan(
            hedge_id=hedge_id,
            action=decision.action.name,
            side=sizing.hedge_side,
            quantity=sizing.additional_quantity,
            execution_priority=priority,
            execution_style=execution_style,
            estimated_post_hedge_delta=sizing.estimated_post_hedge_delta,
            hedge_reason=decision.reason,
            urgency=decision.urgency,
            timestamp=time.time(),
            warnings=list(self._warnings) + sizing.warnings
        )
        
        return plan
