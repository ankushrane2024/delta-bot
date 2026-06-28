import time
from api_client import DeltaIndiaClient

def test_api():
    client = DeltaIndiaClient()
    res = client.get_candles("BTCUSD", "5m")
    
    if res.get("success"):
        candles = res.get("result", [])
        print(f"Total candles fetched: {len(candles)}")
        
        if len(candles) >= 2:
            print("Last 2 candles:")
            print(f"-2: {candles[-2]}")
            print(f"-1 (Latest): {candles[-1]}")
            
            close_price = float(candles[-2].get('close', 0))
            print(f"\nExtracted close price: {close_price}")
        else:
            print("Not enough candles returned:", candles)
    else:
        print("API Call Failed:", res)

test_api()
