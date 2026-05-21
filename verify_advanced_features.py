import sys
import os
import requests
import json
from backtester import AdvancedBacktester

def main():
    print("====================================================")
    print("      Delta BTC Options Bot - Verification Run      ")
    print("====================================================")
    
    # 1. Test AdvancedBacktester directly
    print("\n1. Testing AdvancedBacktester directly...")
    try:
        backtester = AdvancedBacktester(starting_capital=50000.0)
        results = backtester.run(days=90)
        
        metrics = results.get('metrics', {})
        print("   [SUCCESS] Backtester completed successfully.")
        print(f"   - Total Trades: {metrics.get('total_trades')}")
        print(f"   - Win Rate: {metrics.get('win_rate')}%")
        print(f"   - Total PnL: ${metrics.get('total_pnl')}")
        print(f"   - Profit Factor: {metrics.get('profit_factor')}")
        print(f"   - Max Drawdown: {metrics.get('max_drawdown_pct')}%")
        print(f"   - Sharpe Ratio: {metrics.get('sharpe_ratio')}")
        print(f"   - Total Return: {metrics.get('total_return_pct')}%")
        print(f"   - Hedges Triggered: {metrics.get('hedge_triggered_count')}")
    except Exception as e:
        print(f"   [FAIL] Backtester direct test failed: {e}")
        import traceback
        traceback.print_exc()

    # 2. Test Local REST APIs
    base_url = "http://127.0.0.1:5000"
    print(f"\n2. Querying running Web Dashboard at {base_url}...")
    
    # 2a. Check /api/status
    try:
        r = requests.get(f"{base_url}/api/status", timeout=5)
        if r.status_code == 200:
            data = r.json()
            print("   [SUCCESS] /api/status is responsive.")
            print(f"   - Mode: {data.get('mode')}")
            print(f"   - Equity: ${data.get('equity')}")
            print(f"   - Rule Compliance: {data.get('rule_report', {}).get('compliance', 'N/A') if isinstance(data.get('rule_report'), dict) else 'N/A'}%")
            print(f"   - Current IV: {data.get('current_iv')}%")
            print(f"   - Size Multiplier: {data.get('size_multiplier')}x")
            
            dvol_status = data.get('dvol_status') or {}
            print(f"   - DVOL Level: {dvol_status.get('current_dvol')}% (Percentile: {dvol_status.get('dvol_percentile')}%)")
            
            hedge_status = data.get('hedge_status') or {}
            print(f"   - Smart Hedging Status: {hedge_status.get('status', 'N/A')} (Delta: {hedge_status.get('net_delta', 0.0)})")
        else:
            print(f"   [FAIL] /api/status returned status code {r.status_code}")
    except Exception as e:
        print(f"   [FAIL] /api/status connection failed: {e}")

    # 2b. Check /api/trade_probability
    try:
        r = requests.get(f"{base_url}/api/trade_probability", timeout=5)
        if r.status_code == 200:
            data = r.json()
            print("   [SUCCESS] /api/trade_probability is responsive.")
            print(f"   - Tomorrow Day: {data.get('tomorrow_day')}")
            print(f"   - Probability of Trading: {data.get('probability')}%")
            print(f"   - Verdict: {data.get('verdict')}")
            print("   - Factors Checked:")
            for factor in data.get('factors', []):
                print(f"     * {factor.get('name')}: {factor.get('score')}/{factor.get('max')} - {factor.get('label')}")
        else:
            print(f"   [FAIL] /api/trade_probability returned status code {r.status_code}")
    except Exception as e:
        print(f"   [FAIL] /api/trade_probability connection failed: {e}")

    # 2c. Check /api/backtest
    try:
        payload = {
            "starting_capital": 50000.0,
            "start_date": "2026-02-01",
            "end_date": "2026-05-01"
        }
        r = requests.post(f"{base_url}/api/backtest", json=payload, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get('success'):
                print("   [SUCCESS] /api/backtest POST is responsive.")
                metrics = data.get('metrics', {})
                print(f"   - Backtest Trades: {metrics.get('total_trades')}")
                print(f"   - Total Return: {metrics.get('total_return_pct')}%")
                print(f"   - Equity Curve Data Points: {len(data.get('equity_curve', []))}")
            else:
                print(f"   [FAIL] /api/backtest returned success=False: {data.get('error')}")
        else:
            print(f"   [FAIL] /api/backtest POST returned status code {r.status_code}")
    except Exception as e:
        print(f"   [FAIL] /api/backtest POST connection failed: {e}")

    print("\n====================================================")
    print("              Verification Completed!               ")
    print("====================================================")

if __name__ == '__main__':
    main()
