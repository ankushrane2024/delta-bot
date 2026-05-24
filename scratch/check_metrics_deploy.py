import time
import requests
import json

url = 'https://delta-btc-options-bot.onrender.com/api/backtest'
payload = {'starting_capital': 50000, 'start_date': '2026-02-21', 'end_date': '2026-05-22'}

print("Starting deployment check...")
start_time = time.time()
success = False

while time.time() - start_time < 120:
    try:
        r = requests.post(url, json=payload, timeout=10)
        metrics = r.json().get('metrics', {})
        print(f"Checked keys: {list(metrics.keys())}")
        if 'total_pnl_usd' in metrics:
            print("\n🎉 DEPLOYMENT SUCCESSFUL! New metrics keys found!")
            print(json.dumps(metrics, indent=2))
            success = True
            break
    except Exception as e:
        print(f"Error checking: {e}")
    time.sleep(10)

if not success:
    print("\nDeployment is still taking longer. Try running the script again in a minute.")
