import threading
import time
import requests
import main

# Step 1: Start main server in background
def run_server():
    try:
        main.main()
    except Exception as e:
        print("Server thread died:", e)

# Give main.py a bit of a shim so it doesn't block forever 
# we'll use a local mock or we can just start it directly.
server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()

# Wait for server to boot
# Wait for server to boot (allow DB self-heal)
print("Waiting 15 seconds for server to boot...")
time.sleep(15)

# Verify Endpoints
endpoints = [
    ('/', 200),
    ('/ping', 200),
    ('/api/status', 200),
    ('/ares/dashboard', 200),
    ('/ares/status', 200),
    ('/ares/orders', 200),
    ('/ares/risk', 200),
    ('/ares/portfolio', 200),
    ('/ares/analytics', 200),
    ('/ares/provider', 200),
    ('/ares/system', 200),
    ('/ares/logs', 200),
]

results = {}
for endpoint, expected_status in endpoints:
    url = f"http://127.0.0.1:5000{endpoint}"
    try:
        response = requests.get(url)
        print(f"[{response.status_code}] {url}")
        results[endpoint] = response.status_code == expected_status
        if response.status_code != expected_status:
            print(f"   ERROR RESPONSE: {response.text[:200]}")
    except Exception as e:
        print(f"[ERROR] {url} - {e}")
        results[endpoint] = False

print("\n--- RESULTS ---")
for k, v in results.items():
    print(f"{k}: {'PASS' if v else 'FAIL'}")

if all(results.values()):
    print("ALL ROUTES VERIFIED SUCCESSFULLY.")
else:
    print("SOME ROUTES FAILED.")
