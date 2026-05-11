from bot_core import bot_instance
import time

def test_full_strategy():
    print("Initializing engine...")
    bot_instance.start({'mode': 'PAPER'})
    
    print("\nTriggering Manual Trade...")
    bot_instance.trigger_execution('PAPER')
    
    print("Waiting 15 seconds for execution...")
    for i in range(15):
        time.sleep(1)
        # Fetch logs from bot state
        logs = bot_instance.get_logs('PAPER')
        if len(logs) > 1:
            last_msg = logs[-1]['msg']
            print(f" [{logs[-1]['time']}] {last_msg}")
            if "COMPLETE" in last_msg or "FAILED" in last_msg or "Aborting" in last_msg:
                break

if __name__ == "__main__":
    test_full_strategy()
