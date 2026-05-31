import time
from unittest.mock import MagicMock
from smart_hedging import SmartHedgingManager
from config import HEDGE_SYMBOL

def test_dynamic_continuous_scaling():
    print("\n--- RUNNING DYNAMIC HEDGE SCALING TEST (100 Lots) ---")
    
    # Setup mock manager
    execution_mock = MagicMock()
    execution_mock.hedge_size_btc = 0.0
    
    def mock_place_hedge(size, direction):
        print(f"-> [ORDER PLACED] Bot executed {direction.upper()} {size:.4f} BTC")
        execution_mock.hedge_size_btc += size if direction == 'sell' else -size
        return {'success': True, 'order_id': 'mock123'}
    
    execution_mock.place_hedge_order.side_effect = mock_place_hedge
    
    dvol_mock = MagicMock()
    dvol_mock.get_current_dvol.return_value = 40.0
    
    risk_mock = MagicMock()
    
    api_mock = MagicMock()
    manager = SmartHedgingManager(api_mock, execution_mock, dvol_mock, risk_mock)
    
    # Mock the delta fetching so we can control it in the test
    manager._fetch_net_delta_and_gamma = MagicMock(return_value=(0.05, 0.01))
    
    # Simulate 100 lots (0.100 BTC exposure per leg)
    positions = {
        'C-BTC-123': {'size': 100},
        'P-BTC-456': {'size': 100}
    }
    
    print("\n[Step 1] Normal Condition, No Hedge")
    profit_usd = -5.0
    manager.manage_hedge(positions, -0.05, profit_usd)
    print(f"Hedge Active: {manager.hedge_active}, Size: {abs(execution_mock.hedge_size_btc):.4f} BTC")
    
    print("\n[Step 2] Market Dumps, Net Delta > 0.15, Loss = $30")
    manager._fetch_net_delta_and_gamma.return_value = (0.16, 0.01)
    profit_usd = -30.0
    manager.manage_hedge(positions, -0.15, profit_usd)
    print(f"Hedge Active: {manager.hedge_active}, Size: {abs(execution_mock.hedge_size_btc):.4f} BTC")
    
    print("\n[Step 3] Market Keeps Dumping, Loss Grows to $50 (15 seconds later)")
    manager._fetch_net_delta_and_gamma.return_value = (0.16, 0.01)
    profit_usd = -50.0
    manager.manage_hedge(positions, -0.25, profit_usd)
    print(f"Hedge Active: {manager.hedge_active}, Size: {abs(execution_mock.hedge_size_btc):.4f} BTC")
    
    print("\n[Step 4] Emergency! Loss Hits 25%")
    manager._fetch_net_delta_and_gamma.return_value = (0.16, 0.01)
    profit_usd = -100.0
    manager.manage_hedge(positions, -0.30, profit_usd)
    print(f"Hedge Active: {manager.hedge_active}, Size: {abs(execution_mock.hedge_size_btc):.4f} BTC")

if __name__ == '__main__':
    test_dynamic_continuous_scaling()
