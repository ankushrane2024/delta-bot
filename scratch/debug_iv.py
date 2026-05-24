"""
Debug script — check what IV-related fields Delta India API actually returns.
Run from project root: python scratch/debug_iv.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_client import DeltaIndiaClient

client = DeltaIndiaClient()
res = client.get_tickers({'contract_types': 'call_options,put_options', 'underlying_asset_symbol': 'BTC'})

if not res.get('success'):
    print("API call failed:", res)
    sys.exit(1)

tickers = res.get('result', [])
print(f"Total BTC option tickers returned: {len(tickers)}")

if not tickers:
    print("No tickers found!")
    sys.exit(1)

# Print all keys from the first ticker
sample = tickers[0]
print("\n--- Sample ticker keys ---")
for k, v in sample.items():
    print(f"  {k}: {v}")

# Scan mark_iv across all tickers
print("\n--- mark_iv values (first 10) ---")
for t in tickers[:10]:
    sym = t.get('symbol','?')
    mark_iv = t.get('mark_iv', 'MISSING')
    close = t.get('close', 0)
    mark_price = t.get('mark_price', 0)
    greeks = t.get('greeks') or {}
    print(f"  {sym}: mark_iv={mark_iv}, close={close}, mark_price={mark_price}, greeks_keys={list(greeks.keys())}")

# Count how many have non-zero mark_iv
non_zero = [t for t in tickers if float(t.get('mark_iv', 0) or 0) > 0]
print(f"\nTickers with non-zero mark_iv: {len(non_zero)} / {len(tickers)}")

if non_zero:
    ivs = [float(t['mark_iv']) for t in non_zero]
    print(f"IV range: {min(ivs):.4f} to {max(ivs):.4f}, avg: {sum(ivs)/len(ivs):.4f}")
