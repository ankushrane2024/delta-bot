import sys
sys.path.insert(0, '.')
from backtester import AdvancedBacktester
import config

# Actual June 13 trade
ACTUAL_PREMIUM = 49.92
ACTUAL_PNL     = 29.90
ACTUAL_PNL_PCT = 29.90 / 49.92
ACTUAL_REASON  = 'Profit Target Hit (30%)'

print("=== ACTUAL TRADE (June 13) ===")
print(f"Premium Collected : ${ACTUAL_PREMIUM:.2f}")
print(f"Net PnL           : +${ACTUAL_PNL:.2f}")
print(f"PnL %             : {ACTUAL_PNL_PCT*100:.1f}%")
print(f"Exit Reason       : {ACTUAL_REASON}")
print()

# Run backtest for June 13 only
bt = AdvancedBacktester(starting_capital=50000)
results = bt.run(start_date='2026-06-13', end_date='2026-06-13')
trades = results['trades']

print("=== BACKTESTER OUTPUT (June 13) ===")
if not trades:
    print("No trades - probably filtered by DVOL percentile. Check DVOL_PERCENTILE_MIN/MAX in config.")
    import json
    with open('historical_data_cache.json') as f:
        data = json.load(f)
    rec = [r for r in data if r['date'] == '2026-06-13']
    if rec:
        r = rec[0]
        print(f"DVOL: {r['dvol_close']:.2f}  |  Percentile: {r['dvol_percentile']:.1f}")
        print(f"Config DVOL_PERCENTILE_MIN={config.DVOL_PERCENTILE_MIN}  MAX={config.DVOL_PERCENTILE_MAX}")
else:
    t = trades[0]
    btc_qty = t['lots'] * config.LOT_TO_BTC
    total_prem = t['premium_collected'] * btc_qty

    print(f"BTC Open          : ${t['btc_price']:,.0f}")
    print(f"DVOL              : {t['dvol']:.2f}%")
    print(f"DVOL Percentile   : {t['dvol_percentile']:.1f}%")
    print(f"Call Strike       : ${t['call_strike']:,}")
    print(f"Put Strike        : ${t['put_strike']:,}")
    print(f"Premium per BTC   : ${t['premium_collected']:.4f}")
    print(f"Lots              : {t['lots']}")
    print(f"Total Premium USD : ${total_prem:.2f}")
    print(f"PnL %             : {t['pnl_pct']:.1f}%")
    print(f"Net PnL USD       : ${t['pnl_usd']:.2f}")
    print(f"Exit Reason       : {t['exit_reason']}")
    print(f"Hedge Triggered   : {t['hedge_triggered']}")
    print()
    print("=== COMPARISON ===")
    print(f"Actual PnL%   : {ACTUAL_PNL_PCT*100:.1f}%  |  Backtest PnL%  : {t['pnl_pct']:.1f}%")
    diff = abs(ACTUAL_PNL_PCT*100 - t['pnl_pct'])
    print(f"Difference    : {diff:.1f}%  ({'GOOD - within tolerance' if diff < 20 else 'NEEDS REVIEW'})")
    print()
    match_reason = 'TARGET' in t['exit_reason']
    print(f"Exit reason match: {'YES - both hit profit target' if match_reason else 'NO - ' + t['exit_reason']}")
