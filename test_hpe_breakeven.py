import logging
from local_hpe_engine import HedgeProtectionEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_breakeven_sl():
    print("="*60)
    print("TEST: TRAILING BREAKEVEN STOP LOSS")
    print("="*60)
    
    engine = HedgeProtectionEngine()
    
    # 1. Trigger Tier 1 (SELL at 64000)
    engine.evaluate(-11.5, -500, 1000, 0.10, 64000, 'SELL', 30, 'BREAKDOWN_DOWN')
    
    assert engine.state == 'HEDGING'
    assert engine.active_hedge['breakeven_sl_active'] == False
    print("[1] Hedge Opened. Breakeven Lock is OFF.")
    
    # 2. Market drops to 60000. Hedge is highly profitable! 
    # Profit calculation: entry=64000, price=60000 -> ((64000 - 60000) / 64000) * 100 = +6.25%
    engine.evaluate(-11.5, -500, 1000, 0.10, 60000, 'SELL', 30, 'BREAKDOWN_DOWN')
    
    assert engine.active_hedge['highest_pnl_pct'] == 6.25
    assert engine.active_hedge['breakeven_sl_active'] == True
    print(f"[2] Hedge hit +6.25% profit. Breakeven Lock is ON.")
    
    # 3. Market slightly recovers to 62000 (still profitable at +3.125%)
    engine.evaluate(-11.5, -500, 1000, 0.10, 62000, 'SELL', 30, 'BREAKDOWN_DOWN')
    assert engine.state == 'HEDGING'
    print("[3] Market retracts. Hedge still active (Lock is holding strong).")
    
    # 4. Market totally reverses to 64000 (0.0% breakeven)
    engine.evaluate(-11.5, -500, 1000, 0.10, 64000, 'SELL', 30, 'BREAKDOWN_DOWN')
    assert engine.state == 'COOLDOWN'
    print("[4] Market hits 64000 (Breakeven). Hedge closes exactly at $0 risk!")
    
    print("\n-> BREAKEVEN STOP LOSS PASSED PERFECTLY!")

if __name__ == "__main__":
    test_breakeven_sl()
