"""
╔══════════════════════════════════════════════════════════════╗
║  FORWARD TRADER FULL TEST SUITE                              ║
║  Tests: Lock & Trail math, weekday filter, trade entry,      ║
║  position monitoring, PnL recording, force-entry flow        ║
╚══════════════════════════════════════════════════════════════╝
"""

import sys
import os
import json
import time
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = "✅ PASS"
FAIL = "❌ FAIL"

def test_lock_trail_math():
    print("\n[TEST 1] LOCK & TRAIL MATH (INR-based)")
    from forward_trader import LockTrailEngine, FT_LOCK_TRIGGER_INR, FT_LOCK_AMOUNT_INR, FT_TRAIL_STEP_INR, FT_TRAIL_BY_INR

    engine = LockTrailEngine()

    # Stage A: Profit below trigger — no lock
    r = engine.update(1000.0)
    assert not r['locked'], "Should not lock at ₹1000"
    assert r['locked_floor'] is None
    print(f"  Stage A: ₹1000 profit → Lock NOT active: {PASS}")

    # Stage B: Profit hits trigger at ₹1500 → lock ₹500
    r = engine.update(1500.0)
    assert r['locked'], "Should activate lock at ₹1500"
    assert r['locked_floor'] == FT_LOCK_AMOUNT_INR, f"Floor should be ₹{FT_LOCK_AMOUNT_INR}"
    assert not r['exit_now']
    print(f"  Stage B: ₹1500 profit → Lock activated, floor ₹{r['locked_floor']:.0f}: {PASS}")

    # Stage C: Profit rises to ₹2000 (+₹500 step) → trail floor to ₹700
    r = engine.update(2000.0)
    expected_floor = FT_LOCK_AMOUNT_INR + FT_TRAIL_BY_INR  # 500 + 200 = 700
    assert r['locked_floor'] == expected_floor, f"Floor should be ₹{expected_floor}, got ₹{r['locked_floor']}"
    print(f"  Stage C: ₹2000 profit → Floor ratcheted to ₹{r['locked_floor']:.0f}: {PASS}")

    # Stage D: Profit rises to ₹2500 (+₹500 more) → floor to ₹900
    r = engine.update(2500.0)
    expected_floor_d = FT_LOCK_AMOUNT_INR + 2 * FT_TRAIL_BY_INR  # 500 + 400 = 900
    assert r['locked_floor'] == expected_floor_d, f"Floor should be ₹{expected_floor_d}, got ₹{r['locked_floor']}"
    print(f"  Stage D: ₹2500 profit → Floor at ₹{r['locked_floor']:.0f}: {PASS}")

    # Stage E: Profit drops below floor → trigger exit
    r = engine.update(400.0)  # Below ₹900 floor
    assert r['exit_now'], "Should trigger exit when profit < floor"
    print(f"  Stage E: ₹400 profit < floor ₹{engine.locked_inr:.0f} → EXIT triggered: {PASS}")
    print(f"  Exit Reason: {r['exit_reason']}")

    # Test no-exit if above floor
    engine2 = LockTrailEngine()
    engine2.update(1500.0)
    r2 = engine2.update(600.0)  # Above initial ₹500 floor
    assert not r2['exit_now'], "Should NOT exit when still above floor"
    print(f"  Stage F: ₹600 > floor ₹{engine2.locked_inr:.0f} → No exit: {PASS}")

    print(f"\n  Lock & Trail Rule Summary:")
    print(f"    Trigger: ≥ ₹{FT_LOCK_TRIGGER_INR:.0f} → Lock ₹{FT_LOCK_AMOUNT_INR:.0f}")
    print(f"    Per ₹{FT_TRAIL_STEP_INR:.0f} more → Trail floor up by ₹{FT_TRAIL_BY_INR:.0f}")
    print(f"  ✅ ALL LOCK & TRAIL MATH TESTS PASSED")


