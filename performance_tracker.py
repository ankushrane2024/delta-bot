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

    def log_pro_trader_journal(self, trade_record, current_iv, dvol_status, size_multiplier, hedge_status):
        """Appends a highly detailed pro-trader markdown diary entry for deep-dive analysis."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        journal_file = os.path.join(base_dir, "scratch", "pro_trader_journal.md")
        os.makedirs(os.path.dirname(journal_file), exist_ok=True)
        
        # Format the diary entry
        pnl_status = "🟢 WIN" if trade_record['pnl'] > 0 else "🔴 LOSS" if trade_record['pnl'] < 0 else "⚪ FLAT"
        
        entry_text = (
            f"## 📝 Trade Diary - Date: {trade_record['date']} ({pnl_status})\n"
            f"- **Entry Time (IST)**: `{trade_record['entry_time']}`\n"
            f"- **Exit Time (IST)**: `{trade_record['exit_time']}`\n"
            f"- **Symbols**: Call: `{trade_record['call_symbol']}` | Put: `{trade_record['put_symbol']}`\n"
            f"- **Size Multiplier**: `{size_multiplier:.2f}x` | **Total Premium Collected**: `${trade_record['premium_collected']:.2f}`\n"
            f"- **Net P&L**: `${trade_record['pnl']:.2f}` | **Exit Reason**: `{trade_record['exit_reason']}`\n"
            f"- **Account Equity After**: `${trade_record['equity_after']:.2f}`\n"
            f"\n"
            f"### 📊 Volatility & Market Environment\n"
            f"- **DVOL Index**: `{dvol_status.get('current_dvol', 'N/A')}%` (Percentile: `{dvol_status.get('dvol_percentile', 'N/A')}%`)\n"
            f"- **Current IV**: `{current_iv:.1f}%`\n"
            f"- **Market Regime**: `{'Trending' if trade_record['regime_filter_enabled'] else 'Ranging'}` (ADX: `{trade_record.get('adx', 'N/A')}`)\n"
            f"\n"
            f"### 🛡️ Smart Hedging Telemetry\n"
            f"- **Hedging Triggered**: `{hedge_status.get('hedge_active', False)}` (Type: `{hedge_status.get('hedge_type', 'None')}`)\n"
            f"- **Futures Hedge Size**: `{hedge_status.get('hedge_size_btc', 0.0)} BTC` | **Tightened SL**: `{hedge_status.get('sl_tightened', False)}`\n"
            f"\n"
            f"### 🧠 Pro-Trader Post-Mortem Notes\n"
            f"> [!NOTE]\n"
            f"> **Performance Analysis**: This trade ended in a **{trade_record['exit_reason']}** with a net P&L of **${trade_record['pnl']:.2f}**. "
            f"DVOL was at **{dvol_status.get('current_dvol', 'N/A')}%** which directed our premium targets. "
            f"Smart hedging status was **{'active' if hedge_status.get('hedge_active', False) else 'inactive'}**. "
            f"This journal entry was captured automatically for subsequent quantitative analysis and optimization.\n"
            f"\n"
            f"---\n\n"
        )
        
        try:
            # Check if file exists, if not write header
            file_exists = os.path.exists(journal_file)
            with open(journal_file, 'a') as f:
                if not file_exists:
                    f.write("# 📓 Pro Trader Research Journal & Diary\n")
                    f.write("This journal contains a deep-dive technical diary of every trade executed by the bot. It is automatically parsed by the AI quantitative advisor for strategy improvements and risk optimizations.\n\n---\n\n")
                f.write(entry_text)
        except Exception as e:
            app_logger.error(f"Tracker: Failed to write to pro_trader_journal.md: {e}")

    def log_trade(self, entry_time, call_symbol, put_symbol, premium_collected, pnl, exit_reason, current_equity, 
                  regime_filter_enabled=False, current_iv=0.0, dvol_status=None, size_multiplier=1.0, hedge_status=None, adx=0.0):
        """Logs a completed trade with full details."""
        today = get_ist_date()
        dvol_status = dvol_status or {}
        hedge_status = hedge_status or {}
        
        trade_record = {
            "date": today,
            "entry_time": entry_time,
            "exit_time": (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).isoformat(),
            "call_symbol": call_symbol,
            "put_symbol": put_symbol,
            "premium_collected": premium_collected,
            "pnl": pnl,
            "exit_reason": exit_reason,
            "equity_after": current_equity,
            "regime_filter_enabled": regime_filter_enabled,
            "adx": adx
        }
        
        self.trades.append(trade_record)
        self.update_high_water_mark(current_equity)
        self._save_history()
        app_logger.info(f"Tracker: Logged trade -> {exit_reason} | PnL: ${pnl:.2f} | Filter: {'ON' if regime_filter_enabled else 'OFF'}")
        
        # Write to the pro-trader markdown diary for automated AI review
        self.log_pro_trader_journal(trade_record, current_iv, dvol_status, size_multiplier, hedge_status)

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

        # Comparison tracking
        trades_filter_off = [t for t in self.trades if not t.get("regime_filter_enabled", False)]
        trades_filter_on = [t for t in self.trades if t.get("regime_filter_enabled", False)]
        
        def calc_stats(trade_list):
            total = len(trade_list)
            wins = len([t for t in trade_list if t.get("pnl", 0) > 0])
            pnl = sum([t.get("pnl", 0) for t in trade_list])
            win_rate = (wins / total * 100) if total > 0 else 0.0
            # Calculate simple max drawdown for the subset
            peak = 0.0
            max_dd = 0.0
            for t in trade_list:
                eq = t.get("equity_after", 0)
                if eq > peak: peak = eq
                elif peak > 0:
                    dd = ((peak - eq) / peak) * 100.0
                    if dd > max_dd: max_dd = dd
            return {
                "trades": total,
                "win_rate": round(win_rate, 2),
                "pnl": round(pnl, 2),
                "max_drawdown": round(max_dd, 2)
            }
            
        stats_off = calc_stats(trades_filter_off)
        stats_on = calc_stats(trades_filter_on)

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
            },
            "comparison": {
                "filter_off": stats_off,
                "filter_on": stats_on
            }
        }
