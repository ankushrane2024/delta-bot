import sys
import os

# Add root directory to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy import ShortStrangleStrategy
from api_client import DeltaIndiaClient
from utils import get_next_expiry_date

def main():
    print("Testing new strike selection rules...")
    api = DeltaIndiaClient()
    strategy = ShortStrangleStrategy(api)
    
    expiry = get_next_expiry_date()
    print(f"Target expiry date (D2): {expiry}")
    
    # Call find_strikes
    call, put = strategy.find_strikes(expiry_date=expiry)
    print("\n--- RESULTS ---")
    if call and put:
        print(f"Call Symbol: {call['symbol']}")
        print(f"Call Strike: {call['strike']}")
        print(f"Call Delta: {call['delta']}")
        print(f"Call Premium (INR): Rs. {call['premium_inr']:.2f}")
        print(f"Put Symbol: {put['symbol']}")
        print(f"Put Strike: {put['strike']}")
        print(f"Put Delta: {put['delta']}")
        print(f"Put Premium (INR): Rs. {put['premium_inr']:.2f}")
        print(f"Strangle Net Delta: {call['delta'] + put['delta']:.4f}")
    else:
        print("No strikes found.")

if __name__ == '__main__':
    main()
