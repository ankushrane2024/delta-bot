import time
import os
import json
import logging
import sys

from audit_manager import audit_system
from bot_engine import DeltaTradingEngine
import db_manager

logging.getLogger("BotCore").setLevel(logging.CRITICAL)

print("=== STARTING END-TO-END AUDIT SIMULATION ===")

# Force cleanup
if os.path.exists('decision_audit.json'): os.remove('decision_audit.json')
audit_system.session_events = []
audit_system.current_trade_id = None
db_manager.JSONBLOB_ID = None

# Initialize bot1
bot = DeltaTradingEngine()

# 1. Trade Entry
print("[+] Simulating Trade Entry")
bot.current_trade_info["btc_entry_price"] = 64000.0
bot._trade_start_ts = time.time() - 3600 # 1 hour ago
audit_system.start_trade_session(64000.0)

trade_id = audit_system.current_trade_id
print(f"    -> Trade ID: {trade_id}")

# 2. Profit Lock Activation (Routine cycle)
print("[+] Simulating Profit Lock Activation")
bot.risk_manager.active_trade_params = {'max_profit_pct': 0.15, 'trailing_sl_pct': 5.0, 'locked': True}
audit_snapshot = bot._build_audit_snapshot(
    btc_price=64500.0, options_profit=15.0, hedge_pnl=0.0, pnl_pct=0.15, 
    time_in_trade_seconds=3600, action=None, reason="Peak profit hit 15%, locked SL at 5%"
)
audit_system.log_event("Profit Lock Activated", "bot_engine", "_monitor_loop", audit_snapshot, "Profit > 15%")

# 3. Hedge Trigger
print("[+] Simulating Hedge Trigger")
bot.smart_hedging._log_hedge_event("OPEN", "Bleeding Call Leg", "buy", 0.05, 0.05, 65000.0, -10.0, 0.0)

# 4. Render Restart (Crash simulation)
print("[+] Simulating Render Crash & Wipe")
audit_system.session_events = []
audit_system.current_trade_id = None
# db_manager holds the JSON file simulating cloud storage
print(f"    -> Cloud DB exists: {os.path.exists('decision_audit.json')}")

# 5. Hot Recovery
print("[+] Simulating Hot Recovery")
bot2 = DeltaTradingEngine()
bot2.total_entry_premium = 0
bot2.execution.active_positions = {"CALL_64000": {"entry_price": 0.01, "size": 1000, "leg_type": "call"}}

recovered_audit = db_manager.load_audit_log()
audit_system.recover_trade_session(recovered_audit)
print(f"    -> Recovered Trade ID: {audit_system.current_trade_id}")
print(f"    -> Recovered Events: {len(audit_system.session_events)}")

# 6. Trailing SL Hit
print("[+] Simulating Trailing SL Trigger")
audit_snapshot2 = bot2._build_audit_snapshot(
    btc_price=64000.0, options_profit=2.0, hedge_pnl=0.0, pnl_pct=0.02, 
    time_in_trade_seconds=3610, action="TRAILING_SL_EXIT", reason="Profit dropped below 5% lock"
)
audit_system.log_critical_event("Action Triggered: TRAILING_SL_EXIT", "bot_engine", "_monitor_loop", audit_snapshot2, "Risk Engine decided to TRAILING_SL_EXIT")

# 7. Square-Off & Export
print("[+] Simulating Square-Off and Export")
export_file = audit_system.export_session()
print(f"    -> Exported to {export_file}")

# 8. Validation
print("\n=== VALIDATING AUDIT EXPORT ===")
with open(export_file, 'r') as f:
    exported_events = json.load(f)

print(f"Total Events Found: {len(exported_events)}")

event_types = [e['Event Type'] for e in exported_events]
print(f"Event Flow: {' -> '.join(event_types)}")

assert "Trade Entry" in event_types, "Missing Trade Entry"
assert "Profit Lock Activated" in event_types, "Missing Profit Lock"
assert "Hedge OPEN" in event_types, "Missing Hedge Trigger"
assert "Hot Recovery" in event_types, "Missing Hot Recovery"
assert "Action Triggered: TRAILING_SL_EXIT" in event_types, "Missing SL Trigger"

print("\n[SUCCESS] E2E Audit validation completed perfectly.")
sys.exit(0)
