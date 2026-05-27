import time
import threading
import datetime
import config
config.BOT_MODE = 'PAPER'

# Mock time to 8:30 AM
from utils import get_ist_now as original_get_ist_now
import utils
def mock_get_ist_now():
    now = original_get_ist_now()
    return now.replace(hour=8, minute=30)
utils.get_ist_now = mock_get_ist_now

from bot_engine import DeltaTradingEngine
from logger import app_logger

def run_test():
    app_logger.info("Starting Local Monitor Test")
    engine = DeltaTradingEngine()
    
    # Start the monitor loop in background
    monitor_thread = threading.Thread(target=engine.monitor_loop, daemon=True)
    monitor_thread.start()
    
    app_logger.info("Triggering Force Strangle Entry")
    engine.run_entry_cycle(force=True)
    
    app_logger.info("Waiting 20 seconds to see if the trade cuts early...")
    for i in range(20):
        time.sleep(1)
        if not engine.execution.active_positions:
            app_logger.info(f"TRADE CUT EARLY AT {i} SECONDS!")
            return
            
    app_logger.info("Test passed: Trade did NOT cut early.")
    
if __name__ == '__main__':
    run_test()
