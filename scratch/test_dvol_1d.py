import requests
import time

url = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
end_ts = int(time.time() * 1000)
start_ts = end_ts - 40 * 24 * 60 * 60 * 1000  # 40 days ago to make sure we have at least 30 days

params = {
    "currency": "BTC",
    "start_timestamp": start_ts,
    "end_timestamp": end_ts,
    "resolution": "1D"  # Capital D!
}

try:
    response = requests.get(url, params=params)
    print("Status code:", response.status_code)
    data = response.json()
    if "result" in data:
        res = data["result"]
        if "data" in res:
            points = res["data"]
            print("Number of daily data points:", len(points))
            if len(points) > 0:
                print("First data point:", points[0])
                print("Last data point (latest):", points[-1])
                # Print last 5 points to see dates
                print("Last 5 points:")
                for p in points[-5:]:
                    # p is [timestamp, open, high, low, close]
                    t_str = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(p[0]/1000))
                    print(f"Time: {t_str}, Close (DVOL): {p[4]}")
except Exception as e:
    print("Error:", e)
