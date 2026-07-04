import math
import logging
from typing import List

from hedge.models.decision import HedgeDecision, HedgeAction
from hedge.context.position_context import PositionContext
from hedge.models.sizing import HedgeSizingResult
import config

logger = logging.getLogger(__name__)

class HedgeSizingEngine:
    def __init__(self):
        self._warnings: List[str] = []

    def _build_empty_result(self, decision: HedgeDecision, target_delta: float, 
                            current_hedge_qty: float, reason: str) -> HedgeSizingResult:
        return HedgeSizingResult(
            target_delta=target_delta,
            current_delta=0.0,
            delta_to_hedge=0.0,
            hedge_side="NONE",
            hedge_quantity=0.0,
            current_hedge_quantity=current_hedge_qty,
            additional_quantity=0.0,
            estimated_post_hedge_delta=0.0,
            hedge_reason=reason,
            confidence=0.0,
            warnings=list(self._warnings)
        )

    def evaluate(self, decision: HedgeDecision, context: PositionContext, 
                 current_hedge_qty: float) -> HedgeSizingResult:
        self._warnings.clear()

        # 2. Extract Config
        lot_to_btc = config.LOT_TO_BTC
        futures_contract_size = config.FUTURES_CONTRACT_SIZE_BTC
        min_qty = config.MIN_ORDER_QTY
        step_size = config.QTY_STEP_SIZE
        max_qty = config.MAX_ORDER_QTY
        
        if futures_contract_size <= 0:
            self._warnings.append("FUTURES_CONTRACT_SIZE_BTC is zero or negative.")
            return self._build_empty_result(decision, 0.0, current_hedge_qty, "Invalid futures contract size.")

        # 3. Calculate Options Delta
        # A short strangle means we sold calls and puts.
        # Net Options Delta = -1 * (Call Delta + Put Delta) * Lots * Lot Size
        # Ensure safe values
        call_delta = 0.0 if math.isnan(context.call_delta) else context.call_delta
        put_delta = 0.0 if math.isnan(context.put_delta) else context.put_delta
        
        lots_per_leg = max(1.0, context.total_lots / 2.0)
        
        # Total portfolio delta from options (in BTC)
        # Assuming call_delta is positive (+0.3) and put_delta is negative (-0.3) for long options
        # Since we are short both, we multiply by -1.
        net_options_delta_btc = -1.0 * (call_delta + put_delta) * lots_per_leg * lot_to_btc
        
        # Target delta to hedge is based on the hedge_ratio from DecisionEngine
        # If options delta is negative (e.g. -0.5 BTC), we need +0.5 BTC to hedge.
        # So target hedge delta = -1.0 * net_options_delta_btc * hedge_ratio
        target_delta_to_hedge_btc = -1.0 * net_options_delta_btc * decision.hedge_ratio
        
        # Current hedge delta
        current_hedge_delta_btc = current_hedge_qty * futures_contract_size
        
        # Remaining delta to hedge
        delta_shortfall_btc = target_delta_to_hedge_btc - current_hedge_delta_btc
        
        # If action is DEHEDGE, target delta is 0, so shortfall is -current_hedge_delta_btc
        if decision.action == HedgeAction.DEHEDGE:
            delta_shortfall_btc = -current_hedge_delta_btc
            target_delta_to_hedge_btc = 0.0
        elif decision.action in (HedgeAction.NO_ACTION, HedgeAction.MONITOR, HedgeAction.PREPARE_HEDGE):
            # No action, shortfall is 0
            delta_shortfall_btc = 0.0
            target_delta_to_hedge_btc = current_hedge_delta_btc # Target is whatever we have

        # Calculate required quantity in contracts
        raw_quantity = delta_shortfall_btc / futures_contract_size
        
        if math.isnan(raw_quantity) or math.isinf(raw_quantity):
            self._warnings.append("Raw quantity calculated to NaN or Inf.")
            return self._build_empty_result(decision, target_delta_to_hedge_btc, current_hedge_qty, "Math error in sizing.")

        # 4. Rounding and Exchange Constraints
        abs_qty = abs(raw_quantity)
        
        # Step size rounding
        if step_size > 0:
            abs_qty = round(abs_qty / step_size) * step_size
            
        if abs_qty < min_qty:
            abs_qty = 0.0
            
        if abs_qty > max_qty:
            self._warnings.append(f"Calculated quantity {abs_qty} exceeds MAX_ORDER_QTY {max_qty}. Clamping.")
            abs_qty = max_qty
            
        # Determine additional quantity and side
        if abs_qty == 0:
            hedge_side = "NONE"
            additional_quantity = 0.0
        else:
            if raw_quantity > 0:
                hedge_side = "BUY"
                additional_quantity = abs_qty
            else:
                hedge_side = "SELL"
                additional_quantity = abs_qty # Always positive, side defines direction

        if hedge_side == "SELL":
            target_quantity = current_hedge_qty - additional_quantity
        else:
            target_quantity = current_hedge_qty + additional_quantity
            
        estimated_post_hedge_delta = target_quantity * futures_contract_size
        
        return HedgeSizingResult(
            target_delta=target_delta_to_hedge_btc,
            current_delta=net_options_delta_btc,
            delta_to_hedge=delta_shortfall_btc,
            hedge_side=hedge_side,
            hedge_quantity=target_quantity,
            current_hedge_quantity=current_hedge_qty,
            additional_quantity=additional_quantity,
            estimated_post_hedge_delta=estimated_post_hedge_delta,
            hedge_reason=decision.reason,
            confidence=100.0,
            warnings=list(self._warnings)
        )
