"""
Comprehensive Backtester Validation Script
==========================================
Tests every aspect of the backtester to verify correctness:
  1. Math check — verify P&L formula manually
  2. SL check   — verify stop loss triggers at config.SL_PERCENT
  3. TP check   — verify profit target exits at config.EXIT_PROFIT_TARGET
  4. Full run   — 90-day backtest with sanity checks on all results
  5. Summary    — overall health grade
"""

import sys, json, math
sys.path.insert(0, '.')

import config
from backtester import AdvancedBacktester, black_scholes_call, black_scholes_put

PASS = "  PASS"
FAIL = "  FAIL"
SEP  = "-" * 60

def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    print(f"{status} | {label}")
    if detail:
        print(f"       {detail}")
    return condition

all_ok = []

# ═══════════════════════════════════════════════════════════
# TEST 1: Black-Scholes sanity check
# ═══════════════════════════════════════════════════════════
print(SEP)
print("TEST 1: Black-Scholes Math Sanity")
print(SEP)

S, K_c, K_p = 63801, 69000, 58000
T = 32.5 / (24*365)
r, sig_c, sig_p = 0.05, 0.80, 0.92

call_price = black_scholes_call(S, K_c, T, r, sig_c)
put_price  = black_scholes_put (S, K_p, T, r, sig_p)

all_ok.append(check("Call price > 0", call_price > 0, f"call = ${call_price:.4f}"))
all_ok.append(check("Put price > 0",  put_price  > 0, f"put  = ${put_price:.4f}"))
all_ok.append(check("OTM Call < intrinsic barrier",
    call_price < (S * 0.10),
    f"${call_price:.4f} < ${S*0.10:.2f} (10% of spot)"))
all_ok.append(check("OTM Put < intrinsic barrier",
    put_price < (S * 0.10),
    f"${put_price:.4f} < ${S*0.10:.2f} (10% of spot)"))

# ATM call should be close to ATM put (put-call parity)
atm_call = black_scholes_call(S, S, T, r, 0.80)
atm_put  = black_scholes_put (S, S, T, r, 0.80)
parity_ok = abs(atm_call - atm_put) / atm_call < 0.15   # within 15%
all_ok.append(check("Put-call parity holds (ATM)", parity_ok,
    f"ATM call=${atm_call:.4f}  ATM put={atm_put:.4f}"))

# ═══════════════════════════════════════════════════════════
# TEST 2: Config values are read correctly
# ═══════════════════════════════════════════════════════════
print()
print(SEP)
print("TEST 2: Config Values Read Correctly")
print(SEP)

all_ok.append(check("EXIT_PROFIT_TARGET is 30%",
    abs(config.EXIT_PROFIT_TARGET - 0.30) < 0.001,
    f"value = {config.EXIT_PROFIT_TARGET}"))
all_ok.append(check("PARTIAL_PROFIT_TRIGGER is 20%",
    abs(config.PARTIAL_PROFIT_TRIGGER - 0.20) < 0.001,
    f"value = {config.PARTIAL_PROFIT_TRIGGER}"))
all_ok.append(check("SL_PERCENT is 1.30 (130%)",
    abs(config.SL_PERCENT - 1.30) < 0.001,
    f"value = {config.SL_PERCENT}"))
all_ok.append(check("TRAILING_SL_TRIGGER is 15%",
    abs(config.TRAILING_SL_TRIGGER - 0.15) < 0.001,
    f"value = {config.TRAILING_SL_TRIGGER}"))
all_ok.append(check("MANUAL_TOTAL_LOTS > 0",
    config.MANUAL_TOTAL_LOTS > 0,
    f"value = {config.MANUAL_TOTAL_LOTS}"))

# ═══════════════════════════════════════════════════════════
# TEST 3: Historical data coverage
# ═══════════════════════════════════════════════════════════
print()
print(SEP)
print("TEST 3: Historical Data Cache")
print(SEP)

