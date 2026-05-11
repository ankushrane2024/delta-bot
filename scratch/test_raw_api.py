import requests

def test_raw_api():
    base = "https://api.india.delta.exchange"
    endpoints = [
        "/v2/tickers",
        "/v2/products",
        "/v2/wallet/balances", # This might 401 but should exist
    ]
    
    for ep in endpoints:
        url = base + ep
        print(f"Testing {url}...")
        try:
            r = requests.get(url, timeout=10)
            print(f" Status: {r.status_code}")
            print(f" Content (first 100): {r.text[:100]}")
        except Exception as e:
            print(f" Failed: {e}")

if __name__ == "__main__":
    test_raw_api()