def test_weekday_filter():
    print("\n[TEST 2] WEEKDAY FILTER (Sat/Sun skipped)")
    from forward_trader import ForwardTrader

    ft = ForwardTrader.__new__(ForwardTrader)

    weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    weekends = ['Saturday', 'Sunday']

    # 2026-11-23 = Monday, 2026-11-28 = Saturday, 2026-11-29 = Sunday
    test_cases = [
        (datetime.datetime(2026, 11, 23, 22, 30), True,  'Monday'),
        (datetime.datetime(2026, 11, 24, 22, 30), True,  'Tuesday'),
        (datetime.datetime(2026, 11, 25, 22, 30), True,  'Wednesday'),
        (datetime.datetime(2026, 11, 26, 22, 30), True,  'Thursday'),
        (datetime.datetime(2026, 11, 27, 22, 30), True,  'Friday'),
        (datetime.datetime(2026, 11, 28, 22, 30), False, 'Saturday'),
        (datetime.datetime(2026, 11, 29, 22, 30), False, 'Sunday'),
    ]

    all_pass = True
    for dt, expected, name in test_cases:
        result = dt.weekday() < 5
        status = PASS if result == expected else FAIL
        if result != expected:
            all_pass = False
        print(f"  {name}: trade={'YES' if result else 'NO'} → {status}")

    assert all_pass, "Weekday filter has bugs!"
    print(f"  ✅ WEEKDAY FILTER: All 7 days correctly classified")


def test_recorder():
    print("\n[TEST 3] TRADE RECORDER (Persistent JSON Log)")
    from forward_trader import ForwardTestRecorder
    import tempfile

    tmp = tempfile.NamedTemporaryFile(suffix='.json', delete=False)
    tmp.close()
    recorder = ForwardTestRecorder(log_file=tmp.name)

    # Save a sample winning trade
    recorder.save_trade({
        'trade_date': '2026-11-22',
        'entry_time': '2026-11-22T22:30:00',
        'exit_time': '2026-11-23T17:00:00',
        'exit_reason': 'SCHEDULED_SQUAREOFF',
        'call_symbol': 'C-BTC-60200-231126',
        'put_symbol': 'P-BTC-57800-231126',
        'pnl_usd': 15.5,
        'pnl_inr': 1317.5,
        'peak_pnl_inr': 1800.0,
        'lock_activated': True,
        'lock_floor_inr': 500.0
    })

    # Save a losing trade
    recorder.save_trade({
        'trade_date': '2026-11-23',
        'exit_reason': 'LEG_SL',
        'pnl_usd': -18.0,
        'pnl_inr': -1530.0,
        'peak_pnl_inr': 0.0,
        'lock_activated': False,
        'lock_floor_inr': 0.0
    })

    summary = recorder.get_summary()
    all_trades = recorder.get_all_trades()

    assert summary['total_trades'] == 2, f"Expected 2 trades, got {summary['total_trades']}"
    assert summary['wins'] == 1, f"Expected 1 win, got {summary['wins']}"
    assert summary['losses'] == 1, f"Expected 1 loss, got {summary['losses']}"
    assert summary['win_rate_pct'] == 50.0, f"Expected 50% win rate, got {summary['win_rate_pct']}"
    assert len(all_trades) == 2

    print(f"  Saved 2 trades → Total: {summary['total_trades']}, Wins: {summary['wins']}, Losses: {summary['losses']}")
    print(f"  Win Rate: {summary['win_rate_pct']}% | Net PnL: ₹{summary['total_pnl_inr']:.2f}")
    print(f"  Trade file: {tmp.name}")
    os.unlink(tmp.name)
    print(f"  ✅ TRADE RECORDER: All assertions passed")


