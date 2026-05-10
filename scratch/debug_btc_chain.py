import requests
base = "https://api.india.delta.exchange"
print("Testing /v2/tickers with all possible BTC params...")
# Try both symbol and ID
params = {
    'contract_types': 'call_options,put_options',
    'underlying_asset_id': '13',
    'underlying_asset_symbol': 'BTC'
}
r = requests.get(f"{base}/v2/tickers", params=params)
data = r.json()
if data.get('success'):
    res = data.get('result', [])
    print(f"Total returned: {len(res)}")
    # Print underlying symbols of the first 20 items to see what's inside
    underlyings = set([t.get('underlying_asset_symbol') for t in res])
    print(f"Underlying assets in response: {underlyings}")
    
    btc_items = [t for t in res if 'BTC' in t.get('symbol', '')]
    print(f"Items with 'BTC' in symbol: {len(btc_items)}")
    if btc_items:
        print("Sample BTC Symbol:", btc_items[0].get('symbol'))
        print("Sample BTC Underlying:", btc_items[0].get('underlying_asset_symbol'))
else:
    print("Error:", data.get('error'))
