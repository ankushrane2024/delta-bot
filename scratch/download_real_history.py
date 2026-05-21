import requests
import time
import json
import datetime
import os

def download_data():
    print("====================================================")
    print("  Downloading Real Historical DVOL & BTC Price Data ")
    print("====================================================")
    
    end_ts = int(time.time() * 1000)
    # Fetch last 600 days to have a solid buffer
    days_to_fetch = 600
    start_ts = end_ts - days_to_fetch * 24 * 60 * 60 * 1000
    
    # 1. Fetch DVOL from Deribit
    print("Fetching DVOL data from Deribit...")
    dvol_url = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
    dvol_params = {
        "currency": "BTC",
        "start_timestamp": start_ts,
        "end_timestamp": end_ts,
        "resolution": "1D"
    }
    
    dvol_points = []
    try:
        r = requests.get(dvol_url, params=dvol_params, timeout=20)
        if r.status_code == 200:
            dvol_points = r.json().get("result", {}).get("data", [])
            print(f"DVOL: Successfully fetched {len(dvol_points)} daily candles.")
        else:
            print(f"DVOL Fetch Error {r.status_code}: {r.text}")
            return False
    except Exception as e:
        print(f"DVOL Fetch Exception: {e}")
        return False
        
    # 2. Fetch BTC Perpetual Prices from Deribit
    print("Fetching BTC Perpetual candles from Deribit...")
    price_url = "https://www.deribit.com/api/v2/public/get_tradingview_chart_data"
    price_params = {
        "instrument_name": "BTC-PERPETUAL",
        "start_timestamp": start_ts,
        "end_timestamp": end_ts,
        "resolution": "1D"
    }
    
    price_data = {}
    try:
        r = requests.get(price_url, params=price_params, timeout=20)
        if r.status_code == 200:
            res = r.json().get("result", {})
            ticks = res.get("ticks", [])
            if ticks:
                price_data = {
                    "ticks": ticks,
                    "open": res.get("open", []),
                    "high": res.get("high", []),
                    "low": res.get("low", []),
                    "close": res.get("close", [])
                }
                print(f"BTC Price: Successfully fetched {len(ticks)} daily candles.")
            else:
                print("BTC Price API returned empty ticks.")
                return False
        else:
            print(f"BTC Price Fetch Error {r.status_code}: {r.text}")
            return False
    except Exception as e:
        print(f"BTC Price Fetch Exception: {e}")
        return False

    # 3. Align and Merge
    print("\nAligning and merging historical data...")
    aligned_data = []
    
    # Map price ticks by date (YYYY-MM-DD)
    price_by_date = {}
    for idx, tick in enumerate(price_data["ticks"]):
        # Convert timestamp to date
        dt = datetime.datetime.utcfromtimestamp(tick / 1000.0)
        date_str = dt.strftime('%Y-%m-%d')
        price_by_date[date_str] = {
            "open": price_data["open"][idx],
            "high": price_data["high"][idx],
            "low": price_data["low"][idx],
            "close": price_data["close"][idx]
        }
        
    # Map DVOL points by date
    # Format: [timestamp, open, high, low, close]
    dvol_by_date = {}
    for p in dvol_points:
        ts = p[0]
        dt = datetime.datetime.utcfromtimestamp(ts / 1000.0)
        date_str = dt.strftime('%Y-%m-%d')
        dvol_by_date[date_str] = {
            "open": p[1],
            "high": p[2],
            "low": p[3],
            "close": p[4]
        }
        
    # Merge sorted by date
    all_dates = sorted(list(set(price_by_date.keys()) & set(dvol_by_date.keys())))
    print(f"Merged aligned record count: {len(all_dates)} matching days.")
    
    # Calculate rolling DVOL percentile
    dvol_closes = []
    for date_str in all_dates:
        dvol_val = dvol_by_date[date_str]["close"]
        dvol_closes.append(dvol_val)
        
        # Take last 30 days window (inclusive of current day)
        window = dvol_closes[-30:]
        count = sum(1 for val in window if val <= dvol_val)
        percentile = (count / len(window)) * 100.0
        
        p_entry = price_by_date[date_str]
        d_entry = dvol_by_date[date_str]
        
        aligned_data.append({
            "date": date_str,
            "btc_open": p_entry["open"],
            "btc_high": p_entry["high"],
            "btc_low": p_entry["low"],
            "btc_close": p_entry["close"],
            "dvol_open": d_entry["open"],
            "dvol_high": d_entry["high"],
            "dvol_low": d_entry["low"],
            "dvol_close": d_entry["close"],
            "dvol_percentile": round(percentile, 2)
        })

    # Save to file
    out_file = "historical_data_cache.json"
    try:
        with open(out_file, "w") as f:
            json.dump(aligned_data, f, indent=4)
        print(f"\n[SUCCESS] Saved aligned historical dataset to {out_file} ({len(aligned_data)} records).")
        return True
    except Exception as e:
        print(f"Failed to write output cache file: {e}")
        return False

if __name__ == '__main__':
    download_data()
