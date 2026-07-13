import logging
logging.basicConfig(level=logging.INFO)

from hedge.engines.decision_engine import DecisionEngine
from hedge.context.position_context import PositionContext
from hedge.models.position import StressFusionBreakdown
from hedge.models.decision import HedgeAction

def test_reversal_exit():
    engine = DecisionEngine()
    
    # 1. Start unhedged, PE is losing
    context = PositionContext(total_lots=500)
    context.metadata['call_pnl_usd'] = 10.0
    context.metadata['put_pnl_usd'] = -60.0
    context.metadata['total_entry_premium'] = 200.0
    
    breakdown = StressFusionBreakdown()
    breakdown.directional_cluster.score = 85.0
    
    from hedge.models.enums import MarketRegime
    class DummyRegime:
        current_regime = MarketRegime.ACCELERATION
        
    # Fused score > 80
    decision = engine.evaluate(85.0, breakdown, context, current_hedge_ratio=0.0, regime_result=DummyRegime())
    print(f"Initial Hedge Decision: {decision.action.name}")
    assert decision.action == HedgeAction.FULL_HEDGE
    
    # Check that start bleeding pnl was recorded
    print(f"Recorded Start PnL: {engine._hedge_start_bleeding_pnl}")
    assert engine._hedge_start_bleeding_pnl == -60.0
    
    # 2. Market Reverses slightly
    # PE recovers to -10, Hedge loses 10. CE loses its profit and goes to 0.
    context.metadata['call_pnl_usd'] = 0.0
    context.metadata['put_pnl_usd'] = -10.0
    context.metadata['hedge_pnl_usd'] = -10.0
    
    # Evaluate with current_hedge_ratio > 0
    decision2 = engine.evaluate(85.0, breakdown, context, current_hedge_ratio=0.5)
    print(f"Reversal Decision: {decision2.action.name} - Reason: {decision2.reason}")
    assert decision2.action == HedgeAction.DEHEDGE
    assert "Reversal Exit" in decision2.reason
    
    print("Test Passed: Reversal Exit successfully triggered!")

if __name__ == "__main__":
    test_reversal_exit()
