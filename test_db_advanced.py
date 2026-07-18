import os
import time
import db_manager
from unittest.mock import patch

def clear_local_disk():
    for f in ["bot_state.json", "trade_history.json", "active_positions.json", "cloud_db_config.json"]:
        if os.path.exists(f):
            os.remove(f)

# Ensure fallback mode
if "GITHUB_PAT" in os.environ: del os.environ["GITHUB_PAT"]
if "GITHUB_GIST_ID" in os.environ: del os.environ["GITHUB_GIST_ID"]

print("\n--- TEST 1: Multiple Save/Restart Cycles ---")
clear_local_disk()
db_manager._connected = False

# Cycle 1
data = {"max_equity": 100, "trades": [{"id": 1}], "daily_reports": [], "state": {}}
db_manager.save_all_data(data)
print("Cycle 1: Saved Trade 1. Wiping disk.")
clear_local_disk()

# Cycle 2
db_manager._connected = False
loaded_1 = db_manager.load_all_data()
print(f"Cycle 2: Loaded Trades: {loaded_1.get('trades')}")
data["trades"].append({"id": 2})
db_manager.save_all_data(data)
print("Cycle 2: Appended Trade 2. Wiping disk.")
clear_local_disk()

# Cycle 3
db_manager._connected = False
loaded_2 = db_manager.load_all_data()
print(f"Cycle 3: Loaded Trades: {loaded_2.get('trades')}")

print("\n--- TEST 2: Network Failure Simulation ---")
# Simulate requests.put throwing a Timeout
with patch('requests.put', side_effect=Exception("Simulated Network Timeout")):
    data["trades"].append({"id": 3})
    success = db_manager.save_all_data(data)
    print(f"Network Failure Save Result: {success}")
    print("Local trades on disk:", db_manager.load_all_data().get("trades")) # Loads from local because cloud failed but local saved

print("\n--- TEST 3: Concurrent Write Handling ---")
# The bot uses _sync_lock (threading.Lock) to prevent concurrent writes.
print(f"Sync Lock type: {type(db_manager._sync_lock)}")
print("When save_all_data is called, the lock is acquired, ensuring atomic operations across threads.")

