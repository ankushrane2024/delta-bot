import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_client import DeltaIndiaClient
from utils import get_next_expiry_date
from strategy import ShortStrangleStrategy
import logging

def main():
    client = DeltaIndiaClient()
    strat = ShortStrangleStrategy(client)
    expiry = get_next_expiry_date()
    
    print(f"Expiry: {expiry}")
    res = client.get_tickers({
        'contract_types': 'call_options,put_options',
        'underlying_asset_symbol': 'BTC'
    })
    tickers = res.get('result', [])
    expiry_tickers = [t for t in tickers if expiry in t.get('symbol', '') and '-BTC-' in t.get('symbol', '')]
    
    # Get spot
    spot = 0.0
    for t in expiry_tickers:
        spot = float(t.get('spot_price') or t.get('greeks', {}).get('spot') or 0)
        if spot > 0:
            break
            
    all_strikes = sorted(list(set(float(t.get('strike_price', 0)) for t in expiry_tickers if t.get('strike_price'))))
    ATM = min(all_strikes, key=lambda s: abs(s - spot))
    atm_idx = all_strikes.index(ATM)
    
    print(f"Spot: {spot}")
    print(f"ATM: {ATM} (index {atm_idx})")
    print(f"Strike at index atm_idx + 5: {all_strikes[atm_idx + 5] if atm_idx + 5 < len(all_strikes) else 'N/A'}")
    print(f"Strike at index atm_idx - 5: {all_strikes[atm_idx - 5] if atm_idx - 5 >= 0 else 'N/A'}")
    
    call_opt, put_opt = strat.find_strikes(expiry_date=expiry, check_premium=True)
    print(f"Selected Call Strike: {call_opt['strike'] if call_opt else 'None'}")
    print(f"Selected Put Strike: {put_opt['strike'] if put_opt else 'None'}")

if __name__ == "__main__":
    main()
