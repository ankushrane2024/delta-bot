import time
from unittest.mock import MagicMock
from smart_hedging import SmartHedgingManager

def test_screenshot_simulation():
    print("=========================================================")
    print("  DYNAMIC RECOVERY HEDGE SIMULATION (SCREENSHOT REPLAY)  ")
    print("=========================================================\n")
    
    # 1. Setup Environment
    api_mock = MagicMock()
    execution_mock = MagicMock()
    execution_mock.hedge_size_btc = 0.0
    
    def mock_place_hedge(size, direction):
        print(f"   [ACTION] Bot executes MARKET {direction.upper()} of {size:.4f} BTC futures")
        execution_mock.hedge_size_btc += size if direction == 'sell' else -size
        return {'success': True, 'order_id': 'mock_123'}
    
    execution_mock.place_hedge_order.side_effect = mock_place_hedge
    
    dvol_mock = MagicMock()
    dvol_mock.get_current_dvol.return_value = 38.34 # From screenshot
    
    risk_mock = MagicMock()
    
    manager = SmartHedgingManager(execution_mock, dvol_mock, risk_mock, api_mock)
    
    # 2. Recreate the exact position from the screenshot
    # 500 contracts = 0.500 BTC exposure per leg. Total exposure = 0.500 BTC.
    positions = {
        'C-BTC-74600-020626': {'size': 500},
        'P-BTC-72800-020626': {'size': 500}
    }
    
    # Mock the delta fetching function to return exact net_delta from screenshot
    # Call Delta = 0.132, Put Delta = 0.000 (from screenshot) -> net_delta = 0.066
    
    print("=== TIME: 10:00 AM (Hedge Triggers at -$31.33) ===")
    print("Condition: Market begins dumping. Loss reaches -$31.33.")
    manager._fetch_net_delta_and_gamma = MagicMock(return_value=(0.066, 0.0002))
    unrealized_loss_pct = 31.33 / 211.11
    manager.manage_hedge(positions, unrealized_loss_pct, profit_usd=-31.33)
    print(f"-> Shield Active: {manager.hedge_active}")
    print(f"-> Shield Size:   {abs(execution_mock.hedge_size_btc):.4f} BTC\n")
    
    print("=== TIME: 10:15 AM (Loss grows to -$39.36, mimicking screenshot) ===")
    print("Condition: Market dumped further. Static hedge previously failed here.")
    # With continuous scaling, the bot should now instantly place a top-up order.
    unrealized_loss_pct = 39.36 / 211.11
    manager.manage_hedge(positions, unrealized_loss_pct, profit_usd=-39.36)
    print(f"-> Shield Active: {manager.hedge_active}")
    print(f"-> Shield Size:   {abs(execution_mock.hedge_size_btc):.4f} BTC\n")
    
    print("=== TIME: 10:30 AM (Loss grows to -$70.00) ===")
    print("Condition: Violent dump continues.")
    unrealized_loss_pct = 70.00 / 211.11
    manager.manage_hedge(positions, unrealized_loss_pct, profit_usd=-70.00)
    print(f"-> Shield Active: {manager.hedge_active}")
    print(f"-> Shield Size:   {abs(execution_mock.hedge_size_btc):.4f} BTC\n")
    
    print("=== TIME: 11:00 AM (Loss hits 45% Emergency Cutoff at -$95.00) ===")
    print("Condition: Extreme dump. The new bot_engine 45% Hard Stop will trigger BEFORE this,")
    print("but if it reached here, the hedge escalates to absolute maximum 2.5x over-hedge.")
    manager._fetch_net_delta_and_gamma = MagicMock(return_value=(0.150, 0.0002))
    unrealized_loss_pct = 95.00 / 211.11 # 45% loss
    manager.manage_hedge(positions, unrealized_loss_pct, profit_usd=-95.00)
    print(f"-> Shield Active: {manager.hedge_active}")
    print(f"-> Shield Size:   {abs(execution_mock.hedge_size_btc):.4f} BTC\n")

if __name__ == '__main__':
    test_screenshot_simulation()
