import requests
import time
import json

def run_integration():
    print("====================================================")
    print("   Delta BTC Options Bot - Full End-to-End Test     ")
    print("====================================================")
    
    # 1. Trigger manual order
    print("\n1. Posting to /api/manual_order...")
    try:
        r = requests.post("http://127.0.0.1:5000/api/manual_order", timeout=10)
        print("   Response:", json.dumps(r.json(), indent=2))
    except Exception as e:
        print("   [FAIL] Could not post to manual_order:", e)
        return

    # 2. Wait 5s for entry
    print("\n2. Waiting 5 seconds for execution cycle...")
    time.sleep(5)

    # 3. Verify positions
    print("\n3. Querying /api/status...")
    try:
        r = requests.get("http://127.0.0.1:5000/api/status", timeout=10)
        status = r.json()
        positions = status.get("positions", [])
        print(f"   Active positions found: {len(positions)}")
        if len(positions) == 2:
            print("   [PASS] 2 active strangle positions created successfully.")
        else:
            print("   [FAIL] Expected 2 positions, got", len(positions))
            return
            
        print("   Checking for monitor loop errors...")
        logs = status.get("logs", [])
        has_error = False
        for log in logs:
            if "Error in monitor loop" in log:
                print(f"   [FAIL] Found error in logs: {log}")
                has_error = True
        if not has_error:
            print("   [PASS] No monitor loop errors detected.")
            
    except Exception as e:
        print("   [FAIL] Could not check status:", e)
        return

    # 4. Trigger emergency close
    print("\n4. Posting to /api/emergency_close...")
    try:
        r = requests.post("http://127.0.0.1:5000/api/emergency_close", timeout=10)
        print("   Response:", json.dumps(r.json(), indent=2))
    except Exception as e:
        print("   [FAIL] Could not post to emergency_close:", e)
        return

    # 5. Wait 2s for close
    time.sleep(2)

    # 6. Verify positions are cleared and journal is written
    print("\n5. Querying /api/status post-close...")
    try:
        r = requests.get("http://127.0.0.1:5000/api/status", timeout=10)
        status = r.json()
        positions = status.get("positions", [])
        print(f"   Active positions found: {len(positions)}")
        if len(positions) == 0:
            print("   [PASS] Positions cleared successfully.")
        else:
            print("   [FAIL] Positions still active!", positions)
            
        print(f"   New Account Equity: ${status.get('equity')}")
        
        print("\n6. Fetching /api/journal...")
        r_j = requests.get("http://127.0.0.1:5000/api/journal")
        journal = r_j.json()
        if journal.get("success"):
            print("   [PASS] /api/journal queried successfully.")
            content = journal.get("content", "")
            if "📝 Trade Diary" in content:
                print("   [PASS] Pro-Trader Journal successfully logged the trade post-mortem.")
                print("\n   --- JOURNAL DIARY SUMMARY ---")
                lines = content.strip().split("\n")
                for line in lines[-20:]:
                    print("     ", line)
                print("   -----------------------------")
            else:
                print("   [FAIL] Journal was empty or had no Trade Diary entry! Content:", content)
        else:
            print("   [FAIL] /api/journal returned success=False:", journal.get("error"))
            
    except Exception as e:
        print("   [FAIL] Post-close verification failed:", e)

    print("\n====================================================")
    print("          Full Integration Test Completed!          ")
    print("====================================================")

if __name__ == '__main__':
    run_integration()
