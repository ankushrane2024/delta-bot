import logging
from typing import Dict, Any, List, Tuple, Optional
import math

from hedge.models.decision import HedgeDecision, HedgeAction
from hedge.models.position import StressFusionBreakdown
from hedge.context.position_context import PositionContext
from config import (
    DECISION_EMA_ALPHA,
    HEDGE_THRESHOLD_PREPARE,
    HEDGE_THRESHOLD_PARTIAL,
    HEDGE_THRESHOLD_FULL,
    HEDGE_THRESHOLD_EMERGENCY,
    UNHEDGE_THRESHOLD_BUFFER,
    PARTIAL_HEDGE_RATIO,
    FULL_HEDGE_RATIO
)

logger = logging.getLogger(__name__)

class DecisionEngine:
    def __init__(self):
        self._warnings: List[str] = []
        self._ema_stress: Optional[float] = None
        self._last_ema_time: Optional[float] = None

    def _determine_dominant_cluster(self, breakdown: StressFusionBreakdown) -> Tuple[str, str, str]:
        clusters = {
            "Directional": breakdown.directional_cluster,
            "Volatility": breakdown.volatility_cluster,
            "Financial": breakdown.financial_cluster,
            "Context": breakdown.context_cluster
        }
        
        highest_score = -1.0
        dominant_cluster_name = "Unknown"
        dominant_factor = "Unknown"
        primary_reason = "No Danger"
        
        for name, cluster in clusters.items():
            if cluster.score > highest_score:
                highest_score = cluster.score
                dominant_cluster_name = name
                dominant_factor = cluster.dominant_factor
                primary_reason = cluster.primary_reason
                
        return dominant_cluster_name, dominant_factor, primary_reason

    def evaluate(self, fused_score: float, breakdown: StressFusionBreakdown, 
                 context: PositionContext, current_hedge_ratio: float, current_time: float = 0.0,
                 regime_result=None) -> HedgeDecision:
                 
        if context.total_lots == 0:
            self._ema_stress = 0.0
            self._last_ema_time = current_time
            return HedgeDecision(
                action=HedgeAction.HOLD,
                hedge_ratio=0.0,
                urgency=0.0,
                reason="No active option positions.",
                dominant_cluster="None", dominant_factor="None",
                ema_stress=0.0,
                debug_information={"total_lots": 0}
            )

        if self._ema_stress is None:
            self._ema_stress = fused_score
            self._last_ema_time = current_time
        else:
            dt = max(0.0, current_time - self._last_ema_time)
            # Tau of 60 seconds. Decay constant.
            tau = 60.0
            alpha = 1.0 - math.exp(-dt / tau)
            self._ema_stress = (alpha * fused_score) + ((1.0 - alpha) * self._ema_stress)
            self._last_ema_time = current_time
            
        ema = self._ema_stress
        buffer = UNHEDGE_THRESHOLD_BUFFER
        
        # ===== HARD GATE 1: PROFIT OVERRIDE =====
        # If combined PnL is in profit, NO HEDGE allowed (block entry, keep existing)
        call_pnl = float(context.metadata.get('call_pnl_usd', 0))
        put_pnl = float(context.metadata.get('put_pnl_usd', 0))
        combined_pnl = call_pnl + put_pnl
        
        if combined_pnl >= 0.0:
            # Trade is in profit — NEVER hedge
            if current_hedge_ratio > 0:
                # If we have an existing hedge and we're now profitable, dehedge
                return HedgeDecision(
                    action=HedgeAction.DEHEDGE,
                    hedge_ratio=0.0,
                    urgency=0.0,
                    reason="Trade in Profit — Removing hedge",
                    dominant_cluster="None", dominant_factor="Combined PnL > 0",
                    ema_stress=ema,
                    debug_information={"msg": "Dehedge: trade turned profitable", "combined_pnl": combined_pnl}
                )
            return HedgeDecision(
                action=HedgeAction.MONITOR,
                hedge_ratio=0.0,
                urgency=0.0,
                reason="Profit Override (Standby)",
                dominant_cluster="None", dominant_factor="Combined PnL > 0",
                ema_stress=ema,
                debug_information={"msg": "Forced standby due to overall trade profitability", "combined_pnl": combined_pnl}
            )
        
        # ===== HARD GATE 2: MINIMUM LOSS THRESHOLD =====
        # Options must be losing at least 20% of premium collected before any hedge is considered
        total_premium = float(context.metadata.get('total_entry_premium', 0.0))
        loss_pct = 0.0
        if total_premium > 0:
            loss_pct = (abs(combined_pnl) / total_premium) * 100.0
        
        if loss_pct < 20.0 and current_hedge_ratio == 0:
            # Loss is less than 20% of premium — too early to hedge, might reverse
            return HedgeDecision(
                action=HedgeAction.MONITOR,
                hedge_ratio=0.0,
                urgency=0.0,
                reason=f"Loss {loss_pct:.1f}% < 20% threshold — Waiting for confirmation",
                dominant_cluster="None", dominant_factor="Loss too small",
                ema_stress=ema,
                debug_information={"loss_pct": loss_pct, "combined_pnl": combined_pnl, "total_premium": total_premium}
            )
        
        # ===== HARD GATE 3: CONFIRMED TREND REQUIRED =====
        # Only hedge if the market regime is CONFIRMED_TREND or ACCELERATION (not early/weak)
        trend_confirmed = False
        if regime_result:
            from hedge.models.enums import MarketRegime
            current_regime = getattr(regime_result, 'current_regime', None)
            if current_regime in (MarketRegime.CONFIRMED_TREND, MarketRegime.ACCELERATION):
                trend_confirmed = True
        
        if not trend_confirmed and current_hedge_ratio == 0:
            # Trend is not confirmed — do not enter hedge
            regime_name = getattr(getattr(regime_result, 'current_regime', None), 'name', 'UNKNOWN') if regime_result else 'UNKNOWN'
            return HedgeDecision(
                action=HedgeAction.MONITOR,
                hedge_ratio=0.0,
                urgency=0.0,
                reason=f"Trend not confirmed ({regime_name}) — Waiting",
                dominant_cluster="None", dominant_factor="Regime not confirmed",
                ema_stress=ema,
                debug_information={"regime": regime_name, "loss_pct": loss_pct}
            )
        
        # ===== PASSED ALL GATES — Apply stress-based hedge scaling =====
        action = HedgeAction.NO_ACTION
        target_ratio = current_hedge_ratio
        
        # State transitions with Hysteresis
        if current_hedge_ratio == 0.0:
            # Scaling up
            if ema >= HEDGE_THRESHOLD_EMERGENCY:
                action = HedgeAction.EMERGENCY_HEDGE
                target_ratio = FULL_HEDGE_RATIO
            elif ema >= HEDGE_THRESHOLD_FULL:
                action = HedgeAction.FULL_HEDGE
                target_ratio = FULL_HEDGE_RATIO
            elif ema >= HEDGE_THRESHOLD_PARTIAL:
                action = HedgeAction.PARTIAL_HEDGE
                target_ratio = PARTIAL_HEDGE_RATIO
            elif ema >= HEDGE_THRESHOLD_PREPARE:
                action = HedgeAction.PREPARE_HEDGE
                target_ratio = 0.0
            else:
                action = HedgeAction.MONITOR
                target_ratio = 0.0
        else:
            # We are already hedged, scaling down or up requires hysteresis
            if ema >= HEDGE_THRESHOLD_EMERGENCY:
                action = HedgeAction.EMERGENCY_HEDGE
                target_ratio = FULL_HEDGE_RATIO
            elif ema >= HEDGE_THRESHOLD_FULL:
                if current_hedge_ratio < FULL_HEDGE_RATIO:
                    action = HedgeAction.FULL_HEDGE
                    target_ratio = FULL_HEDGE_RATIO
                else:
                    action = HedgeAction.MONITOR
                    target_ratio = current_hedge_ratio
            elif ema >= HEDGE_THRESHOLD_PARTIAL:
                if current_hedge_ratio < PARTIAL_HEDGE_RATIO:
                    action = HedgeAction.PARTIAL_HEDGE
                    target_ratio = PARTIAL_HEDGE_RATIO
                elif current_hedge_ratio >= FULL_HEDGE_RATIO and ema < (HEDGE_THRESHOLD_FULL - buffer):
                    action = HedgeAction.PARTIAL_HEDGE
                    target_ratio = PARTIAL_HEDGE_RATIO
                else:
                    action = HedgeAction.MONITOR
                    target_ratio = current_hedge_ratio
            else:
                # Below partial
                if ema < (HEDGE_THRESHOLD_PARTIAL - buffer):
                    action = HedgeAction.DEHEDGE
                    target_ratio = 0.0
                elif current_hedge_ratio > 0.0:
                    action = HedgeAction.MONITOR
                    target_ratio = current_hedge_ratio
                
        dominant_cluster_name, dominant_factor, primary_reason = self._determine_dominant_cluster(breakdown)
        
        urgency = min(1.0, max(0.0, ema / 100.0))
        
        decision = HedgeDecision(
            action=action,
            urgency=urgency,
            hedge_ratio=target_ratio,
            reason=primary_reason,
            dominant_cluster=dominant_cluster_name,
            dominant_factor=dominant_factor,
            ema_stress=ema,
            raw_stress=fused_score
        )
        
        return decision

    def reset_state(self):
        self._ema_stress = None