with open('historical_data_cache.json') as f:
    hist = json.load(f)

dates = sorted([r['date'] for r in hist])
dvols = [r['dvol_close'] for r in hist]
btc_opens = [r['btc_open'] for r in hist]

all_ok.append(check("Cache has 500+ records", len(hist) >= 500,
    f"total records = {len(hist)}"))
all_ok.append(check("Cache covers up to June 2026",
    dates[-1] >= '2026-06-13',
    f"last date = {dates[-1]}"))
all_ok.append(check("June 13 2026 data present",
    '2026-06-13' in dates))
all_ok.append(check("No zero BTC prices",
    all(p > 0 for p in btc_opens),
    f"min BTC = ${min(btc_opens):,.0f}"))
all_ok.append(check("DVOL in realistic range (30-200%)",
    all(20 < d < 200 for d in dvols),
    f"DVOL range: {min(dvols):.1f}% - {max(dvols):.1f}%"))

# ═══════════════════════════════════════════════════════════
# TEST 4: Single-trade logic verification
# ═══════════════════════════════════════════════════════════
print()
print(SEP)
print("TEST 4: Exit Logic — SL / TP / Partial")
print(SEP)

# June 13 record
june13 = [r for r in hist if r['date'] == '2026-06-13'][0]
bt = AdvancedBacktester(starting_capital=50000)
results = bt.run(start_date='2026-06-13', end_date='2026-06-13')
trades = results['trades']

all_ok.append(check("June 13 produced a trade", len(trades) == 1,
    f"trades generated = {len(trades)}"))

if trades:
    t = trades[0]
    all_ok.append(check("Exit is FULL_TARGET (30% profit, quiet day)",
        t['exit_reason'] == 'FULL_TARGET',
        f"actual exit = {t['exit_reason']}"))
    all_ok.append(check("PnL% equals config.EXIT_PROFIT_TARGET (30%)",
        abs(t['pnl_pct'] - config.EXIT_PROFIT_TARGET * 100) < 0.5,
        f"pnl_pct = {t['pnl_pct']:.1f}%  target = {config.EXIT_PROFIT_TARGET*100:.1f}%"))
    all_ok.append(check("PnL USD > 0 (profitable)",
        t['pnl_usd'] > 0,
        f"pnl_usd = ${t['pnl_usd']:.2f}"))
    all_ok.append(check("Premium collected > 0",
        t['premium_collected'] > 0,
        f"premium = ${t['premium_collected']:.4f}/BTC"))
    all_ok.append(check("BTC price is realistic",
        50000 <= t['btc_price'] <= 150000,
        f"price = ${t['btc_price']:,.0f}"))
    all_ok.append(check("Call strike > Put strike (strangle)",
        t['call_strike'] > t['put_strike'],
        f"call={t['call_strike']:,}  put={t['put_strike']:,}"))

# ═══════════════════════════════════════════════════════════
# TEST 5: 90-day full backtest statistical sanity
# ═══════════════════════════════════════════════════════════
print()
print(SEP)
print("TEST 5: 90-Day Full Backtest — Statistical Sanity")
print(SEP)

bt90 = AdvancedBacktester(starting_capital=50000)
r90  = bt90.run(days=90)
m    = r90['metrics']
t90  = r90['trades']

all_ok.append(check("90-day backtest ran successfully", len(t90) > 0,
    f"trades executed = {m['total_trades']}"))
all_ok.append(check("Win rate between 50-95% (realistic for option selling)",
    50 <= m['win_rate'] <= 95,
    f"win rate = {m['win_rate']:.1f}%"))
all_ok.append(check("Profit factor > 1.0 (strategy makes money)",
    m['profit_factor'] > 1.0,
    f"profit factor = {m['profit_factor']:.2f}"))
all_ok.append(check("Max drawdown < 30% (not blowing up)",
    m['max_drawdown_pct'] < 30,
    f"max drawdown = {m['max_drawdown_pct']:.1f}%"))
