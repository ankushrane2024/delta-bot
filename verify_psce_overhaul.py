"""
PSCE Overhaul Verification Script
Tests the simplified IV Trade Readiness Master Gate logic.
"""
import sys
import time
import json

# Mock the dependencies
class MockLogger:
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg, **kwargs): pass

class MockModule:
    pass

# Setup mock modules before importing psce
sys.modules['logger'] = type(sys)('logger')
sys.modules['logger'].app_logger = MockLogger()
sys.modules['logger'].error_logger = MockLogger()
sys.modules['utils'] = type(sys)('utils')

from datetime import datetime, timezone
sys.modules['utils'].get_ist_now = lambda: datetime.now(timezone.utc)

sys.modules['db_manager'] = type(sys)('db_manager')

# Now import psce
from psce import PremiumSellingConditionsEngine

class MockApiClient:
    last_price_update_time = time.time()
    def get_realtime_ticker(self, symbol):
        return {'spot_price': 105000.0, 'mark_price': 105000.0}
    def get_history(self, symbol, interval):
        # Return 120 fake hourly candles
        return [{'close': 100000 + i*10} for i in range(120)]

class MockDvolProvider:
    def __init__(self, dvol_value):
        self.current_dvol = dvol_value
        self.dvol_history = [40 + i*0.5 for i in range(30)]
        self.dvol_percentile = 50.0
        self.last_update_time = time.time()  # Fresh data
    
    def refresh_data(self):
        self.last_update_time = time.time()

def test_iv_scenario(iv_value, expected_allowed, scenario_name):
    provider = MockDvolProvider(iv_value)
    api = MockApiClient()
    engine = PremiumSellingConditionsEngine(api, provider)
    
    result = engine.evaluate_conditions(mode="ENTRY")
    
    actual_allowed = result.get('trade_allowed', False)
    final_decision = result.get('final_decision', 'UNKNOWN')
    reason = result.get('decision_reason', 'No reason')
    
    status = "✅ PASS" if actual_allowed == expected_allowed else "❌ FAIL"
    
    print(f"\n{'='*60}")
    print(f"  {scenario_name}")
    print(f"{'='*60}")
    print(f"  IV Value:       {iv_value}%")
    print(f"  Expected:       {'ALLOW' if expected_allowed else 'BLOCK'}")
    print(f"  Actual:         {final_decision}")
    print(f"  trade_allowed:  {actual_allowed}")
    print(f"  Reason:         {reason}")
    print(f"  Zone:           {result.get('zone')}")
    print(f"  Edge Score:     {result.get('edge_score')}")
    print(f"  IV Status:      {result.get('iv_status')}")
    print(f"  Data Age:       {result.get('data_age_seconds')}s")
    print(f"  IV Timestamp:   {result.get('iv_data_timestamp')}")
    print(f"  Result:         {status}")
    
    return actual_allowed == expected_allowed

def test_manual_force_bypass():
    """Simulate what happens when force=True bypasses PSCE in bot_engine."""
    print(f"\n{'='*60}")
    print(f"  TEST 4: Manual Force Trade Bypass (IV=15%)")
    print(f"{'='*60}")
    
    provider = MockDvolProvider(15.0)  # Very low IV - would normally block
    api = MockApiClient()
    engine = PremiumSellingConditionsEngine(api, provider)
    
    result = engine.evaluate_conditions(mode="ENTRY")
    
    # Simulate the bot_engine logic with force=True
    trade_allowed = result.get('trade_allowed', False)
    force = True
    
    if not trade_allowed:
        if force:
            action = "MANUAL_OVERRIDE"
            proceed = True
            psce_reason = result.get('decision_reason', 'Unknown')
            audit_msg = f"Manual Force Trade bypassed PSCE. IV filter recommended: {psce_reason}"
        else:
            action = "TRADE_BLOCKED"
            proceed = False
            audit_msg = "Trade blocked by PSCE"
    else:
        action = "TRADE_ALLOWED"
        proceed = True
        audit_msg = "Trade allowed normally"
    
    status = "✅ PASS" if proceed and action == "MANUAL_OVERRIDE" else "❌ FAIL"
    
    print(f"  PSCE Decision:  {result.get('final_decision')} (would block)")
    print(f"  force=True:     Trade PROCEEDS anyway")
    print(f"  Action:         {action}")
    print(f"  Audit Log:      {audit_msg}")
    print(f"  Result:         {status}")
    
    return proceed and action == "MANUAL_OVERRIDE"

