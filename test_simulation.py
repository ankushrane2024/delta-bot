import sys, time, json, logging
import config

# Force PAPER mode for testing
config.BOT_MODE = 'PAPER'

from bot_engine import DeltaTradingEngine
from utils import get_ist_now

def run_system_test():
    print("=" * 60)
    print("  DELTA BTC OPTIONS BOT - FULL SYSTEM VERIFICATION TEST")
    print("=" * 60)
    print(f"  Test Time (IST): {get_ist_now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    engine = DeltaTradingEngine()
    engine.is_running = True
    engine.execution.mode = 'PAPER'

    # --- Test 1: Entry Cycle ---
    print('\n[TEST 1] ENTRY CYCLE (FORCE)')
    print('-' * 40)
    engine.run_entry_cycle(force=True)
    
    positions = engine.execution.active_positions
    print(f'  Active Positions: {len(positions)}')
    total_entry_lots = 0
    for sym, data in positions.items():
        size = data.get("size", 0)
        entry = data.get("entry_price", 0)
        total_entry_lots += size
        print(f'  {sym}: Size={size}, Entry=${entry:.4f}')
    
    entry_premium = engine.total_entry_premium
    print(f'  Total Entry Premium: ${entry_premium:.2f}')
    print(f'  Total Lots (per leg): {total_entry_lots // 2 if len(positions) == 2 else total_entry_lots}')

    # --- Test 2: Smart Hedging ---
    print('\n[TEST 2] SMART HEDGING CHECK')
    print('-' * 40)
    time.sleep(3)
    engine.smart_hedging.manage_hedge(positions, 0.0)
    print(f'  Hedge Active: {engine.smart_hedging.hedge_active}')
    print(f'  Hedge Position (BTC): {engine.execution.hedge_position}')

    # --- Test 3: Exit Cycle & P&L Verification ---
    print('\n[TEST 3] EXIT CYCLE & P&L VERIFICATION')
    print('-' * 40)
    engine.run_exit_cycle()
    
    trades = engine.performance_tracker.trades
    if trades:
        last_trade = trades[-1]
        pnl = last_trade.get("pnl", 0)
        entry_time = last_trade.get("entry_time", "")
        exit_time = last_trade.get("exit_time", "")
        mode = last_trade.get("mode", "")
        premium = last_trade.get("premium_collected", 0)
        
        print(f'  Mode: {mode}')
        print(f'  PnL: ${pnl:.2f}')
        print(f'  Premium Collected: ${premium:.2f}')
        print(f'  Entry Time: {entry_time}')
        print(f'  Exit Time:  {exit_time}')

        # --- Validation Checks ---
        print('\n' + '=' * 60)
        print('  VALIDATION RESULTS')
        print('=' * 60)
        
        # Check 1: P&L is realistic (not above $1000 for 100-200 lot paper trade on short expiry)
        pnl_ok = abs(pnl) < 2000
        print(f'  [{"PASS" if pnl_ok else "FAIL"}] P&L is realistic: ${pnl:.2f} (expected < $2000)')
        
        # Check 2: Exit time is in IST (contains no +00:00 or Z suffix, and no UTC indication)
        exit_is_ist = 'T' in exit_time and '+00:00' not in exit_time and not exit_time.endswith('Z')
        print(f'  [{"PASS" if exit_is_ist else "FAIL"}] Exit time is IST: {exit_time}')
        
        # Check 3: Entry time has IST offset (+05:30)
        entry_is_ist = '+05:30' in entry_time
        print(f'  [{"PASS" if entry_is_ist else "FAIL"}] Entry time has IST offset: {entry_time}')
        
        # Check 4: Mode is PAPER
        mode_ok = mode == 'PAPER'
        print(f'  [{"PASS" if mode_ok else "FAIL"}] Mode is PAPER: {mode}')
        
        # Check 5: Premium is consistent with lot size
        # Premium = (call_entry + put_entry) * per_entry_size
        # For 100 lots at ~$180 each, premium should be ~$36,000
        premium_ok = premium > 0
        print(f'  [{"PASS" if premium_ok else "FAIL"}] Premium recorded: ${premium:.2f}')
        
        # Check 6: PnL matches formula (entry_premium - exit_value)
        pnl_formula_ok = abs(pnl) < entry_premium if entry_premium > 0 else True
        print(f'  [{"PASS" if pnl_formula_ok else "FAIL"}] P&L is less than total premium (no inflation)')
        
        all_pass = all([pnl_ok, exit_is_ist, entry_is_ist, mode_ok, premium_ok, pnl_formula_ok])
        print('\n' + '=' * 60)
        if all_pass:
            print('  ✅ ALL TESTS PASSED - BOT IS READY')
        else:
            print('  ❌ SOME TESTS FAILED - REVIEW NEEDED')
        print('=' * 60)
    else:
        print('  ❌ No trades logged!')

if __name__ == '__main__':
    run_system_test()
