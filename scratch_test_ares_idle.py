import time
import threading
from bot_engine import DeltaTradingEngine
from web_server import app, init_web_server, set_ares_runner

def mock_bot():
    engine = DeltaTradingEngine()
    
    # Force a mock option
    engine.execution.active_options = {
        "BTC-26JUL24-65000-C": {
            "size": 1.0,
            "entry_price": 0.05,
            "leg_type": "call",
            "side": "SELL"
        }
    }
    
    # Initialize ARES
    from hedge.deployment.service_runner import ServiceRunner
    from hedge.engines.adapters.option_bridge import OptionBridge
    
    bridge = OptionBridge(engine)
    ares_runner = ServiceRunner(mode_override='PAPER', option_bridge=bridge, bot_engine=engine)
    set_ares_runner(ares_runner)
    
    init_web_server(engine)
    
    # Start threads
    threading.Thread(target=ares_runner.run, daemon=True).start()
    
    print("Started mock bot...")
    time.sleep(5)
    
    # Fetch /ares/status directly
    with app.test_client() as client:
        res = client.get('/ares/status')
        data = res.get_json()
        print("ARES Status Clusters:", data.get('clusters'))
        print("Decision Action:", data.get('decision_action'))
        print("Decision Reason:", data.get('decision_reason'))
        
    ares_runner.running = False

mock_bot()
