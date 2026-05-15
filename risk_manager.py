from config import RISK_PERCENT, STARTING_CAPITAL, BASE_CAPITAL_FOR_SCALING, BASE_LOTS_TARGET
from logger import app_logger

class RiskManager:
    def __init__(self, api_client):
        self.api_client = api_client
        self.current_equity = STARTING_CAPITAL

    def update_equity(self):
        """Fetch current equity from exchange."""
        try:
            res = self.api_client.get_balances()
            if res.get('success'):
                for b in res.get('result', []):
                    if b.get('asset_symbol') == 'USDT':
                        self.current_equity = float(b.get('available_balance', 0))
                        app_logger.info(f"Risk: Equity updated to ${self.current_equity:.2f}")
                        return
        except Exception as e:
            app_logger.error(f"Risk: Failed to update equity. Using fallback ${self.current_equity:.2f}. {e}")

    def calculate_lot_size(self):
        """
        Calculates exact lot size scaling based on user rules:
        Rule: "equal lots so total target = 500 lots per leg when capital is ₹50k"
        Scaling Formula: (Current Equity / 50000) * 500
        """
        # E.g., if equity is 50000, target is 500.
        # If equity is 25000, target is 250.
        total_lots_target = (self.current_equity / BASE_CAPITAL_FOR_SCALING) * BASE_LOTS_TARGET
        
        # We split the total lots across 3 entries (8:30, 9:00, 9:30)
        lots_per_entry = int(total_lots_target / 3)
        
        return max(1, lots_per_entry)

    def check_sl_tp(self, total_entry_premium, current_total_premium, pnl_pct):
        """
        Checks for Trailing SL, Partial Profit, and Square-off based strictly on rules.
        """
        # Partial Profit: Close 50% at 50% profit
        # Trailing SL: After 40% profit, trail to breakeven (0%)
        # Exit: at 70% profit
        # SL: Trigger when unrealized loss reaches 150% of collected premium (i.e., pnl_pct <= -1.50)
        
        action = None
        
        if pnl_pct >= 0.70:
            action = "TAKE_PROFIT_ALL"
        elif pnl_pct >= 0.50:
            action = "PARTIAL_PROFIT"
        elif pnl_pct >= 0.40:
            action = "TRAILING_SL_TRIGGERED"
            
        # SL condition: Unrealized loss is >= 150% of premium collected
        if pnl_pct <= -1.50:
            action = "STOP_LOSS_ALL"
            
        return action
