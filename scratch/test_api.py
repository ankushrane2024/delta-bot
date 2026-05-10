import requests
import json

base = "https://api.india.delta.exchange"
print("Testing /v2/tickers for options...")
r = requests.get(f"{base}/v2/tickers", params={
    'contract_types': 'call_options,put_options',
    'underlying_asset_symbol': 'BTC'
})
data = r.json()
print(f"Success: {data.get('success')}")
if data.get('success'):
    results = data.get('result', [])
    print(f"Count: {len(results)}")
    if results:
        print("Sample:", json.dumps(results[0], indent=2))
else:
    print("Error:", data.get('error'))

print("\nTesting /v2/products for options...")
r2 = requests.get(f"{base}/v2/products", params={
    'contract_types': 'call_options,put_options',
    'underlying_asset_symbol': 'BTC'
})
data2 = r2.json()
print(f"Success: {data2.get('success')}")
if data2.get('success'):
    print(f"Count: {len(data2.get('result', []))}")
