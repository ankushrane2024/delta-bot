import logging
from local_hpe_engine import HedgeProtectionEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def run_tests():
    print("="*60)
    print("SCENARIO A: SCALE IN AND TREND REVERSAL EXIT")
    print("="*60)
    engine = HedgeProtectionEngine()
    
    # Trigger Tier 1
    engine.evaluate(-11.5, -500, 1000, 0.10, 64000, 'SELL', 30, 'BREAKDOWN_DOWN')
    assert engine.state == 'HEDGING'
    assert engine.active_hedge['scale_tier'] == 1
    
    # Trigger Trend Reversal (Supertrend flips to BUY)
    engine.evaluate(-12.0, -500, 1000, 0.10, 63000, 'BUY', 30, 'BREAKDOWN_DOWN')
    assert engine.state == 'COOLDOWN'
    assert engine.active_hedge is None
    print("-> Scenario A Passed!\n")


    print("="*60)
    print("SCENARIO B: SCALE IN TO TIER 2 AND OPTIONS RECOVERY EXIT")
    print("="*60)
    engine = HedgeProtectionEngine()
    
    # Tier 1
    engine.evaluate(-11.5, -500, 1000, 0.10, 64000, 'SELL', 30, 'BREAKDOWN_DOWN')
    # Tier 2
    engine.evaluate(-15.5, -600, 1000, 0.10, 63000, 'SELL', 30, 'BREAKDOWN_DOWN')
    assert engine.active_hedge['scale_tier'] == 2
    
    # Options Recover > -4%
    engine.evaluate(-3.5, -200, 1000, 0.10, 64500, 'SELL', 30, 'BREAKDOWN_DOWN')
    assert engine.state == 'COOLDOWN'
    assert engine.active_hedge is None
    print("-> Scenario B Passed!\n")


    print("="*60)
    print("SCENARIO C: SCALE TO TIER 3 AND WHIPSAW EXIT")
    print("="*60)
    engine = HedgeProtectionEngine()
    
    # Tier 1, 2, 3
    engine.evaluate(-11.5, -500, 1000, 0.10, 64000, 'SELL', 30, 'BREAKDOWN_DOWN')
    engine.evaluate(-15.5, -600, 1000, 0.10, 63000, 'SELL', 30, 'BREAKDOWN_DOWN')
    engine.evaluate(-20.5, -700, 1000, 0.10, 62000, 'SELL', 30, 'BREAKDOWN_DOWN')
    assert engine.active_hedge['scale_tier'] == 3
    
    # Whipsaw: Rejection Signal triggers
    engine.evaluate(-20.5, -700, 1000, 0.10, 62000, 'SELL', 30, 'BREAKDOWN_DOWN', rejection_signal='BULLISH_REJECTION')
    assert engine.state == 'COOLDOWN'
    print("-> Scenario C Passed!\n")


    print("="*60)
    print("SCENARIO D: HEDGE STOP LOSS (10%)")
    print("="*60)
    engine = HedgeProtectionEngine()
    
    engine.evaluate(-11.5, -500, 1000, 0.10, 64000, 'SELL', 30, 'BREAKDOWN_DOWN')
    # BTC pumps massively, hedge (SELL) goes into deep loss
    # Entry = 64000. 10% loss on SELL is when price rises to 64000 * 1.10 = 70400
    engine.evaluate(-11.5, -500, 1000, 0.10, 71000, 'SELL', 30, 'BREAKDOWN_DOWN')
    assert engine.state == 'COOLDOWN'
    print("-> Scenario D Passed!\n")
    
    print("ALL TESTS PASSED PERFECTLY!")

if __name__ == "__main__":
    run_tests()
