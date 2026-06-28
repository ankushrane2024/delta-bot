import os
import sys
import json
from performance_tracker import PerformanceTracker
import db_manager

def run_disaster_recovery_test():
    print("=== PRO-LEVEL DISASTER RECOVERY TEST ===")
    
    local_file = "trade_history.json"
    
    # STEP 1: Simulate Render Server Wipe
    print("\n[STEP 1] Simulating a full server crash...")
    if os.path.exists(local_file):
        os.remove(local_file)
        print("--> Deleted local 'trade_history.json'")
    else:
        print("--> 'trade_history.json' already missing.")
        
    print(f"--> File exists check: {os.path.exists(local_file)}")
    
    # STEP 2: Boot up the Bot's Memory Engine
    print("\n[STEP 2] Bot restarts. Initializing Performance Tracker...")
    tracker = PerformanceTracker(filename=local_file)
    
    # STEP 3: Verify the Recovery
    print("\n[STEP 3] Verifying Memory Restoration...")
    trades_recovered = len(tracker.trades)
    
    if trades_recovered > 0:
        print(f"✅ SUCCESS! Recovered {trades_recovered} trades from the Cloud DB!")
        print(f"--> Most recent trade restored: {tracker.trades[-1].get('date', 'Unknown')}")
        print(f"--> Max Equity restored: {tracker.max_equity}")
    else:
        print("❌ FAILED! 0 trades recovered.")
        sys.exit(1)
        
    # STEP 4: Verify the local file was recreated by the sync
    print("\n[STEP 4] Verifying local sync cache...")
    if os.path.exists(local_file):
        with open(local_file, 'r') as f:
            local_data = json.load(f)
            print(f"✅ SUCCESS! Local file was instantly rebuilt with {len(local_data.get('trades', []))} trades.")
    else:
        print("❌ FAILED! Local file was not rebuilt.")
        sys.exit(1)
        
    print("\n=== ALL TESTS PASSED: 100% AMNESIA PROOF ===")

if __name__ == "__main__":
    run_disaster_recovery_test()
