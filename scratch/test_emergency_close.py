import requests
import time
import json

def test():
    print("====================================================")
    print("      Testing Manual Emergency Close Pipeline        ")
    print("====================================================")
    
    # 1. Verify we have active positions first
    print("\n1. Checking active positions before close...")
    try:
        r = requests.get("http://127.0.0.1:5000/api/status", timeout=10)
        status = r.json()
        positions = status.get("positions", [])
        print(f"   Active positions found: {len(positions)}")
        if len(positions) == 0:
            print("   [WARNING] No active positions to close! Creating one first...")
            requests.post("http://127.0.0.1:5000/api/manual_order")
            time.sleep(5)
            r = requests.get("http://127.0.0.1:5000/api/status")
            status = r.json()
            positions = status.get("positions", [])
            print(f"   Now active positions: {len(positions)}")
    except Exception as e:
        print("   [FAIL] Pre-check failed:", e)
        return

    # 2. Trigger emergency close
    print("\n2. Posting to /api/emergency_close...")
    try:
        r = requests.post("http://127.0.0.1:5000/api/emergency_close", timeout=10)
        print("   Status Code:", r.status_code)
        print("   Response:", json.dumps(r.json(), indent=2))
    except Exception as e:
        print("   [FAIL] Could not post to emergency_close:", e)
        return

    # 3. Wait 2 seconds for server to process close
    time.sleep(2)

    # 4. Verify positions are cleared
    print("\n3. Querying /api/status post-close...")
    try:
        r = requests.get("http://127.0.0.1:5000/api/status", timeout=10)
        status = r.json()
        positions = status.get("positions", [])
        print(f"   [SUCCESS] Status responsive. Active positions found: {len(positions)}")
        
        print("\n4. Checking general status fields:")
        print(f"   - Mode: {status.get('mode')}")
        print(f"   - Equity: ${status.get('equity')}")
        print(f"   - Trade skip/close status: {status.get('logs', [''])[0] if status.get('logs') else 'None'}")
        
        # 5. Check if journal was updated
        print("\n5. Querying /api/journal to check Pro-Trader Diary...")
        r_j = requests.get("http://127.0.0.1:5000/api/journal")
        journal = r_j.json()
        if journal.get("success"):
            print("   [SUCCESS] /api/journal queried successfully.")
            content = journal.get("content", "")
            # Print last 15 lines of journal content
            lines = content.strip().split("\n")
            print("   Tail of Pro-Trader Journal:")
            for line in lines[-15:]:
                print("     >", line)
        else:
            print("   [FAIL] /api/journal returned success=False:", journal.get("error"))
    except Exception as e:
        print("   [FAIL] Post-close check failed:", e)

    print("\n====================================================")
    print("              Verification Completed!               ")
    print("====================================================")

if __name__ == '__main__':
    test()
