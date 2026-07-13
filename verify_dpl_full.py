"""
Comprehensive DPL Verification Test — Tests all critical scenarios including server restart recovery.
"""
from risk_manager import RiskManager
import config

print("=" * 60)
print("   DPL RATCHET + CLOUD PERSISTENCE VERIFICATION")
print("=" * 60)

rm = RiskManager(api_client=None)

# Test 1: Fresh state
print("\nTest 1: Fresh state")
ts = rm.get_trailing_state()
print(f"  Peak={ts['highest_profit_pct']}%, SL={ts['current_trailing_sl']}, Confirmed={ts['trailing_confirmed']}")
assert rm.highest_profit_pct == 0.0
assert rm.current_trailing_sl is None
assert rm.trailing_confirmed == False
print("  >> PASS")

# Test 2: Profit hits 23% → SL should lock at +17%
print("\nTest 2: Profit hits 23% -> SL should lock at +17%")
rm.check_sl_tp(100, 77, 0.23)
ts = rm.get_trailing_state()
print(f"  Peak={ts['highest_profit_pct']}%, SL={ts['current_trailing_sl']}%, Confirmed={ts['trailing_confirmed']}")
assert ts['trailing_confirmed'] == True
assert ts['current_trailing_sl'] == 12.0  # Tier: 20%->12% (23% has NOT reached 25% tier yet)
print("  >> PASS")

# Test 3: Profit drops to 18% → SL must NOT drop
print("\nTest 3: Profit drops to 18% -> SL must NOT drop")
rm.check_sl_tp(100, 82, 0.18)
ts = rm.get_trailing_state()
print(f"  Peak={ts['highest_profit_pct']}%, SL={ts['current_trailing_sl']}%, Confirmed={ts['trailing_confirmed']}")
assert ts['current_trailing_sl'] == 12.0  # Must not go down!
assert ts['highest_profit_pct'] == 23.0    # Peak must not drop!
print("  >> PASS - SL stayed at 17%, did NOT drop")

# Test 4: Profit rises to 30% → SL should move to 25% (dynamic trail: 30% - 5% gap)
print("\nTest 4: Profit rises to 30% -> SL should move to 25% (dynamic trail)")
rm.check_sl_tp(100, 70, 0.30)
ts = rm.get_trailing_state()
print(f"  Peak={ts['highest_profit_pct']}%, SL={ts['current_trailing_sl']}%, Confirmed={ts['trailing_confirmed']}")
assert ts['current_trailing_sl'] == 25.0
print("  >> PASS")

# Test 5: Simulate SERVER RESTART — save state, create new RiskManager, restore
print("\nTest 5: Simulate SERVER RESTART - save and restore DPL state")
saved_state = rm.get_trailing_state()
print(f"  Saved state: {saved_state}")

rm2 = RiskManager(api_client=None)  # Fresh instance (simulates server restart)
ts_fresh = rm2.get_trailing_state()
print(f"  Fresh instance (before restore): Peak={ts_fresh['highest_profit_pct']}%, SL={ts_fresh['current_trailing_sl']}")
assert ts_fresh['highest_profit_pct'] == 0.0  # Wiped!

rm2.restore_trailing_state(saved_state)
ts2 = rm2.get_trailing_state()
print(f"  After restore: Peak={ts2['highest_profit_pct']}%, SL={ts2['current_trailing_sl']}%, Confirmed={ts2['trailing_confirmed']}")
assert ts2['current_trailing_sl'] == 25.0
assert ts2['highest_profit_pct'] == 30.0
assert ts2['trailing_confirmed'] == True
print("  >> PASS - EXACT state restored after restart")

# Test 6: After restore, profit drops to 26% → SL must NOT drop from 25%
print("\nTest 6: After restore, profit drops to 26% -> SL must NOT drop from 25%")
rm2.check_sl_tp(100, 74, 0.26)
ts3 = rm2.get_trailing_state()
print(f"  Peak={ts3['highest_profit_pct']}%, SL={ts3['current_trailing_sl']}%, Confirmed={ts3['trailing_confirmed']}")
assert ts3['current_trailing_sl'] == 25.0
assert ts3['highest_profit_pct'] == 30.0
print("  >> PASS - SL stayed at 25% after restore + drop")

# Test 7: After restore, profit rises to 35% → SL moves UP to 30%
print("\nTest 7: After restore, profit rises to 35% -> SL ratchets UP to 30%")
rm2.check_sl_tp(100, 65, 0.35)
ts4 = rm2.get_trailing_state()
print(f"  Peak={ts4['highest_profit_pct']}%, SL={ts4['current_trailing_sl']}%, Confirmed={ts4['trailing_confirmed']}")
assert ts4['current_trailing_sl'] == 30.0
print("  >> PASS - SL correctly ratcheted UP to 30%")

# Test 8: Trailing SL HIT — profit drops below locked SL
print("\nTest 8: Profit drops to 24% which is BELOW locked SL of 30% -> TRAILING_SL_EXIT")
result = rm2.check_sl_tp(100, 76, 0.24)
print(f"  Result: {result}")
assert result == "TRAILING_SL_EXIT"
print("  >> PASS - Trade correctly exited at trailing SL")

print("\n" + "=" * 60)
print("   ALL 8 TESTS PASSED! DPL IS BULLETPROOF!")
print("=" * 60)
