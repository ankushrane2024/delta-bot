import os
import db_manager

# Ensure no PAT is set to force JSONBlob fallback
if "GITHUB_PAT" in os.environ:
    del os.environ["GITHUB_PAT"]
if "GITHUB_GIST_ID" in os.environ:
    del os.environ["GITHUB_GIST_ID"]

print("1. Creating a fake trade and saving it to cloud...")
mock_trade_data = {
    "max_equity": 1000.0,
    "trades": [{"id": 1, "profit": 50}],
    "daily_reports": [],
    "state": {}
}

# Delete local files to ensure clean state
for f in ["bot_state.json", "trade_history.json", "active_positions.json", "cloud_db_config.json"]:
    if os.path.exists(f):
        os.remove(f)

# Save data
db_manager.save_all_data(mock_trade_data)
print("Saved. Check logs for JSONBlob ID.")

print("\n2. Simulating a Render restart (wiping local files)...")
for f in ["bot_state.json", "trade_history.json", "active_positions.json"]:
    if os.path.exists(f):
        os.remove(f)
        
print("\n3. Loading data from cloud (should retrieve JSONBlob)...")
# Force reconnect
db_manager._connected = False
loaded_data = db_manager.load_all_data()

print(f"Loaded max_equity: {loaded_data.get('max_equity')}")
print(f"Loaded trades: {loaded_data.get('trades')}")

if loaded_data.get("max_equity") == 1000.0 and len(loaded_data.get("trades", [])) == 1:
    print("SUCCESS! Data was recovered from JSONBlob fallback after local wipe.")
else:
    print("FAILED! Data was not recovered.")
