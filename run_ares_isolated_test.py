import os
import sys
import time
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hedge.engines.position_risk_engine import PositionRiskEngine
from hedge.engines.sizing_engine import HedgeSizingEngine
from hedge.models.trend import TrendResult
from hedge.models.enums import TrendDirection, MarketRegime
from hedge.models.regime import MarketRegimeResult
from hedge.context.position_context import PositionContext
from hedge.models.decision import HedgeDecision, HedgeAction

def run_report():
    print("# ARES Mathematical Validation Report (Crash Scenario)")
    print("## Overview")
    print("This simulation runs the exact mathematical logic of `PositionRiskEngine` and `HedgeSizingEngine` across a simulated market crash from 50,000 to 45,000 for a 20-lot short strangle option position.")
    
    print("\n## Simulation Results")
    print("| BTC Price | Call Delta | Put Delta | PnL Factor | Overall Risk | ARES Action | Target Hedge (BTC) | Contracts |")
    print("|-----------|------------|-----------|------------|--------------|-------------|--------------------|-----------|")
    
    risk_engine = PositionRiskEngine()
    sizing_engine = HedgeSizingEngine()
    
    from unittest.mock import Mock
    trend = Mock()
    trend.trend_direction = TrendDirection.SHORT
    trend.trend_strength = 80.0
    trend.trend_confidence = 90.0
    trend.continuation_probability = 85.0
    
    regime = Mock()
    regime.current_regime = MarketRegime.ACCELERATION
    regime.confidence = 95.0
    
    for tick in range(11):
        price = 50000.0 - (tick * 500)
        
        call_delta = max(0.0, 0.5 - (tick * 0.05))
        put_delta = max(-1.0, -0.5 - (tick * 0.05))
        
        # Fake a heavy loss on the PUT leg
        put_loss = - (50000.0 - price) * 0.5 * 20 * 0.001
        
        ctx = PositionContext()
        ctx.position_size = 20000.0
        ctx.wallet_balance = 100000.0
        ctx.total_lots = 20
        ctx.options_delta = -(call_delta + put_delta) * 10 * 0.001
        ctx.options_pnl = put_loss
        ctx.futures_price = price
        ctx.short_call_strike = 60000.0
        ctx.short_put_strike = 40000.0
        ctx.call_delta = call_delta
        ctx.put_delta = put_delta
        ctx.call_gamma = 0.05
        ctx.put_gamma = 0.05
        ctx.call_vega = 10.0
        ctx.put_vega = 10.0
        ctx.call_mark_price = max(10.0, 500.0 - (50000.0 - price) * 0.2)
        ctx.put_mark_price = 500.0 + (50000.0 - price) * 0.5
        ctx.call_leg_pnl = 0.0
        ctx.put_leg_pnl = put_loss
        ctx.call_iv = 0.6
        ctx.put_iv = 0.6 + (tick * 0.02)
        
        ctx.metadata["put_entry_price"] = 500.0
        ctx.metadata["call_entry_price"] = 500.0
        ctx.metadata["put_entry_iv"] = 0.6
        ctx.metadata["call_entry_iv"] = 0.6
        
        risk = risk_engine.evaluate(regime, trend, ctx)
        
        action = HedgeAction.PARTIAL_HEDGE if risk.overall_risk_score > 70 else HedgeAction.MONITOR
        decision = HedgeDecision(action=action, hedge_ratio=0.3 if action == HedgeAction.PARTIAL_HEDGE else 0.0, reason="Risk threshold exceeded", urgency="HIGH", dominant_cluster="PRICE_ACTION", dominant_factor="TREND_STRENGTH")
        
        size = sizing_engine.evaluate(decision, ctx, current_hedge_qty=0.0)
        
        # PNL factor for debug printing
        pnl_f = risk.debug_information["put_stress_breakdown"].pnl_factor if "put_stress_breakdown" in risk.debug_information else 0.0
        
        contracts = abs(size.hedge_quantity)
        
        print(f"| {price:9.1f} | {call_delta:10.2f} | {put_delta:9.2f} | {pnl_f:10.2f} | {risk.overall_risk_score:12.2f} | {action.name:11} | {size.target_delta:18.4f} | {contracts:9.0f} |")

if __name__ == "__main__":
    run_report()
