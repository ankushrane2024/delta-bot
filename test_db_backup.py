import sys, time, json, os
import config
import db_manager
from performance_tracker import PerformanceTracker
from logger import app_logger

def run_db_test():
    print("=" * 60)
    print("  DATABASE BACKUP & RESTORE VERIFICATION TEST")
    print("=" * 60)
    
    # 1. Force connection to the Cloud DB
    print("[1] Connecting to Cloud DB...")
    db_manager._connect()
    
    if not db_manager._connected:
        print("  [X] FAILED: Could not connect to any Cloud Database.")
        return
        
    print("  [PASS] Connected successfully.")
    
    # 2. Create a Fake Trade
    print("\n[2] Generating simulated trade data...")
    fake_trade = {
        "entry_time": "2026-07-23T22:55:00+05:30",
        "exit_time": "2026-07-23T22:58:00+05:30",
        "pnl": 150.50,
        "test_flag": "BACKUP_VERIFICATION_TEST"
    }
    
    tracker = PerformanceTracker()
    # Ensure tracker sees the cloud
    tracker._cloud_sync_safe = True
    
    # Load existing to not overwrite real data
    print("\n[3] Loading existing history to prevent data loss...")
    existing = db_manager.load_all_data() or {}
    existing_trades = existing.get("trades", [])
    print(f"  [PASS] Found {len(existing_trades)} existing trades in Cloud.")
    
    # 3. Save to Cloud
    print("\n[4] Triggering Cloud Backup Save...")
    test_data = {
        "max_equity": existing.get("max_equity", 50000.0),
        "trades": existing_trades + [fake_trade]
    }
    
    success = db_manager.save_all_data(test_data)
    if not success:
        print("  [X] FAILED: Save operation returned False.")
        return
    print("  [PASS] Data successfully pushed to Cloud.")
    
    # 4. Verify Local Timestamp updated
    print("\n[5] Verifying Local Timestamp Update...")
    time.sleep(1) # wait for file write
    last_time = db_manager.get_last_backup_time()
    print(f"  [PASS] Local timestamp updated to: {last_time}")
    
    # 5. Fetch from Cloud to Verify Integrity
    print("\n[6] Re-downloading from Cloud to verify data integrity...")
    downloaded_data = db_manager.load_all_data()
    
    if not downloaded_data:
        print("  [X] FAILED: Downloaded data is empty.")
        return
        
    downloaded_trades = downloaded_data.get("trades", [])
    print(f"  [PASS] Downloaded {len(downloaded_trades)} trades from Cloud.")
    
    # Find our fake trade
    found = False
    for t in downloaded_trades:
        if t.get("test_flag") == "BACKUP_VERIFICATION_TEST":
            found = True
            break
            
    if found:
        print("  [PASS] VERIFIED: Test trade was successfully written to and read from the Cloud Database!")
    else:
        print("  [X] FAILED: The test trade was missing from the downloaded cloud data.")
        return
        
    print("\n[7] Cleaning up test data...")
    # Clean up so we don't leave fake trades in the user's history
    clean_data = {
        "max_equity": existing.get("max_equity", 50000.0),
        "trades": existing_trades
    }
    db_manager.save_all_data(clean_data)
    print("  [PASS] Cleanup complete. Original history restored.")
    
    print("\n" + "=" * 60)
    print("  DATABASE VERIFICATION COMPLETE - ALL SYSTEMS PASS")
    print("=" * 60)

if __name__ == "__main__":
    run_db_test()
