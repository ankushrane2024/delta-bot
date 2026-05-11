import requests as _requests
import json

DELTA_INDIA_BASE = "https://api.india.delta.exchange"

def check_symbols():
    url = f"{DELTA_INDIA_BASE}/v2/tickers"
    params = {
        'contract_types': 'call_options,put_options',
        'underlying_asset_symbol': 'BTC'
    }
    try:
        r = _requests.get(url, params=params, timeout=15).json()
        if r.get('success'):
            res = r.get('result', [])
            print(f"Total tickers: {len(res)}")
            if res:
                print("First 5 symbols:")
                for t in res[:5]:
                    print(f" - {t.get('symbol')} (Type: {t.get('contract_type')})")
                
                # Check for specific dates
                # Today is 11 May. Next expiry is likely 12 May.
                # Symbols might be like C-BTC-120526-70000 or similar.
                expiries = set()
                for t in res:
                    sym = t.get('symbol', '')
                    parts = sym.split('-')
                    if len(parts) >= 3:
                        expiries.add(parts[2])
                print(f"Unique Expiries found: {sorted(list(expiries))}")
        else:
            print(f"API Error: {r.get('error')}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    check_symbols()
