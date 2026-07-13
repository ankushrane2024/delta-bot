import requests
import json
import time
import os
import datetime

def fetch_delta_candles(symbol="BTCUSD", resolution="15m", days_back=365):
    end_time = int(time.time())
    start_time = end_time - (days_back * 24 * 60 * 60)
    
    url = "https://api.delta.exchange/v2/history/candles"
    
    # 15m candles = 96 per day. 365 days = 35040 candles. 
    # Delta API max limit per request might be 1000 or 500. We paginate.
    
    all_candles = []
    current_end = end_time
    
    print(f"Fetching {days_back} days of data for {symbol}...")
    
    while current_end > start_time:
        chunk_start = max(start_time, current_end - (1000 * 15 * 60))
        params = {
            "symbol": symbol,
            "resolution": resolution,
            "start": chunk_start,
            "end": current_end
        }
        try:
            res = requests.get(url, params=params, timeout=10)
            data = res.json()
            if not data.get("success"):
                print("Delta API Error:", data)
                break
                
            result = data.get("result", [])
            if not result:
                print("No result found in data:", data)
                break
                
            # result is sorted by time usually descending or ascending? Let's check first timestamp
            # Delta API typically returns oldest first in the chunk
            # Actually we just append and sort later
            all_candles.extend(result)
            
            # The oldest time in this chunk
            oldest_in_chunk = min([candle["time"] for candle in result])
            
            if oldest_in_chunk >= current_end:
                # To prevent infinite loop if pagination fails
                break
                
            current_end = oldest_in_chunk - 1
            
            print(f"Fetched {len(result)} candles. Total: {len(all_candles)}. Oldest: {datetime.datetime.fromtimestamp(oldest_in_chunk)}")
            time.sleep(0.5) # rate limit
            
        except Exception as e:
            print("Error fetching data:", e)
            break
            
    # Remove duplicates and sort
    unique_candles = {c["time"]: c for c in all_candles}
    sorted_candles = [unique_candles[t] for t in sorted(unique_candles.keys())]
    
    # Filter strictly for the requested range
    final_candles = [c for c in sorted_candles if c["time"] >= start_time]
    
    with open(os.path.join(os.path.dirname(__file__), "historical_btc.json"), "w") as f:
        json.dump(final_candles, f)
        
    print(f"Saved {len(final_candles)} candles to historical_btc.json")

if __name__ == "__main__":
    fetch_delta_candles()