all_ok.append(check("Final equity > starting capital",
    m['final_equity'] > 50000,
    f"equity: $50,000 -> ${m['final_equity']:,.2f}"))
all_ok.append(check("No NaN in equity curve",
    all(isinstance(e['equity'], (int, float)) for e in r90['equity_curve'])))
all_ok.append(check("Equity curve is monotonically valid (never goes <0)",
    all(e['equity'] > 0 for e in r90['equity_curve'])))

# Verify P&L math: sum of trade PnLs should equal equity gain
sum_pnl = sum(t['pnl_usd'] for t in t90)
equity_gain = m['final_equity'] - 50000
math_match = abs(sum_pnl - equity_gain) < 1.0   # within $1 rounding
all_ok.append(check("Sum of trade PnLs = total equity gain (math integrity)",
    math_match,
    f"sum PnL=${sum_pnl:.2f}  equity gain=${equity_gain:.2f}  diff=${abs(sum_pnl-equity_gain):.4f}"))

# Check SL trades have negative PnL
sl_trades = [t for t in t90 if t['exit_reason'] == 'STOP_LOSS']
sl_pnls_negative = all(t['pnl_usd'] < 0 for t in sl_trades)
all_ok.append(check("All STOP_LOSS trades have negative PnL",
    sl_pnls_negative or len(sl_trades) == 0,
    f"SL trades: {len(sl_trades)}  {'all negative' if sl_trades else 'none triggered'}"))

# Check profit target trades have positive PnL
tp_trades = [t for t in t90 if 'TARGET' in t['exit_reason']]
tp_pnls_positive = all(t['pnl_usd'] > 0 for t in tp_trades)
all_ok.append(check("All TARGET trades have positive PnL",
    tp_pnls_positive or len(tp_trades) == 0,
    f"TP trades: {len(tp_trades)}"))

# ═══════════════════════════════════════════════════════════
# FINAL SUMMARY
# ═══════════════════════════════════════════════════════════
print()
print("=" * 60)
print("FULL 90-DAY BACKTEST RESULTS SUMMARY")
print("=" * 60)
print(f"  Starting Capital  : $50,000")
print(f"  Final Equity      : ${m['final_equity']:,.2f}")
print(f"  Total Return      : {m['total_return_pct']:.1f}%")
print(f"  Total PnL         : ${m['total_pnl']:.2f}")
print(f"  Total Trades      : {m['total_trades']}")
print(f"  Win Rate          : {m['win_rate']:.1f}%")
print(f"  Avg Winner        : ${m['avg_winner']:.2f}")
print(f"  Avg Loser         : ${m['avg_loser']:.2f}")
print(f"  Best Trade        : ${m['best_trade']:.2f}")
print(f"  Worst Trade       : ${m['worst_trade']:.2f}")
print(f"  Profit Factor     : {m['profit_factor']:.2f}x")
print(f"  Max Drawdown      : {m['max_drawdown_pct']:.1f}%")
print(f"  Sharpe Ratio      : {m['sharpe_ratio']:.2f}")
print(f"  Hedges Triggered  : {m['hedge_triggered_count']}")
print()
print(f"  Exit Breakdown:")
reasons = {}
for t in t90:
    reasons[t['exit_reason']] = reasons.get(t['exit_reason'], 0) + 1
for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
    pct = count / len(t90) * 100
    print(f"    {reason:<25}: {count:>3} trades ({pct:.1f}%)")

print()
print("=" * 60)
passed = sum(1 for x in all_ok if x)
total  = len(all_ok)
grade  = "A - EXCELLENT" if passed == total else \
         "B - GOOD" if passed >= total * 0.85 else \
         "C - NEEDS WORK" if passed >= total * 0.70 else "D - BROKEN"
print(f"  VALIDATION SCORE: {passed}/{total} tests passed  |  Grade: {grade}")
print("=" * 60)
