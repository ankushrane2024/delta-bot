import time
import logging
from bot_engine import DeltaTradingEngine

# Suppress noisy logs
logging.getLogger("BotCore").setLevel(logging.CRITICAL)

print("--- PHASE 6: RECOVERY STRESS TEST ---")
print("Running 20 consecutive recoveries...\n")

success_count = 0

try:
    for i in range(1, 21):
        # 1. Start fresh trade
        bot = DeltaTradingEngine()
        bot.execution.active_positions = {
            "CALL_60000": {"entry_price": 0.05, "size": 1000, "leg_type": "call", "time": "2026-07-18T09:40:00+05:30"},
            "PUT_40000": {"entry_price": 0.03736, "size": 1000, "leg_type": "put", "time": "2026-07-18T09:40:00+05:30"},
            "__dpl_state__": {"highest_profit_pct": 17.02, "current_trailing_sl": 5.0, "trailing_confirmed": True, "confirm_started": True}
        }
        bot.total_entry_premium = 0.0
        
        # 2. Force Hot Recovery & Validation
        try:
            bot.api_client.get_realtime_ticker = lambda sym: {"mark_price": "0.04"} if sym != "BTCUSD" else {"spot_price": "64000"}
            
            recovered_premium = 0.0
            rcalls = []
            rputs = []
            oldest_entry_time = time.time()
            for sym, data in bot.execution.active_positions.items():
                if sym == "__dpl_state__": continue
                ltype = data.get('leg_type', '').lower()
                rcalls.append(sym) if 'call' in ltype else rputs.append(sym)
                recovered_premium += data.get('entry_price', 0) * data.get('size', 0) * 0.001
                if 'time' in data:
                    from dateutil import parser
                    ts = parser.parse(data['time']).timestamp()
                    if ts < oldest_entry_time: oldest_entry_time = ts
            
            bot.total_entry_premium = recovered_premium
            bot._trade_start_ts = oldest_entry_time
            bot.current_trade_info["calls"] = rcalls
            bot.current_trade_info["puts"] = rputs
            
            persisted_dpl = bot.execution.active_positions.pop('__dpl_state__', None)
            bot.risk_manager.restore_trailing_state(persisted_dpl)
            
            # The exact validator I just added to the code
            bot._validate_startup_state()
            
            # 3. Trigger SL and ensure action fires correctly
            action = bot.risk_manager.check_sl_tp(bot.total_entry_premium, 89.88, -0.0288)
            time_in_trade_seconds = time.time() - bot._trade_start_ts
            
            if action == "TRAILING_SL_EXIT" and time_in_trade_seconds > 15:
                print(f"Recovery #{i} PASS")
                success_count += 1
            else:
                print(f"Recovery #{i} FAIL (Action: {action}, Time: {time_in_trade_seconds})")
                break
                
        except Exception as e:
            print(f"Recovery #{i} FAIL (Exception: {e})")
            break

except KeyboardInterrupt:
    pass

print(f"\nStress Test Complete: {success_count}/20 successful recoveries.")
print("--- END PHASE 6 ---")
