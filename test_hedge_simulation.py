"""
End-to-end simulation test for the fixed smart_hedging.py engine.
Tests all 3 critical scenarios found in the screenshots.
"""
import sys

# Mock all external dependencies
class MockExec:
    def __init__(self):
        self.hedge_size_btc = 0.0
        self.hedge_entry_price = 0.0
        self.hedge_position = 0
        self.hedge_order_id = None
    def place_hedge_order(self, size, direction, use_limit=False):
        price = getattr(self, '_mock_price', 69800)
        signed = size if direction == 'buy' else -size
        self.hedge_size_btc += signed
        if self.hedge_entry_price <= 0:
            self.hedge_entry_price = price
        return {'success': True, 'order_id': 'TEST-001', 'fill_price': price}
    def close_hedge(self):
        self.hedge_size_btc = 0.0
        self.hedge_entry_price = 0.0
        self.hedge_position = 0

class MockDvol:
    def get_current_dvol(self): return 38.5

class MockRisk:
    def tighten_stop_loss(self, x): print(f"  SL tightened to {x}x")

class MockApi:
    def __init__(self, call_d, put_d, btc_price, call_price=63.58, put_price=349.30):
        self.call_d = call_d
        self.put_d = put_d
        self.btc = btc_price
        self.call_price = call_price
        self.put_price = put_price

    def get_realtime_ticker(self, sym):
        if sym.startswith('C-'):
            return {'mark_price': self.call_price, 'greeks': {'delta': self.call_d, 'gamma': 0.0001}}
        else:
            return {'mark_price': self.put_price, 'greeks': {'delta': self.put_d, 'gamma': 0.0}}

    def get_tickers(self, params=None):
        return {
            'success': True,
            'result': [{'symbol': 'BTCUSD', 'mark_price': self.btc, 'product_id': 123}]
        }

class MockNotifier:
    def notify_hedge_executed(self, **kw):
        print(f"  [NOTIFY] Hedge executed: {kw.get('hedge_type')} {kw.get('size_btc', 0):.4f} BTC")
    def notify_hedge_failed(self):
        print("  [NOTIFY] Hedge FAILED!")
    def notify_hedge_escalated(self, **kw):
        print(f"  [NOTIFY] Hedge escalated to {kw.get('to_pct', 0):.0f}%")
    def notify_error(self, msg):
        print(f"  [NOTIFY] Error: {msg}")

mock_mod = type(sys)('notifier')
mock_mod.notifier = MockNotifier()
sys.modules['notifier'] = mock_mod

from smart_hedging import SmartHedgingManager

positions = {
    'C-BTC-72200-080626': {'size': 500, 'entry_price': 178.30, 'leg_type': 'call'},
    'P-BTC-69600-080626': {'size': 500, 'entry_price': 176.53, 'leg_type': 'put'},
}

PASS = 0
FAIL = 0

def check(cond, label):
    global PASS, FAIL
    if cond:
        print(f"  [PASS] {label}")
        PASS += 1
    else:
        print(f"  [FAIL] {label}")
        FAIL += 1

# ==========================================================
print("=" * 60)
print("SCENARIO 1: API returns delta=0.000 for PUT leg (main bug)")
print("=" * 60)
print("  Context: BTC dropped, put is bleeding. But API shows put delta=0.")
print("  Expected: Hedge should SELL BTC (go short) to profit when BTC falls.")
print()

api = MockApi(call_d=0.093, put_d=0.0, btc_price=69500, call_price=63.58, put_price=349.30)
exc = MockExec()
exc._mock_price = 69500
mgr = SmartHedgingManager(exc, MockDvol(), MockRisk(), api)
mgr.set_entry_premiums(positions)

mgr.manage_hedge(positions, unrealized_loss_pct=0.35, profit_usd=-60.0)

print()
check(mgr.hedge_active, "Hedge is active")
check(exc.hedge_size_btc < 0, f"Hedge is SHORT BTC (size={exc.hedge_size_btc:+.4f}) — will profit when BTC falls")
check(mgr.hedge_avg_entry_price > 0, f"Avg entry price set correctly: ${mgr.hedge_avg_entry_price:,.2f}")

