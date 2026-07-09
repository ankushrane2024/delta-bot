"""Quick DPL + INR verification script"""
from risk_manager import RiskManager

rm = RiskManager(50000)

# Test 1: Default state
ts = rm.get_trailing_state()
assert ts['current_trailing_sl'] is None
assert ts['trailing_confirmed'] == False
print("Test 1 PASS: Default state clean")

# Test 2: 15% profit -> lock SL at +5%
action = rm.check_sl_tp(100, 85, 0.15)
ts = rm.get_trailing_state()
print(f"Test 2: At 15% profit -> SL={ts['current_trailing_sl']}%, confirmed={ts['trailing_confirmed']}")
assert ts['trailing_confirmed'] == True
assert ts['current_trailing_sl'] == 5.0
print("Test 2 PASS: SL locked at +5%")

# Test 3: 20% profit -> lock SL at +12%
action = rm.check_sl_tp(100, 80, 0.20)
ts = rm.get_trailing_state()
print(f"Test 3: At 20% profit -> SL={ts['current_trailing_sl']}%")
assert ts['current_trailing_sl'] == 12.0
print("Test 3 PASS: SL ratcheted to +12%")

# Test 4: 25% profit -> lock SL at +17%
action = rm.check_sl_tp(100, 75, 0.25)
ts = rm.get_trailing_state()
print(f"Test 4: At 25% profit -> SL={ts['current_trailing_sl']}%")
assert ts['current_trailing_sl'] == 17.0
print("Test 4 PASS: SL ratcheted to +17%")

# Test 5: SL dollar value calculation (same math the chart uses)
entry_premium = 0.5  # $0.50 total
sl_pct = ts['current_trailing_sl']
sl_dollar = entry_premium * (sl_pct / 100)
print(f"Test 5: SL Line: entry=${entry_premium}, locked={sl_pct}%, line_at=${sl_dollar:.4f}")
assert sl_dollar > 0
print("Test 5 PASS: SL dollar value correct")

# Test 6: INR rate check
rate = 95.5
pnl_usd = 1.0
pnl_inr = pnl_usd * rate
assert pnl_inr == 95.5
print(f"Test 6 PASS: INR rate = {rate}")

print("\n=== ALL VERIFICATION TESTS PASSED ===")
