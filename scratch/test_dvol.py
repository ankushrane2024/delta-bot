import requests
import time

url = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
end_ts = int(time.time() * 1000)
start_ts = end_ts - 30 * 24 * 60 * 60 * 1000  # 30 days ago

params = {
    "currency": "BTC",
    "start_timestamp": start_ts,
    "end_timestamp": end_ts,
    "resolution": "1d"  # or maybe "60", "3600" or similar
}

try:
    response = requests.get(url, params=params)
    print("Status code:", response.status_code)
    data = response.json()
    print("Keys in response:", data.keys())
    if "result" in data:
        res = data["result"]
        print("Keys in result:", res.keys() if isinstance(res, dict) else "Not a dict")
        if "data" in res:
            print("Data length:", len(res["data"]))
            if len(res["data"]) > 0:
                print("First data point:", res["data"][0])
                print("Last data point:", res["data"][-1])
except Exception as e:
    print("Error:", e)
