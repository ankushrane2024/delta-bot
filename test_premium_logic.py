import os
import sys
import logging
from unittest.mock import Mock, patch

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from bot_engine import DeltaTradingEngine

# Setup basic logging to see the output
logging.basicConfig(level=logging.INFO)

def test_premium_rejection():
    print("\n--- Running Premium Rejection Test ---")
    engine = DeltaTradingEngine()
    
    # Mock necessary components to simulate an entry cycle
    engine.execution = Mock()
    engine.execution.active_positions = {}
    engine.execution.mode = 'PAPER'
    
    engine.risk_manager = Mock()
    engine.risk_manager.current_equity = 50000.0
    
    engine.filters = Mock()
    engine.filters.get_filter_status.return_value = (True, "")
    engine.filters.get_market_regime.return_value = ("Sideways", 15.0, [])
    
    engine.dvol_provider = Mock()
    engine.strategy = Mock()
    
    # Simulate find_strikes returning options with premium < $100
    mock_call = {'symbol': 'C-BTC-60000', 'mark_price': 85.50}
    mock_put = {'symbol': 'P-BTC-50000', 'mark_price': 110.0}
    engine.strategy.find_strikes.return_value = (mock_call, mock_put)
    
    # Run entry cycle (force=True to bypass time/day checks)
    with patch('bot_engine.app_logger') as mock_logger:
        engine.run_entry_cycle(force=True)
        
        # Check if trade was rejected as expected
        print(f"Status: {engine.today_trade_status}")
        print(f"Reason: {engine.today_skip_reason}")
        
        if engine.today_trade_status == "Waiting for Valid Premium":
            print("\n✅ SUCCESS: Premium validation correctly blocked entry!")
        else:
            print("\n❌ FAILED: Premium validation did not block entry.")

if __name__ == "__main__":
    test_premium_rejection()
