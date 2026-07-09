import sys
import time
import logging
import threading
from bot_engine import DeltaTradingEngine
from hedge.deployment.service_runner import ServiceRunner
from hedge.engines.adapters.option_bridge import OptionBridge

logger = logging.getLogger("ReplayTest")

def run_replay():
    print("=== STARTING ARES REPLAY SIMULATION ===")
    
    # 1. Start Bot Engine in PAPER mode
    import config
    config.MODE = "PAPER"
    engine = DeltaTradingEngine()
    
    # Mock api_client to return specific prices
    class MockApiClient:
        def __init__(self):
            self.price = 50000.0
            
        def get_realtime_ticker(self, symbol):
            if symbol == "BTCUSDT":
                return {"mark_price": self.price}
            return {"mark_price": 500.0} # Option price mock
            
        def get_tickers(self, params=None):
            return {"success": True, "result": [{"symbol": "BTCUSDT", "mark_price": self.price}]}
            
        def get_position(self, product_id):
            return None
            
        def place_order(self, *args, **kwargs):
            return {"success": True, "result": {"id": 123}}
            
    engine.api_client = MockApiClient()
    
    # 2. Start ARES
    bridge = OptionBridge(engine)
    ares_runner = ServiceRunner(mode_override="PAPER", option_bridge=bridge)
    ares_thread = threading.Thread(target=ares_runner.run, daemon=True)
    ares_thread.start()
    
    time.sleep(2) # let ARES boot
    
    # 3. Enter a position
    print("--- ENTERING PAPER OPTION POSITION ---")
    engine.execution.active_positions = {
        "CALL_60000": {"size": 2, "entry_price": 500.0, "side": "SELL", "leg_type": "call"},
        "PUT_40000": {"size": 2, "entry_price": 500.0, "side": "SELL", "leg_type": "put"}
    }
    engine.total_entry_premium = 2000.0
    
    time.sleep(5)
    
    # 4. Simulate Trend (BTC crashes)
    print("--- SIMULATING MARKET CRASH ---")
    
    for _ in range(10):
        engine.api_client.price -= 500.0
        print(f"Simulated BTC Price: {engine.api_client.price}")
        
        # We need to manually push tick into Ares? No, Ares queries bridge -> engine.api_client
        time.sleep(1)
        
        tick_result = getattr(ares_runner.orchestrator, 'latest_tick_result', None)
        if tick_result and tick_result.hedge_decision:
            print(f"ARES Decision: {tick_result.hedge_decision.action.name if hasattr(tick_result.hedge_decision.action, 'name') else tick_result.hedge_decision.action} | "
                        f"Trend Strength: {getattr(tick_result.trend_result, 'trend_strength', 0.0):.2f} | "
                        f"Regime: {tick_result.regime_result.current_regime.name if tick_result.regime_result and hasattr(tick_result.regime_result, 'current_regime') else 'NONE'} | "
                        f"Risk: {tick_result.risk_result.overall_risk_score if tick_result.risk_result else 0.0:.2f} | "
                        f"Recovery Prob: {tick_result.risk_result.recovery_probability if tick_result.risk_result else 0.0:.2f} | "
                        f"Target Size: {tick_result.hedge_sizing.target_delta if tick_result.hedge_sizing else 0.0:.4f}")
            
    # 5. Check if hedge was placed
    if engine.execution.hedge_size_btc != 0:
        print(f"SUCCESS: ARES placed a hedge of {engine.execution.hedge_size_btc} BTC!")
    else:
        print("FAILURE: ARES did not hedge during the crash.")
        
    # 6. Simulate Exit
    print("--- SIMULATING EOD EXIT ---")
    engine.run_exit_cycle()
    
    print("=== REPLAY SIMULATION COMPLETE ===")

if __name__ == "__main__":
    run_replay()