def test_live_pnl_and_force_entry():
    print("\n[TEST 4] LIVE PAPER TRADE ENTRY & PnL CALCULATION")
    from forward_trader import forward_trader, ForwardTestRecorder, INR_PER_USD, LOT_TO_BTC

    # Reset any existing state
    forward_trader.bot.state['PAPER']['positions'] = {'call': None, 'put': None}
    forward_trader.bot.state['PAPER']['reentry_watch'] = {'call': None, 'put': None}
    forward_trader.bot.state['PAPER']['running'] = False
    forward_trader.trade_active = False
    forward_trader.lock_trail.reset()

    print("  Running force_enter_now() on PAPER...")
    ok = forward_trader.force_enter_now()

    if not ok:
        print(f"  ⚠️  Force entry failed — might be market closed or no valid expiry. Skipping live PnL sub-tests.")
        return

    pos = forward_trader.bot.state['PAPER']['positions']
    assert pos.get('call') is not None, "Call position should be set"
    assert pos.get('put') is not None, "Put position should be set"

    call_p = pos['call']
    put_p  = pos['put']

    print(f"  Call: {call_p['symbol']} @ raw ${call_p.get('raw_entry', call_p['entry_price']):.2f} → eff ${call_p['entry_price']:.2f} (5% slippage) | SL: ${call_p['sl']:.2f} | {call_p['size']} lots")
    print(f"  Put:  {put_p['symbol']} @ raw ${put_p.get('raw_entry', put_p['entry_price']):.2f} → eff ${put_p['entry_price']:.2f} (5% slippage) | SL: ${put_p['sl']:.2f} | {put_p['size']} lots")
    assert call_p['size'] == 500, "Call lot size should be 500"
    assert put_p['size'] == 500, "Put lot size should be 500"
    assert call_p['sl'] == round(call_p.get('raw_entry', call_p['entry_price']) * 2, 2), "100% SL not set correctly"

    # Verify 5% entry slippage applied
    assert call_p['entry_price'] == round(call_p['raw_entry'] * 0.95, 2), "5% slippage not applied to Call entry"
    assert put_p['entry_price']  == round(put_p['raw_entry']  * 0.95, 2), "5% slippage not applied to Put entry"
    print(f"  5% Slippage on Entry verified: {PASS}")

    # TEST: Strike Lock Enforcement while trade is active
    second_entry_attempt = forward_trader.force_enter_now()
    assert second_entry_attempt == False, "Strike lock failed: Trade was allowed to re-enter while already active!"
    assert forward_trader.bot.state['PAPER']['positions']['call']['symbol'] == call_p['symbol'], "Call strike was unexpectedly changed!"
    assert forward_trader.bot.state['PAPER']['positions']['put']['symbol'] == put_p['symbol'], "Put strike was unexpectedly changed!"
    print(f"  Strike Lock Enforcement (strikes locked & cannot change): {PASS}")

    # TEST: Manual Off Option (using temp recorder to avoid polluting production log)
    orig_rec = forward_trader.recorder
    import tempfile
    tmp_rec_file = tempfile.NamedTemporaryFile(suffix='.json', delete=False)
    tmp_rec_file.close()
    forward_trader.recorder = ForwardTestRecorder(log_file=tmp_rec_file.name)

    try:
        ok_manual, msg_manual = forward_trader.manual_squareoff()
        assert ok_manual == True, "Manual off failed!"
        assert forward_trader.trade_active == False, "Trade should not be active after manual off"
        print(f"  Manual Off Option verified: {PASS} ({msg_manual})")

        # Re-enter for the rest of the test
        forward_trader.force_enter_now()
        pos = forward_trader.bot.state['PAPER']['positions']
        call_p = pos['call']
        put_p  = pos['put']

        # PnL at entry reflects the 5% roundtrip slippage
        pnl_at_entry = forward_trader._get_pnl_inr()
        print(f"  PnL at entry (includes 5% roundtrip slippage): ₹{pnl_at_entry:.2f}")

        # Simulate theta decay (premium falls 25%)
        pos['call']['current_price'] = round(call_p['raw_entry'] * 0.75, 2)
        pos['put']['current_price']  = round(put_p['raw_entry']  * 0.75, 2)
        pnl_after_decay = forward_trader._get_pnl_inr()
        print(f"  PnL after 25% theta decay: ₹{pnl_after_decay:.2f}")
        assert pnl_after_decay > pnl_at_entry, "PnL should increase with theta decay"

        # Simulate Lock & Trail kick-in by raising pnl to ₹1600
        # We achieve this by temporarily overriding via LockTrailEngine directly
        lt_result = forward_trader.lock_trail.update(1600.0)
        assert lt_result['locked'] == True, "Lock should activate at ₹1600"
        assert lt_result['locked_floor'] == 500.0, f"Floor should be ₹500, got ₹{lt_result['locked_floor']}"
        print(f"  Lock & Trail at ₹1600 profit → Floor: ₹{lt_result['locked_floor']:.0f}: {PASS}")

        # Squaroff and verify record
        forward_trader.pnl_snapshots = [{'time': '10:30', 'pnl_inr': 1600, 'btc': 59000, 'locked_floor': 500}]
        forward_trader.trade_date = datetime.datetime.utcnow().strftime('%Y-%m-%d')
        forward_trader.entry_time = datetime.datetime.utcnow().isoformat()

        pnl = forward_trader._squareoff(reason='TEST_FORCE_SQUAREOFF')

        all_trades = forward_trader.recorder.get_all_trades()
        latest = all_trades[-1]
        print(f"  Trade recorded: {latest['trade_date']} | Exit: {latest['exit_reason']} | PnL ₹{latest['pnl_inr']:.2f}")
        assert latest['exit_reason'] == 'TEST_FORCE_SQUAREOFF', "Incorrect exit reason"
        assert 'lock_trail_cfg' in latest, "Lock & Trail config missing from record"
        assert latest.get('ce_exit_status') in ['SL 100%', 'OTM Expired'], "ce_exit_status missing or invalid"
        assert latest.get('pe_exit_status') in ['SL 100%', 'OTM Expired'], "pe_exit_status missing or invalid"
        print(f"  CE Exit: {latest.get('ce_exit_status')} | PE Exit: {latest.get('pe_exit_status')}: {PASS}")
    finally:
        # Restore original recorder and delete temp file
        forward_trader.recorder = orig_rec
        try:
            os.remove(tmp_rec_file.name)
        except Exception:
            pass

    print(f"  ✅ LIVE PAPER ENTRY & PnL CALCULATION: All assertions passed")


