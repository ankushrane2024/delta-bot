import time
import requests

url = "https://delta-btc-options-bot.onrender.com/ping"
print(f"Starting local keep-alive pinger for Render bot at {url}")

while True:
    try:
        r = requests.get(url, timeout=10)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Ping status: {r.status_code} - {r.json()}")
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Ping failed: {e}")
    time.sleep(180)  # Ping every 3 minutes
