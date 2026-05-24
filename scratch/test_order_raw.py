import hmac
import hashlib
import json
import time
import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("DELTA_API_KEY")
API_SECRET = os.getenv("DELTA_API_SECRET")
BASE_URL = "https://api.india.delta.exchange"

def generate_signature(method, path, body=""):
    timestamp = str(int(time.time()))
    payload = method + timestamp + path + body
    signature = hmac.new(
        API_SECRET.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return timestamp, signature

def test_place_order():
    # Pick a random active product ID if possible, or use one from recent logs if known.
    # For now, let's just try to get tickers to find a valid product_id.
    path = "/v2/tickers"
    r = requests.get(BASE_URL + path)
    tickers = r.json().get('result', [])
    if not tickers:
        print("Failed to fetch tickers")
        return

    # Find a BTC option
    target = None
    for t in tickers:
        if 'BTC' in t.get('symbol') and 'C' in t.get('symbol'):
            target = t
            break
    
    if not target:
        print("No BTC option found")
        return

    prod_id = target['product_id']
    symbol = target['symbol']
    print(f"Testing order for {symbol} (ID: {prod_id})")

    path = "/v2/orders"
    data = {
        "product_id": prod_id,
        "side": "sell",
        "size": 1,
        "order_type": "market_order"
    }
    body = json.dumps(data)
    
    timestamp, signature = generate_signature("POST", path, body)
    headers = {
        "Content-Type": "application/json",
        "api-key": API_KEY,
        "timestamp": timestamp,
        "signature": signature
    }
    
    res = requests.post(BASE_URL + path, headers=headers, data=body)
    print(f"Status Code: {res.status_code}")
    print(f"Response: {res.text}")

if __name__ == "__main__":
    test_place_order()
