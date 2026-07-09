import time
import logging
from unittest.mock import patch, MagicMock

# Force paper mode for safety
import os
os.environ['BOT_MODE'] = 'PAPER'

import config
from bot_engine import DeltaTradingEngine as BotEngine
from execution_engine import ExecutionEngine
from data_fetcher import DataFetcher
from risk_manager import RiskManager
from logger import app_logger

def simulate_profit_run():
    print("\n--- Starting Dynamic Profit Lock Integration Test ---\n")
    
    # Setup mock components
    mock_api = MagicMock()
    mock_api.ws_connected = True
    
    bot = BotEngine(mock_api)
    
    # Mock the notifier so we can intercept alerts
    bot.notifier = MagicMock()
    
    # Override constraints so it takes a trade immediately
    bot.trades_taken_today = 0
    
    # Inject a fake active position
    # Let's say entry premium collected was $1000 total (for easy math)
    # Entry price = 1000
    fake_pos = {
        'C-BTC-60000': {'size': 1, 'entry_price': 500, 'side': 'sell'},
        'P-BTC-50000': {'size': 1, 'entry_price': 500, 'side': 'sell'}
    }
    bot.execution.active_positions = fake_pos
    bot.total_entry_premium = 1000.0  # $1000 collected
    bot._trade_start_ts = time.time() - 60  # Bypass the 30s MIN_HOLD_SECONDS
    
    def trigger_tick(current_value, expected_action, expected_locked_sl):
        profit = 1000.0 - current_value
        pnl_pct = profit / 1000.0
        
        # Manually invoke the exact logic from bot_engine.py
        action = bot.risk_manager.check_sl_tp(1000.0, current_value, pnl_pct)
        
        trail_state = bot.risk_manager.get_trailing_state()
        peak = trail_state['highest_profit_pct']
        sl = trail_state['current_trailing_sl']
        confirmed = trail_state['trailing_confirmed']
        
        print(f"P&L: {pnl_pct*100:5.1f}% | Peak: {peak:5.1f}% | SL Locked: {sl if sl else 0:5.1f}% | Confirmed: {confirmed} | Action: {action}")
        
        if expected_locked_sl is not None:
            assert abs(sl - expected_locked_sl) < 0.001, f"Expected SL {expected_locked_sl}, got {sl}"
        if expected_action is not None:
            assert action == expected_action, f"Expected action {expected_action}, got {action}"
            
        return action

    # 1. 0% Profit -> current value = 1000
    trigger_tick(1000, None, None)
    
    # 2. 10% Profit -> current value = 900
    trigger_tick(900, None, None)
    
    # 3. 16% Profit -> current value = 840 (Touches 15%, confirmation starts)
    trigger_tick(840, None, None)
    
    # 4. 20% Profit -> current value = 800 (19% reached! Capital protection locks at 5%, then 20% tier locks at 12%)
    trigger_tick(800, None, 12.0)
    
    # 5. Drop to 15% Profit -> current value = 850 (Should do nothing, SL remains 12%)
    trigger_tick(850, None, 12.0)
    
    # 6. Drop to 11% Profit -> current value = 890 (Hits 12% SL! Should exit)
    action = trigger_tick(890, "TRAILING_SL_EXIT", 12.0)
    if action == "TRAILING_SL_EXIT":
        print("\n✅ SUCCESS: Trade correctly exited at 12% locked profit after pulling back from 20% peak!")
        
    print("\n--- Resetting for massive run test ---\n")
    bot.risk_manager.reset_trailing_state()
    bot._trade_start_ts = time.time() - 60
    
    # 1. Skip straight to 35% profit -> current value = 650
    # Should blow past 30% without hitting a hard TP, and lock at dynamic trail (35 - 5 = 30%)
    trigger_tick(650, None, 30.0)
    
    # 2. Go to 50% profit -> current value = 500
    # Should lock at dynamic trail (50 - 5 = 45%)
    trigger_tick(500, None, 45.0)
    
    # 3. Pullback to 46% profit -> current value = 540
    # Should do nothing, SL stays at 45%
    trigger_tick(540, None, 45.0)
    
    # 4. Pullback to 44% profit -> current value = 560
    # Should hit SL!
    action = trigger_tick(560, "TRAILING_SL_EXIT", 45.0)
    
    if action == "TRAILING_SL_EXIT":
        print("\n✅ SUCCESS: Massive trade ran to 50% without hitting hard TP, and correctly exited at 45% locked profit!")

if __name__ == "__main__":
    simulate_profit_run()
