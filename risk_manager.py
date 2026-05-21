import config
from logger import app_logger

class RiskManager:
    def __init__(self, api_client):
        self.api_client = api_client
        self.current_equity = config.STARTING_CAPITAL
        self.sl_multiplier = config.SL_PERCENT  # Default 1.50 (150% of premium)
        
    def update_equity(self):
        """Fetch current equity from exchange."""
        if config.BOT_MODE == 'PAPER':
            # Bypass API call in PAPER mode
            app_logger.info(f"Risk [PAPER]: Simulated equity is ${self.current_equity:.2f} (No live check)")
            return
        
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

    def tighten_stop_loss(self, level):
        """Tighten option SL during emergency hedging (e.g. 1.05 for 105%)."""
        self.sl_multiplier = level
        app_logger.warning(f"Risk: EMERGENCY SL tightened to {level*100:.1f}%")

    def get_dynamic_sl(self):
        """Returns the active SL multiplier."""
        return self.sl_multiplier

    def reset_sl_multiplier(self):
        """Reset SL to default level."""
        self.sl_multiplier = config.SL_PERCENT

    def calculate_max_risk_per_trade(self):
        """Returns the maximum absolute USDT risk allowed for a single trade based on 1.5% rule."""
        return self.current_equity * config.MAX_RISK_PER_TRADE_PCT

    def check_sl_tp(self, total_entry_premium, current_total_premium, pnl_pct):
        """
        Checks for Trailing SL, Partial Profit, and Square-off based strictly on rules.
        """
        # Partial Profit: Close 50% at 50% profit
        # Trailing SL: After 40% profit, trail to breakeven (0%)
        # Exit: at 70% profit
        # SL: Trigger when unrealized loss reaches sl_multiplier of collected premium
        
        action = None
        
        if pnl_pct >= config.EXIT_PROFIT_TARGET:
            action = "TAKE_PROFIT_ALL"
        elif pnl_pct >= config.PARTIAL_PROFIT_TRIGGER:
            action = "PARTIAL_PROFIT"
        elif pnl_pct >= config.TRAILING_SL_TRIGGER:
            action = "TRAILING_SL_TRIGGERED"
            
        # SL condition: Unrealized loss is >= sl_multiplier of premium collected (negative P&L)
        if pnl_pct <= -self.sl_multiplier:
            action = "STOP_LOSS_ALL"
            
        return action

