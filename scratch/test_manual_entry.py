import requests
import time
import json

def test():
    print("====================================================")
    print("      Testing Manual Strangle Force Entry Pipeline  ")
    print("====================================================")
    
    # 1. Trigger manual order
    print("\n1. Posting to /api/manual_order...")
    try:
        r = requests.post("http://127.0.0.1:5000/api/manual_order", timeout=10)
        print("   Status Code:", r.status_code)
        print("   Response:", json.dumps(r.json(), indent=2))
    except Exception as e:
        print("   [FAIL] Could not post to manual_order:", e)
        return

    # 2. Wait for background thread to fetch data, select strikes, and execute orders
    print("\n2. Waiting 5 seconds for execution cycle...")
    time.sleep(5)

    # 3. Verify positions
    print("\n3. Querying /api/status...")
    try:
        r = requests.get("http://127.0.0.1:5000/api/status", timeout=10)
        status = r.json()
        positions = status.get("positions", [])
        print(f"   [SUCCESS] Status responsive. Active positions found: {len(positions)}")
        for idx, pos in enumerate(positions, 1):
            print(f"     Leg {idx}:")
            print(f"       * Symbol: {pos.get('symbol')}")
            print(f"       * Side: {pos.get('side')}")
            print(f"       * Leg Type: {pos.get('leg_type')}")
            print(f"       * Strike: {pos.get('strike')}")
            print(f"       * Entry Price: {pos.get('entry_price')} USDT")
            print(f"       * Size: {pos.get('size')} lots")
            print(f"       * Mins to Square-off: {pos.get('mins_to_squareoff')} mins")
            
        print("\n4. Checking general status fields:")
        print(f"   - Mode: {status.get('mode')}")
        print(f"   - Equity: ${status.get('equity')}")
        print(f"   - Size Multiplier: {status.get('size_multiplier')}x")
        print(f"   - DVOL Level: {status.get('dvol_status', {}).get('current_dvol')}%")
        print(f"   - Smart Hedging Status: {status.get('hedge_status', {}).get('hedge_active')}")
    except Exception as e:
        print("   [FAIL] Could not fetch status:", e)

    print("\n====================================================")
    print("              Verification Completed!               ")
    print("====================================================")

if __name__ == '__main__':
    test()
