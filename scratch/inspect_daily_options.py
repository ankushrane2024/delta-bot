import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_client import DeltaIndiaClient
from utils import get_next_expiry_date
import json

def main():
    client = DeltaIndiaClient()
    expiry = get_next_expiry_date()
    print(f"Target Expiry: {expiry}")
    
    res = client.get_tickers({
        'contract_types': 'call_options,put_options',
        'underlying_asset_symbol': 'BTC'
    })
    if not res.get('success'):
        print("Failed to fetch tickers.")
        return
        
    tickers = res.get('result', [])
    expiry_tickers = [t for t in tickers if expiry in t.get('symbol', '') and '-BTC-' in t.get('symbol', '')]
    print(f"Total expiry tickers: {len(expiry_tickers)}")
    
    # Get Spot Price
    spot = 0.0
    for t in expiry_tickers:
        spot = float(t.get('spot_price') or t.get('greeks', {}).get('spot') or 0)
        if spot > 0:
            break
    print(f"BTC Spot Price: {spot}")
    
    # List Call strikes sorted
    calls = sorted([t for t in expiry_tickers if 'call' in t.get('contract_type', '').lower()], key=lambda x: float(x.get('strike_price', 0)))
    puts = sorted([t for t in expiry_tickers if 'put' in t.get('contract_type', '').lower()], key=lambda x: float(x.get('strike_price', 0)))
    
    print("\n--- CALL OPTIONS ---")
    for c in calls[:30]:
        strike = float(c.get('strike_price', 0))
        delta = float(c.get('greeks', {}).get('delta', 0))
        mp = float(c.get('mark_price', 0))
        premium_inr = mp * 83.0
        print(f"Symbol: {c['symbol']} | Strike: {strike} | Mark Price: {mp:.4f} | Premium INR: {premium_inr:.2f} | Delta: {delta:.4f}")
        
    print("\n--- PUT OPTIONS ---")
    for p in puts[:30]:
        strike = float(p.get('strike_price', 0))
        delta = float(p.get('greeks', {}).get('delta', 0))
        mp = float(p.get('mark_price', 0))
        premium_inr = mp * 83.0
        print(f"Symbol: {p['symbol']} | Strike: {strike} | Mark Price: {mp:.4f} | Premium INR: {premium_inr:.2f} | Delta: {delta:.4f}")

if __name__ == "__main__":
    main()
