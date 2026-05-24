import requests
import time
import json
import datetime

def test_fetch():
    print("Fetching historical DVOL data...")
    end_ts = int(time.time() * 1000)
    # 550 days ago in milliseconds
    start_ts = end_ts - 550 * 24 * 60 * 60 * 1000
    
    # 1. Fetch DVOL from Deribit
    dvol_url = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
    dvol_params = {
        "currency": "BTC",
        "start_timestamp": start_ts,
        "end_timestamp": end_ts,
        "resolution": "1D"
    }
    
    try:
        r = requests.get(dvol_url, params=dvol_params, timeout=15)
        print(f"DVOL API Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            points = data.get("result", {}).get("data", [])
            print(f"DVOL Points fetched: {len(points)}")
            if points:
                print(f"First DVOL point: {points[0]}")
                print(f"Last DVOL point: {points[-1]}")
        else:
            print(f"DVOL API Error: {r.text}")
    except Exception as e:
        print(f"DVOL Fetch failed: {e}")

    # 2. Fetch BTC price from Deribit
    print("\nFetching historical BTC price data...")
    price_url = "https://www.deribit.com/api/v2/public/get_tradingview_chart_data"
    price_params = {
        "instrument_name": "BTC-PERPETUAL",
        "start_timestamp": start_ts,
        "end_timestamp": end_ts,
        "resolution": "1D"  # Try "1D" first
    }
    
    try:
        r = requests.get(price_url, params=price_params, timeout=15)
        print(f"BTC Price API Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            result = data.get("result", {})
            ticks = result.get("ticks", [])
            print(f"Price ticks count: {len(ticks)}")
            if ticks:
                print(f"First price tick (timestamp={ticks[0]}, open={result['open'][0]}, close={result['close'][0]})")
                print(f"Last price tick (timestamp={ticks[-1]}, open={result['open'][-1]}, close={result['close'][-1]})")
        else:
            # Let's try resolution="D" if "1D" fails
            print("Trying resolution='D'...")
            price_params["resolution"] = "D"
            r = requests.get(price_url, params=price_params, timeout=15)
            print(f"BTC Price (resolution='D') Status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                result = data.get("result", {})
                ticks = result.get("ticks", [])
                print(f"Price ticks count: {len(ticks)}")
                if ticks:
                    print(f"First price tick: timestamp={ticks[0]}, open={result['open'][0]}, close={result['close'][0]}")
            else:
                print(f"BTC Price API Error: {r.text}")
    except Exception as e:
        print(f"Price Fetch failed: {e}")

if __name__ == '__main__':
    test_fetch()
