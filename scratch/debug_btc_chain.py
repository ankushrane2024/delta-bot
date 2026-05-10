import requests
import json
base = "https://api.india.delta.exchange"

params = {
    'contract_types': 'call_options,put_options',
    'underlying_asset_symbol': 'BTC'
}
r = requests.get(f"{base}/v2/tickers", params=params)
data = r.json()
if data.get('success'):
    res = data.get('result', [])
    btc_items = [t for t in res if 'BTC' in t.get('symbol', '')]
    if btc_items:
        print("Detailed fields for first BTC item:")
        item = btc_items[0]
        print(f"Symbol: {item.get('symbol')}")
        print("Quotes:", json.dumps(item.get('quotes'), indent=2))
        print("Greeks:", json.dumps(item.get('greeks'), indent=2))
        print("OI Contracts:", item.get('oi_contracts'))
        print("Volume:", item.get('volume'))
        print("Mark Price:", item.get('mark_price'))
else:
    print("Error:", data.get('error'))
