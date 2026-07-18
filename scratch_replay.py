import sys
import time
import logging
from bot_engine import DeltaTradingEngine
from dateutil import parser
import config

# Suppress debug logs for clean table
logging.getLogger("BotCore").setLevel(logging.CRITICAL)

bot = DeltaTradingEngine()

# Setup hot recovery
bot.execution.active_positions = {
    "CALL_60000": {"entry_price": 0.05, "size": 1000, "leg_type": "call", "time": "2026-07-18T09:40:00+05:30"},
    "PUT_40000": {"entry_price": 0.03736, "size": 1000, "leg_type": "put", "time": "2026-07-18T09:40:00+05:30"},
}
# Recover Premium
bot.total_entry_premium = 0.08736 

print("--- PHASE 3: TRADE REPLAY ---")
print("Replaying trade trajectory with fixed bot engine...\n")

trajectory = [
    {"time": "09:40:00", "pnl": 0.00},
    {"time": "10:15:00", "pnl": 14.87},
    {"time": "11:15:00", "pnl": -2.52} # After Render restart
]

entry_dt = parser.parse("2026-07-18T09:40:00+05:30")
entry_ts = entry_dt.timestamp()

for tick in trajectory:
    # Set current time
    current_time_str = tick['time']
    current_time_dt = parser.parse(f"2026-07-18T{current_time_str}+05:30")
    current_ts = current_time_dt.timestamp()
    
    # Calculate premium
    profit_usd = tick['pnl']
    current_value = bot.total_entry_premium - (profit_usd / 1000) # approximate
    pnl_pct = profit_usd / 87.36
    
    # Hot recovery logic simulation for the last tick
    if tick['time'] == "11:15:00":
        # Simulate restart by clearing _trade_start_ts and re-running hot recovery
        bot._trade_start_ts = None
        
        # New HOT-RECOVERY code (which is active in main)
        oldest_entry_time = time.time()
        for sym, data in bot.execution.active_positions.items():
            if 'time' in data:
                ts = parser.parse(data['time']).timestamp()
                if ts < oldest_entry_time:
                    oldest_entry_time = ts
        if not getattr(bot, '_trade_start_ts', None):
            bot._trade_start_ts = oldest_entry_time
            
        # Also restore DPL from DB (it hit 14.87 earlier)
        dpl = {"highest_profit_pct": 17.02, "current_trailing_sl": 5.0, "trailing_confirmed": True, "confirm_started": True}
        bot.risk_manager.restore_trailing_state(dpl)
    else:
        bot._trade_start_ts = entry_ts
        bot.risk_manager._update_ratchet(pnl_pct)
        
    action = bot.risk_manager.check_sl_tp(bot.total_entry_premium, current_value, pnl_pct)
    
    start_ts = getattr(bot, '_trade_start_ts', None) or current_ts
    time_in_trade_seconds = current_ts - start_ts
    
    protection_active = False
    if time_in_trade_seconds < getattr(config, 'MIN_HOLD_SECONDS', 30):
        if action is not None and time_in_trade_seconds < 15:
            protection_active = True
            action = None
            
    hh = int(time_in_trade_seconds // 3600)
    mm = int((time_in_trade_seconds % 3600) // 60)
    ss = int(time_in_trade_seconds % 60)
    
    print(f"Time                  : {tick['time']}")
    print(f"Current PnL           : ${profit_usd:.2f} ({(pnl_pct*100):.2f}%)")
    print(f"Peak Profit           : {bot.risk_manager.highest_profit_pct*100:.2f}%")
    sl_val = bot.risk_manager.current_trailing_sl
    print(f"Locked Profit         : {sl_val*100:.1f}%" if sl_val else "Locked Profit         : None")
    print(f"Trailing SL           : {bot.risk_manager.trailing_confirmed}")
    print(f"Trade Start Time      : {entry_dt.strftime('%H:%M:%S')}")
    print(f"Current Time          : {current_time_dt.strftime('%H:%M:%S')}")
    print(f"Time In Trade         : {hh}h {mm}m {ss}s")
    print(f"Trailing SL Trigger   : {'YES' if action == 'TRAILING_SL_EXIT' else 'NO'}")
    print(f"15 Second Protection  : {protection_active}")
    print(f"Decision              : {action if action else 'HOLD'}")
    print(f"Order Status          : {'SUBMITTED' if action else 'NONE'}")
    print("-" * 50)

print("--- END PHASE 3 ---\n")
