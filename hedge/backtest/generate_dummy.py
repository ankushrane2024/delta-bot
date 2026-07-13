import json
import time
import random
import os

def generate_dummy():
    candles = []
    current_time = int(time.time()) - (365 * 24 * 60 * 60)
    price = 60000.0
    
    # 365 days of 15m candles
    for _ in range(35040):
        # random walk
        price = price * (1.0 + random.normalvariate(0, 0.002))
        candles.append({
            "time": current_time,
            "close": price
        })
        current_time += 15 * 60
        
    with open(os.path.join(os.path.dirname(__file__), "historical_btc.json"), "w") as f:
        json.dump(candles, f)
        
    print(f"Generated {len(candles)} dummy candles")

if __name__ == "__main__":
    generate_dummy()