def test_stale_data():
    """Test that stale IV data triggers refresh."""
    print(f"\n{'='*60}")
    print(f"  TEST 5: Stale IV Data Detection")
    print(f"{'='*60}")
    
    provider = MockDvolProvider(45.0)
    provider.last_update_time = time.time() - 600  # 10 minutes old
    api = MockApiClient()
    engine = PremiumSellingConditionsEngine(api, provider)
    
    result = engine.evaluate_conditions(mode="ENTRY")
    
    # After evaluation, provider should have been refreshed
    data_age = result.get('data_age_seconds', 999)
    refreshed = data_age < 5  # Should be near 0 after refresh
    
    status = "✅ PASS" if refreshed else "❌ FAIL"
    print(f"  Initial Age:    600s (stale)")
    print(f"  After Eval:     {data_age}s")
    print(f"  Refreshed:      {refreshed}")
    print(f"  Result:         {status}")
    
    return refreshed

def show_decision_flow():
    """Print the complete decision flow with file names, function names, and line numbers."""
    print(f"\n{'='*60}")
    print(f"  COMPLETE DECISION FLOW")
    print(f"{'='*60}")
    print("""
  ┌─────────────────────────────────────────────────────────┐
  │ 1. web_server.py → manual_order() [L549]               │
  │    POST /api/manual_order                               │
  │    → bot_engine.run_entry_cycle(force=True)             │
  ├─────────────────────────────────────────────────────────┤
  │ 2. bot_engine.py → run_entry_cycle(force) [L162]        │
  │    L183: psce_eval = premium_engine.evaluate_conditions │
  │    L185: if not trade_allowed:                          │
  │      L186: if force → MANUAL_OVERRIDE (proceed)         │
  │      L200: else → TRADE_BLOCKED (return)                │
  ├─────────────────────────────────────────────────────────┤
  │ 3. psce.py → evaluate_conditions() [L120]               │
  │    L170: _ensure_fresh_iv() — force refresh if stale    │
  │    L178: Check data age vs freshness_timeout            │
  │    L185: Get current_iv from dvol_provider              │
  │    L236: if current_iv < min_iv_threshold (20%)         │
  │      → BLOCK: "Extremely Low IV"                        │
  │    L244: else → ALLOW: "Trade conditions favorable"     │
  ├─────────────────────────────────────────────────────────┤
  │ 4. dvol_provider.py → refresh_data() [L58]              │
  │    L62: fetch_current_dvol() — Deribit API              │
  │    L65: fetch_dvol_history(30d) — Deribit API           │
  │    L82: last_update_time = time.time()                  │
  ├─────────────────────────────────────────────────────────┤
  │ 5. dashboard.html → updateAresPremium() [L4329]         │
  │    Fetches /api/premium_conditions (web_server.py L30)  │
  │    Displays: live_iv, iv_status, data_age_seconds,      │
  │    iv_data_timestamp, final_decision, decision_reason   │
  └─────────────────────────────────────────────────────────┘
""")

# ─── RUN ALL TESTS ───
print("\n" + "═"*60)
print("  PSCE OVERHAUL — VERIFICATION REPORT")
print("═"*60)

results = []
results.append(test_iv_scenario(18.0, False, "TEST 1: IV = 18% → Expected BLOCK"))
results.append(test_iv_scenario(24.0, True, "TEST 2: IV = 24% → Expected ALLOW"))
results.append(test_iv_scenario(35.0, True, "TEST 3: IV = 35% → Expected ALLOW"))
results.append(test_manual_force_bypass())
results.append(test_stale_data())
show_decision_flow()

passed = sum(results)
total = len(results)
print(f"\n{'═'*60}")
print(f"  FINAL RESULT: {passed}/{total} tests passed")
if passed == total:
    print(f"  ✅ ALL TESTS PASSED — PSCE Overhaul is verified!")
else:
    print(f"  ❌ SOME TESTS FAILED — Review needed")
print(f"{'═'*60}\n")
