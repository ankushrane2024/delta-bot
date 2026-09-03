import logging
from local_hpe_engine import HedgeProtectionEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_phantom_hedge():
    print("="*60)
    print("TEST: ZERO DELTA PHANTOM HEDGE")
    engine = HedgeProtectionEngine()
    engine.evaluate(-11.5, -500, 1000, 0.0, 64000, 'SELL', 30, 'BREAKDOWN_DOWN')
    assert engine.state == 'MONITORING', f"State is {engine.state}"
    assert "Hedge Failed (Delta=0)" in engine.standby_reason, f"Reason is {engine.standby_reason}"
    print("-> Phantom Hedge Bug FIXED!\n")

def test_dynamic_delta():
    print("="*60)
    print("TEST: DYNAMIC DELTA RECALCULATION")
    engine = HedgeProtectionEngine()
    # Tier 1 with delta = 0.10 (q_btc = 0.07, max_qty = 0.07, tier1 = 0.0231)
    engine.evaluate(-11.5, -500, 1000, 0.10, 64000, 'SELL', 30, 'BREAKDOWN_DOWN')
    t1_qty = engine.active_hedge['qty']
    assert abs(t1_qty - 0.0231) < 0.001
    
    # Tier 2 with delta = 0.50 (q_btc = 0.35, max_qty = 0.35, tier2 total = 0.231)
    engine.evaluate(-15.5, -600, 1000, 0.50, 63000, 'SELL', 30, 'BREAKDOWN_DOWN')
    t2_qty = engine.active_hedge['qty']
    assert abs(t2_qty - 0.231) < 0.001, f"Expected ~0.231, got {t2_qty}"
    print("-> Dynamic Delta Bug FIXED!\n")

def test_division_by_zero():
    print("="*60)
    print("TEST: DIVISION BY ZERO & MIN CLAMP")
    engine = HedgeProtectionEngine()
    # Microscopic delta = 0.0000001
    engine.evaluate(-11.5, -500, 1000, 0.0000001, 64000, 'SELL', 30, 'BREAKDOWN_DOWN')
    t1_qty = engine.active_hedge['qty']
    assert t1_qty == 0.001, f"Expected 0.001 clamp, got {t1_qty}"
    
    # Scale to tier 2 with same micro delta
    engine.evaluate(-15.5, -600, 1000, 0.0000001, 63000, 'SELL', 30, 'BREAKDOWN_DOWN')
    t2_qty = engine.active_hedge['qty']
    # max_qty is clamped to 0.003, tier 2 target is 0.003 * 0.66 = 0.00198
    assert abs(t2_qty - 0.00198) < 0.0001, f"Expected 0.00198, got {t2_qty}"
    print("-> Division by Zero Bug FIXED!\n")

if __name__ == "__main__":
    test_phantom_hedge()
    test_dynamic_delta()
    test_division_by_zero()
    print("ALL BUG FIX TESTS PASSED PERFECTLY!")
