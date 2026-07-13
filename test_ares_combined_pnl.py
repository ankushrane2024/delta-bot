import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from hedge.engines.position_risk_engine import PositionRiskEngine
from hedge.context.position_context import PositionContext

def test_combined_pnl():
    engine = PositionRiskEngine()
    
    # 1. Trade is net losing (Call loss > Put profit)
    print("--- Test 1: Trade is net losing ---")
    ctx_loss = PositionContext()
    ctx_loss.call_leg_pnl = -400.0
    ctx_loss.put_leg_pnl = +200.0
    
    score_loss = engine._compute_pnl_factor(ctx_loss, is_call=True)
    print(f"Call PnL: -400, Put PnL: +200 => Combined: -200")
    print(f"Call Stress Score: {score_loss:.2f}")
    
    # 2. Trade is net profitable (Put profit > Call loss)
    print("\n--- Test 2: Trade is net profitable ---")
    ctx_profit = PositionContext()
    ctx_profit.call_leg_pnl = -400.0
    ctx_profit.put_leg_pnl = +600.0
    
    score_profit = engine._compute_pnl_factor(ctx_profit, is_call=True)
    print(f"Call PnL: -400, Put PnL: +600 => Combined: +200")
    print(f"Call Stress Score: {score_profit:.2f}")
    
    if score_profit == (score_loss * 0.5):
        print("\n✅ SUCCESS: ARES correctly halved the stress score because the combined trade is profitable!")
    else:
        print("\n❌ FAILED: Score was not halved.")

if __name__ == "__main__":
    test_combined_pnl()