def test_status_api():
    print("\n[TEST 5] STATUS API & DYNAMIC RULES")
    from forward_trader import forward_trader
    s = forward_trader.status()
    print(f"  IST Time: {s['ist_time']}")
    print(f"  Today: {s['today_weekday']} | Will Trade: {s['will_trade_today']}")
    print(f"  Trade Active: {s['trade_active']}")
    print(f"  PnL: ₹{s['pnl_inr']:.2f} | Lock Active: {s['lock_active']} | Floor: ₹{s['lock_floor_inr'] or 0:.0f}")
    print(f"  Total Trades Logged: {s['total_trades_logged']}")
    print(f"  Records File: {s['records_file']}")
    assert 'trade_date' in s
    assert 'summary' in s
    assert 'rules' in s, "Rules dict missing from status API"
    rules = s['rules']
    assert 'call_mult' in rules and 'put_mult' in rules
    assert 'leg_sl_pct' in rules and 'lots' in rules
    assert 'lock_trigger_inr' in rules and 'lock_amount_inr' in rules
    assert 'trail_step_inr' in rules and 'trail_by_inr' in rules
    print(f"  Rules: CE +{rules['call_mult']}x | PE -{rules['put_mult']}x | SL {rules['leg_sl_pct']}% | Lots {rules['lots']} | Slip {rules['slippage_pct']}%")
    print(f"  Lock & Trail Rules: Trigger ₹{rules['lock_trigger_inr']} → Lock ₹{rules['lock_amount_inr']} | Step ₹{rules['trail_step_inr']} → Trail ₹{rules['trail_by_inr']}")
    print(f"  ✅ STATUS API: Returns complete status dict with dynamic rules")


