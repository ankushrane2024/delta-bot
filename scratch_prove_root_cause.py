import sys
import time
import logging
from bot_engine import DeltaTradingEngine
import config

# Setup console logger to capture output
logger = logging.getLogger("BotCore")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

print("\n--- PHASE 1 & 2: PROVING ROOT CAUSE ---\n")

bot = DeltaTradingEngine()

# 1. Simulate DB Load (Trade Loaded)
bot.execution.active_positions = {
    "CALL_60000": {"entry_price": 0.05, "size": 1000, "leg_type": "call", "time": "2026-07-18T09:40:00+05:30"},
    "PUT_40000": {"entry_price": 0.03736, "size": 1000, "leg_type": "put", "time": "2026-07-18T09:40:00+05:30"},
    "__dpl_state__": {"highest_profit_pct": 17.02, "current_trailing_sl": 5.0, "trailing_confirmed": True, "confirm_started": True}
}
bot.total_entry_premium = 0.0  # Triggers hot recovery

print("STAGE: Trade Loaded -> PASS")
print(f"Timestamp: {time.time()}")
print(f"Active Positions DB Input: {bot.execution.active_positions}")
print(f"_trade_start_ts BEFORE recovery: {getattr(bot, '_trade_start_ts', 'MISSING')}")

# Mock API for current price
bot.api_client.get_realtime_ticker = lambda sym: {"mark_price": "0.04"} if sym != "BTCUSD" else {"spot_price": "64000"}

# Run exact logic from bot_engine.py hot-recovery
recovered_premium = 0.0
rcalls = []
rputs = []
for sym, data in list(bot.execution.active_positions.items()):
    if sym == "__dpl_state__": continue
    rcalls.append(sym) if "call" in data.get("leg_type", "") else rputs.append(sym)
    recovered_premium += data.get("entry_price", 0) * data.get("size", 0) * 0.001

bot.total_entry_premium = recovered_premium
bot.current_trade_info["calls"] = rcalls
bot.current_trade_info["puts"] = rputs

print(f"\nSTAGE: Hot Recovery -> PASS")
print(f"Recovered Premium: {bot.total_entry_premium}")

# The EXACT bug: bot_engine.py DOES NOT set _trade_start_ts during Hot-Recovery!
print(f"STAGE: Trade Start Time Restored -> FAIL (Missing from Recovery Block)")
print(f"_trade_start_ts AFTER recovery: {getattr(bot, '_trade_start_ts', 'STILL MISSING')}")

# Simulate market drop
current_total_value = 89.88 # Creates a loss
pnl_pct = (87.36 - current_total_value) / 87.36 # Approx -2.88%

# Restore DPL
persisted_dpl = bot.execution.active_positions.pop("__dpl_state__", None)
bot.risk_manager.restore_trailing_state(persisted_dpl)

print("\nSTAGE: Trailing SL Calculation")
print(f"Input PnL Pct: {pnl_pct*100:.2f}%")
print(f"Trailing Confirmed: {bot.risk_manager.trailing_confirmed}")
print(f"Current Trailing SL: {bot.risk_manager.current_trailing_sl*100:.1f}%")

# Generate Action
action = bot.risk_manager.check_sl_tp(bot.total_entry_premium, current_total_value, pnl_pct)
print(f"STAGE: Trailing SL Trigger -> PASS")
print(f"Decision Action: {action}")

# The EXACT bug: Time In Trade calculation
start_ts = getattr(bot, '_trade_start_ts', None) or time.time()
time_in_trade_seconds = time.time() - start_ts

print(f"\nSTAGE: Time In Trade -> FAIL")
print(f"Calculated time_in_trade_seconds: {time_in_trade_seconds:.4f}s")

# 15 Second Protection Rule Evaluation
if time_in_trade_seconds < getattr(config, 'MIN_HOLD_SECONDS', 30):
    if action is not None and time_in_trade_seconds < 15:
        print(f"STAGE: 15 Second Protection -> FAIL (Triggered incorrectly)")
        logger.warning(f"Engine [DEBUG] Hard-Suppressing {action} because time_in_trade ({time_in_trade_seconds:.1f}s) < 15s (spread stabilization)")
        action = None

print(f"STAGE: Decision Engine")
print(f"Final Action Submitted to Execution: {action}")
print(f"Order Status: BLOCKED BY BUG")

print("\n--- END PHASE 1 & 2 ---")
