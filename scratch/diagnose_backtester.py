import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtester import AdvancedBacktester
import json

def main():
    backtester = AdvancedBacktester(starting_capital=50000.0)
    aligned_data = backtester._load_real_data()
    print(f"Total historical days available: {len(aligned_data)}")
    
    # Run the backtester for 365 days and print details
    results = backtester.run(days=365)
    print("\n--- Diagnostic Metrics ---")
    print(json.dumps(results['metrics'], indent=2))
    
    print("\n--- Diagnostic Trade Log (First 15 trades) ---")
    for idx, t in enumerate(backtester.trades[:15]):
        print(f"Trade {idx+1} | Date: {t['date']} | BTC Open: {t['btc_price']} | DVOL: {t['dvol']}% (Pct: {t['dvol_percentile']}%)")
        print(f"  * Strikes Chosen: Call {t['call_strike']} | Put {t['put_strike']}")
        print(f"  * Entry Premium: {t['premium_collected']} USDT")
        print(f"  * Intraday Range: Low {t['btc_low']} - High {t['btc_high']} (Close {t['btc_close']})")
        print(f"  * PnL: {t['pnl_pct']}% (${t['pnl_usd']}) | Exit Reason: {t['exit_reason']} | Hedge Triggered: {t['hedge_triggered']}")
        print("-" * 60)

if __name__ == '__main__':
    main()

