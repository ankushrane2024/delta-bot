import sys
import os
import time

# Ensure import paths work
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smart_hedging import SmartHedgingManager

class MockAPIClient:
    def __init__(self, call_delta, put_delta):
        self.call_delta = call_delta
        self.put_delta = put_delta
        
    def get_realtime_ticker(self, symbol):
        # Return mock greeks
        delta = self.call_delta if symbol.endswith('-C') else self.put_delta
        return {
            'symbol': symbol,
            'mark_price': 150.0,
            'greeks': {
                'delta': delta,
                'gamma': 0.0005,
                'vega': 1.2,
                'theta': -0.8
            }
        }

class MockExecutionHandler:
    def __init__(self):
        self.hedge_size_btc = 0.0
        self.hedge_order_id = None
        self.orders_placed = []

    def place_hedge_order(self, size_btc, direction, use_limit=False):
        order_id = f"MOCK-HEDGE-{int(time.time())}"
        self.hedge_size_btc += size_btc if direction == 'buy' else -size_btc
        self.hedge_order_id = order_id
        self.orders_placed.append({
            'size': size_btc,
            'direction': direction,
            'order_id': order_id
        })
        return {'success': True, 'order_id': order_id}
        
    def close_hedge(self):
        self.orders_placed.append({'action': 'close_hedge'})
        self.hedge_size_btc = 0.0
        self.hedge_order_id = None

class MockDVOLProvider:
    def __init__(self, dvol):
        self.dvol = dvol
    def get_current_dvol(self):
        return self.dvol

class MockRiskManager:
    def tighten_stop_loss(self, pct):
        print(f"   [MOCK] Tightened options stop loss to {pct*100:.1f}%")

def run_test():
    print("====================================================")
    print("      Testing Smart Hedging Manager Integration      ")
    print("====================================================")
    
    # Position: 100 lots of Call, 100 lots of Put (1 lot = 0.001 BTC option size)
    # Leg size = 100 lots, total option size = 200 contracts
    positions = {
        "BTC-260523-85000-C": {"size": 100, "leg_type": "call"},
        "BTC-260523-75000-P": {"size": 100, "leg_type": "put"}
    }
    
    print("\n--- TEST CASE 1: Low IV Regime (DVOL = 42%), tested Call (Delta Call = 0.35, Put = -0.10) ---")
    # Net raw option delta: -0.35 + 0.10 = -0.25 raw net delta (tested Call leg)
    # Since low IV trigger is 0.20 delta, 0.25 > 0.20 -> SHOULD trigger a FULL hedge!
    # Expected hedge size: 0.25 * 100 * 0.001 = 0.025 BTC (Sell direction)
    api = MockAPIClient(call_delta=0.35, put_delta=-0.10)
    exec_handler = MockExecutionHandler()
    dvol = MockDVOLProvider(dvol=42.0)
    risk = MockRiskManager()
    
    hedger = SmartHedgingManager(exec_handler, dvol, risk, api)
    
    # Run post-entry hedge evaluation (post entry waits 5s, we bypass sleep for test by calling decision directly)
    net_delta_btc, _ = hedger._fetch_net_delta_and_gamma(positions)
    print(f"   - Calculated Net Delta BTC: {net_delta_btc:.4f} BTC")
    
    hedger._execute_hedge_decision(net_delta_btc, dvol.get_current_dvol(), positions)
    
    print("   - Placement Status:")
    print(f"     * Hedger Active State: {hedger.hedge_active}")
    print(f"     * Hedger Type: {hedger.hedge_type}")
    print(f"     * Hedger Size: {hedger.hedge_size_btc:.6f} BTC")
    print(f"     * Orders Placed: {exec_handler.orders_placed}")
    
    assert hedger.hedge_active is True, "Test Case 1 Failed: Hedge should be active!"
    assert hedger.hedge_type == "full", "Test Case 1 Failed: Hedge type should be full!"
    assert abs(hedger.hedge_size_btc - 0.025) < 0.0001, f"Test Case 1 Failed: Size should be 0.025, got {hedger.hedge_size_btc}"
    print("   [PASS] Test Case 1 passed successfully!")

    print("\n--- TEST CASE 2: High IV Regime (DVOL = 60%), tested Put (Delta Call = 0.05, Put = -0.35) ---")
    # Net raw option delta: -0.05 + 0.35 = 0.30 raw net delta (tested Put leg)
    # Since high IV trigger is 0.12 delta, 0.30 > 0.12 -> SHOULD trigger a PARTIAL (50%) hedge!
    # Expected hedge size: 50% * 0.30 * 100 * 0.001 = 0.015 BTC (Buy direction)
    api_high = MockAPIClient(call_delta=0.05, put_delta=-0.35)
    exec_handler_high = MockExecutionHandler()
    dvol_high = MockDVOLProvider(dvol=60.0)
    
    hedger_high = SmartHedgingManager(exec_handler_high, dvol_high, risk, api_high)
    net_delta_btc_high, _ = hedger_high._fetch_net_delta_and_gamma(positions)
    print(f"   - Calculated Net Delta BTC: {net_delta_btc_high:.4f} BTC")
    
    hedger_high._execute_hedge_decision(net_delta_btc_high, dvol_high.get_current_dvol(), positions)
    
    print("   - Placement Status:")
    print(f"     * Hedger Active State: {hedger_high.hedge_active}")
    print(f"     * Hedger Type: {hedger_high.hedge_type}")
    print(f"     * Hedger Size: {hedger_high.hedge_size_btc:.6f} BTC")
    print(f"     * Orders Placed: {exec_handler_high.orders_placed}")
    
    assert hedger_high.hedge_active is True, "Test Case 2 Failed: Hedge should be active!"
    assert hedger_high.hedge_type == "partial", "Test Case 2 Failed: Hedge type should be partial!"
    assert abs(hedger_high.hedge_size_btc - 0.015) < 0.0001, f"Test Case 2 Failed: Size should be 0.015, got {hedger_high.hedge_size_btc}"
    print("   [PASS] Test Case 2 passed successfully!")

    print("\n--- TEST CASE 3: No Hedge Needed (Delta Call = 0.22, Put = -0.22) ---")
    # Net raw option delta: -0.22 + 0.22 = 0.00 raw net delta
    # Since trigger is 0.20, 0.00 <= 0.20 -> SHOULD NOT trigger!
    api_none = MockAPIClient(call_delta=0.22, put_delta=-0.22)
    exec_handler_none = MockExecutionHandler()
    dvol_none = MockDVOLProvider(dvol=42.0)
    
    hedger_none = SmartHedgingManager(exec_handler_none, dvol_none, risk, api_none)
    net_delta_none, _ = hedger_none._fetch_net_delta_and_gamma(positions)
    print(f"   - Calculated Net Delta BTC: {net_delta_none:.4f} BTC")
    
    hedger_none._execute_hedge_decision(net_delta_none, dvol_none.get_current_dvol(), positions)
    
    print("   - Placement Status:")
    print(f"     * Hedger Active State: {hedger_none.hedge_active}")
    print(f"     * Orders Placed: {exec_handler_none.orders_placed}")
    
    assert hedger_none.hedge_active is False, "Test Case 3 Failed: Hedge should not be active!"
    print("   [PASS] Test Case 3 passed successfully!")

    print("\n====================================================")
    print("       All Smart Hedging Tests Passed Perfectly!     ")
    print("====================================================")

if __name__ == '__main__':
    run_test()
