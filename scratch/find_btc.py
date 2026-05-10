import requests
base = "https://api.india.delta.exchange"
print("Fetching all assets to find BTC...")
r = requests.get(f"{base}/v2/assets")
data = r.json()
if data.get('success'):
    for a in data.get('result', []):
        if 'BTC' in a.get('symbol', ''):
            print(f"Asset: {a.get('symbol')}, ID: {a.get('id')}")
else:
    print("Error fetching assets")