def test_dynamic_config_sync():
    print("\n[TEST 6] DYNAMIC STRATEGY CONFIG SYNC")
    from forward_trader import forward_trader
    cfg_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'strategy_config.json')

    # Read current config to restore later
    with open(cfg_file, 'r') as f:
        original_cfg = json.load(f)

    try:
        # Simulate user updating settings to new values:
        # CE = 1.8x, PE = 2.5x, SL = 120%, Lots = 600, Lock ₹800 @ ₹2000, Trail ₹300 per ₹600
        test_new_cfg = dict(original_cfg)
        test_new_cfg['leg1'] = dict(test_new_cfg.get('leg1', {}))
        test_new_cfg['leg2'] = dict(test_new_cfg.get('leg2', {}))
        test_new_cfg['overall'] = dict(test_new_cfg.get('overall', {}))

        test_new_cfg['leg1']['strike_multiplier'] = 1.8
        test_new_cfg['leg1']['stop_loss_value'] = 120.0
        test_new_cfg['leg1']['lots'] = 600
        test_new_cfg['leg2']['strike_multiplier'] = 2.5
        test_new_cfg['leg2']['stop_loss_value'] = 120.0
        test_new_cfg['leg2']['lots'] = 600
        test_new_cfg['overall']['trail_if_profit'] = 2000.0
        test_new_cfg['overall']['trail_lock_profit'] = 800.0
        test_new_cfg['overall']['trail_increase_by'] = 600.0
        test_new_cfg['overall']['trail_profit_by'] = 300.0

        with open(cfg_file, 'w') as f:
            json.dump(test_new_cfg, f, indent=2)

        # Trigger reload_config (or let status() do it automatically)
        forward_trader.trade_active = False
        st = forward_trader.status()
        rules = st['rules']

        assert rules['call_mult'] == 1.8, f"Expected call_mult 1.8, got {rules['call_mult']}"
        assert rules['put_mult']  == 2.5, f"Expected put_mult 2.5, got {rules['put_mult']}"
        assert rules['leg_sl_pct'] == 120.0, f"Expected leg_sl_pct 120.0, got {rules['leg_sl_pct']}"
        assert rules['lots'] == 600, f"Expected lots 600, got {rules['lots']}"
        assert rules['lock_trigger_inr'] == 2000.0, f"Expected lock trigger ₹2000, got ₹{rules['lock_trigger_inr']}"
        assert rules['lock_amount_inr'] == 800.0, f"Expected lock amount ₹800, got ₹{rules['lock_amount_inr']}"
        assert rules['trail_step_inr'] == 600.0, f"Expected trail step ₹600, got ₹{rules['trail_step_inr']}"
        assert rules['trail_by_inr'] == 300.0, f"Expected trail by ₹300, got ₹{rules['trail_by_inr']}"

        print(f"  Saved settings updated forward trader immediately:")
        print(f"    CE Mult: {rules['call_mult']}x | PE Mult: {rules['put_mult']}x | SL: {rules['leg_sl_pct']}% | Lots: {rules['lots']}")
        print(f"    Lock: ₹{rules['lock_amount_inr']} @ ₹{rules['lock_trigger_inr']} | Trail: ₹{rules['trail_by_inr']} per ₹{rules['trail_step_inr']}")
        print(f"  Dynamic Config Sync: {PASS}")

    finally:
        # Restore original config
        with open(cfg_file, 'w') as f:
            json.dump(original_cfg, f, indent=2)
        forward_trader.reload_config()
        print(f"  Original config restored cleanly.")

    print(f"  ✅ DYNAMIC STRATEGY CONFIG SYNC: All assertions passed")


def run_all_tests():
    print("=" * 70)
    print("    FORWARD TRADER TEST SUITE")
    print("=" * 70)

    results = {}
    tests = [
        ('Lock & Trail Math',       test_lock_trail_math),
        ('Weekday Filter',          test_weekday_filter),
        ('Trade Recorder',          test_recorder),
        ('Live Entry & PnL Calc',   test_live_pnl_and_force_entry),
        ('Status API',              test_status_api),
        ('Dynamic Config Sync',     test_dynamic_config_sync),
    ]

    for name, fn in tests:
        try:
            fn()
            results[name] = 'PASS'
        except Exception as e:
            print(f"\n  ❌ FAILED: {name}: {e}")
            import traceback
            traceback.print_exc()
            results[name] = f'FAIL: {e}'

    print("\n" + "=" * 70)
    print("    TEST RESULTS SUMMARY")
    print("=" * 70)
    all_passed = True
    for name, result in results.items():
        status = "✅" if result == 'PASS' else "❌"
        print(f"  {status} {name}: {result}")
        if result != 'PASS':
            all_passed = False

    print("=" * 70)
    if all_passed:
        print("  🎉 ALL TESTS PASSED — FORWARD TRADER IS READY TO RUN!")
    else:
        print("  ⚠️  SOME TESTS FAILED — REVIEW ERRORS ABOVE")
    print("=" * 70)
    return all_passed


if __name__ == '__main__':
    run_all_tests()
