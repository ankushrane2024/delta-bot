from bot_core import bot_instance
import time

def test_fixes():
    print("Testing BTC Price Fallbacks...")
    price = bot_instance.india_client.get_btc_price()
    print(f"Current BTC Price: {price}")
    
    print("\nTesting Option Chain discovery...")
    chain = bot_instance.india_client.get_option_chain()
    print(f"Found {len(chain)} options.")
    
    if chain:
        expiries = bot_instance.get_valid_expiries(chain)
        print(f"Valid Expiries: {expiries}")
        
    print("\nTesting Manual Trigger...")
    # This should not crash even if it fails to find strikes
    bot_instance.trigger_execution('PAPER')
    time.sleep(5)
    print("Check logs in terminal above.")

if __name__ == "__main__":
    test_fixes()
