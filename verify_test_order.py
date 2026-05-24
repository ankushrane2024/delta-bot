import requests
import json
import time

def main():
    base_url = "http://127.0.0.1:5000"
    print("====================================================")
    print("    Delta BTC Options Bot - Test Order Run          ")
    print("====================================================")
    
    print(f"\n1. Triggering Test Order via {base_url}/api/test_order...")
    try:
        # The test order endpoint executes the 10-second strangle simulation.
        # We set a higher timeout (20s) because the simulation sleeps for 10s plus execution delay.
        r = requests.post(f"{base_url}/api/test_order", timeout=25)
        if r.status_code == 200:
            data = r.json()
            if data.get('success'):
                print("   [SUCCESS] Test order completed successfully.")
                print(f"   - Message: {data.get('message')}")
            else:
                print(f"   [FAIL] Test order returned error: {data.get('error')}")
        else:
            print(f"   [FAIL] /api/test_order returned status code {r.status_code}")
    except Exception as e:
        print(f"   [FAIL] Test order invocation failed: {e}")

    print("\n====================================================")
    print("              Verification Completed!               ")
    print("====================================================")

if __name__ == '__main__':
    main()
