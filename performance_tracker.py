import json
import os
from datetime import datetime, timezone, timedelta
from logger import app_logger

# IST helper
def get_ist_date():
    """Returns the current date string in IST."""
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime('%Y-%m-%d')

class PerformanceTracker:
    def __init__(self, filename="trade_history.json"):
        self.filename = filename
        self.history = self._load_history()
        self.max_equity = self.history.get("max_equity", 0.0)
        self.trades = self.history.get("trades", [])
        
    def _load_history(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r') as f:
                    return json.load(f)
            except Exception as e:
                app_logger.error(f"Tracker: Could not load history. {e}")
        return {"max_equity": 0.0, "trades": []}

    def _save_history(self):
        try:
            with open(self.filename, 'w') as f:
                json.dump({
                    "max_equity": self.max_equity,
                    "trades": self.trades
                }, f, indent=4)
        except Exception as e:
            app_logger.error(f"Tracker: Could not save history. {e}")

    def update_high_water_mark(self, current_equity):
        """Updates the peak equity to calculate accurate Max Drawdown."""
        if current_equity > self.max_equity:
            self.max_equity = current_equity
            self._save_history()

    def log_trade(self, entry_time, call_symbol, put_symbol, premium_collected, pnl, exit_reason, current_equity):
        """Logs a completed trade with full details."""
        today = get_ist_date()
        
        trade_record = {
            "date": today,
            "entry_time": entry_time,
            "exit_time": (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).isoformat(),
            "call_symbol": call_symbol,
            "put_symbol": put_symbol,
            "premium_collected": premium_collected,
            "pnl": pnl,
            "exit_reason": exit_reason,
            "equity_after": current_equity
        }
        
        self.trades.append(trade_record)
        self.update_high_water_mark(current_equity)
        self._save_history()
        app_logger.info(f"Tracker: Logged trade -> {exit_reason} | PnL: ${pnl:.2f}")

    def get_metrics(self, current_equity):
        """Calculates advanced performance metrics, splitting Today vs Overall."""
        today = get_ist_date()
        
        # Drawdown logic
        self.update_high_water_mark(current_equity)
        current_drawdown_pct = 0.0
        if self.max_equity > 0:
            current_drawdown_pct = ((self.max_equity - current_equity) / self.max_equity) * 100.0

        # Max drawdown historical check
        # We need to simulate peak-to-trough from all equity_after points
        peak = 0.0
        max_drawdown_pct = 0.0
        for t in self.trades:
            eq = t.get("equity_after", 0)
            if eq > peak:
                peak = eq
            elif peak > 0:
                dd = ((peak - eq) / peak) * 100.0
                if dd > max_drawdown_pct:
                    max_drawdown_pct = dd
                    
        # Include current drawdown in max drawdown check
        if current_drawdown_pct > max_drawdown_pct:
            max_drawdown_pct = current_drawdown_pct

        # Today metrics
        today_trades = [t for t in self.trades if t.get("date") == today]
        today_total = len(today_trades)
        today_wins = len([t for t in today_trades if t.get("pnl", 0) > 0])
        today_pnl = sum([t.get("pnl", 0) for t in today_trades])
        today_win_rate = (today_wins / today_total * 100) if today_total > 0 else 0.0

        # Overall metrics
        overall_total = len(self.trades)
        overall_wins = len([t for t in self.trades if t.get("pnl", 0) > 0])
        overall_pnl = sum([t.get("pnl", 0) for t in self.trades])
        overall_win_rate = (overall_wins / overall_total * 100) if overall_total > 0 else 0.0

        return {
            "today": {
                "trades": today_total,
                "win_rate": round(today_win_rate, 2),
                "pnl": round(today_pnl, 2)
            },
            "overall": {
                "trades": overall_total,
                "win_rate": round(overall_win_rate, 2),
                "pnl": round(overall_pnl, 2),
                "current_drawdown": round(current_drawdown_pct, 2),
                "max_drawdown": round(max_drawdown_pct, 2)
            }
        }