# ==========================================================
print()
print("=" * 60)
print("SCENARIO 2: API returns correct put delta = -0.45")
print("=" * 60)
print("  Expected: Same result — SELL BTC — but using real delta data.")
print()

api2 = MockApi(call_d=0.093, put_d=-0.45, btc_price=69500)
exc2 = MockExec()
exc2._mock_price = 69500
mgr2 = SmartHedgingManager(exc2, MockDvol(), MockRisk(), api2)
mgr2.set_entry_premiums(positions)

mgr2.manage_hedge(positions, unrealized_loss_pct=0.35, profit_usd=-60.0)

print()
check(mgr2.hedge_active, "Hedge is active")
check(exc2.hedge_size_btc < 0, f"Hedge is SHORT BTC (size={exc2.hedge_size_btc:+.4f})")

# ==========================================================
print()
print("=" * 60)
print("SCENARIO 3: Weighted avg entry price after rebalance")
print("=" * 60)
print("  Initial hedge: SELL 0.20 BTC @ $70,000")
print("  Rebalance:     SELL 0.10 BTC @ $69,000")
print("  True avg entry should be: $69,666.67")
print("  BTC drops to $68,000 — hedge should PROFIT.")
print()

exc3 = MockExec()
exc3._mock_price = 70000
api3 = MockApi(0.093, -0.5, 70000)
mgr3 = SmartHedgingManager(exc3, MockDvol(), MockRisk(), api3)
mgr3.hedge_active = True
mgr3.hedge_placed_time = 0  # bypass min-hold for test

# Simulate initial fill
exc3._mock_price = 70000
r1 = mgr3._place_hedge(0.20, 'sell', 'INITIAL')
exc3.hedge_size_btc = -0.20
mgr3.hedge_size_btc = -0.20

# Simulate rebalance fill at lower price
exc3._mock_price = 69000
mgr3.api_client = MockApi(0.093, -0.5, 69000)
r2 = mgr3._place_hedge(0.10, 'sell', 'REBALANCE')
exc3.hedge_size_btc = -0.30
mgr3.hedge_size_btc = -0.30

expected_avg = (0.20 * 70000 + 0.10 * 69000) / 0.30
print(f"  Expected avg entry: ${expected_avg:,.2f}")
print(f"  Computed avg entry: ${mgr3.hedge_avg_entry_price:,.2f}")
print()

check(abs(mgr3.hedge_avg_entry_price - expected_avg) < 1.0, "Weighted avg entry price is correct")

# PnL at BTC = $68,000 (dropped further)
mgr3.api_client = MockApi(0.093, -0.6, 68000)
pnl = mgr3.get_live_hedge_pnl()
print(f"  Hedge PnL at BTC=$68,000: ${pnl:+,.2f}")
check(pnl > 0, f"Hedge is PROFITABLE (${pnl:+,.2f}) when BTC dropped as expected!")

# ==========================================================
print()
print("=" * 60)
print("SCENARIO 4: Unwind when market reverts")
print("=" * 60)
print("  Hedge was placed when BTC was falling. Now BTC rebounds.")
print("  Delta should neutralize. Hedge must unwind to lock in profit.")
print()

exc4 = MockExec()
exc4.hedge_size_btc = -0.20
exc4._mock_price = 70200
# Rebound: both legs delta now nearly neutral (raw_delta < 0.08)
api4 = MockApi(call_d=0.12, put_d=-0.10, btc_price=70200)  # balanced delta
mgr4 = SmartHedgingManager(exc4, MockDvol(), MockRisk(), api4)
mgr4.hedge_active = True
mgr4.hedge_avg_entry_price = 69500.0
mgr4.hedge_placed_time = 0   # min-hold bypassed

mgr4.manage_hedge(positions, unrealized_loss_pct=0.05, profit_usd=-8.0)
print()
check(not mgr4.hedge_active, "Hedge was unwound when delta neutralized (market reverted)")

# ==========================================================
print()
print("=" * 60)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 60)
if FAIL == 0:
    print("ALL TESTS PASSED! Fix is working correctly.")
else:
    print(f"WARNING: {FAIL} test(s) FAILED. Review the logic above.")
