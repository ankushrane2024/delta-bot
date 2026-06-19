import json
import os
from datetime import datetime, timezone, timedelta
from logger import app_logger
import db_manager

# IST helper
def get_ist_date():
    """Returns the current date string in IST."""
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime('%Y-%m-%d')

class PerformanceTracker:
    """
    Permanent trade history tracker.

    Storage strategy (dual-layer — never lose data):
    ─────────────────────────────────────────────────
    PRIMARY:   Cloud DB (JSONBlob via db_manager) — survives Render restarts forever
    FALLBACK:  Local trade_history.json — used as backup/offline cache
    """

    def __init__(self, filename="trade_history.json"):
        self.filename = filename
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.filepath = os.path.join(base_dir, filename)

        # Load current state
        self._reload()

    def _reload(self):
        """Load history from Cloud DB (primary) or local JSON (fallback)."""
        cloud_error = False
        if db_manager.is_connected():
            cloud_data = db_manager.load_all_data()
            if cloud_data is None:
                # Network or SSL error occurred
                cloud_error = True
            elif cloud_data and "trades" in cloud_data:
                self.max_equity = cloud_data.get("max_equity", 0.0)
                self.trades = cloud_data.get("trades", [])
                # Also keep local JSON in sync as a backup copy
                self._write_local_backup()
                return

        # Fallback to local
        data = self._load_local()
        self.max_equity = data.get("max_equity", 0.0)
        self.trades = data.get("trades", [])
        
        # If we loaded from local but cloud is connected, sync up to cloud
        # ONLY IF there was no network error loading from the cloud.
        if db_manager.is_connected() and len(self.trades) > 0 and not cloud_error:
            app_logger.info("Tracker: Syncing local JSON up to Cloud DB...")
            db_manager.save_all_data({"max_equity": self.max_equity, "trades": self.trades})

    def _load_local(self) -> dict:
        """Load from local JSON file."""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r') as f:
                    return json.load(f)
            except Exception as e:
                app_logger.error(f"Tracker: Could not load local history. {e}")
        return {"max_equity": 0.0, "trades": []}

    def _write_local_backup(self):
        """Write a local JSON backup of the current trade history."""
        try:
            with open(self.filepath, 'w') as f:
                json.dump({
                    "max_equity": self.max_equity,
                    "trades": self.trades
                }, f, indent=4, default=str)
        except Exception as e:
            app_logger.warning(f"Tracker: Could not write local backup: {e}")

    def _save(self):
        """Save to both Cloud (primary) and local JSON (backup)."""
        data = {
            "max_equity": self.max_equity,
            "trades": self.trades
        }
        
        # Save to local backup always
        self._write_local_backup()
        
        # Sync to cloud
        if db_manager.is_connected():
            db_manager.save_all_data(data)

    def update_high_water_mark(self, current_equity):
        """Updates the peak equity to calculate accurate Max Drawdown."""
        if current_equity > self.max_equity:
            self.max_equity = current_equity
            self._save()

    def log_pro_trader_journal(self, trade_record, current_iv, dvol_status, size_multiplier, hedge_status):
        """Appends a highly detailed pro-trader markdown diary entry for deep-dive analysis."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        journal_file = os.path.join(base_dir, "scratch", "pro_trader_journal.md")
        os.makedirs(os.path.dirname(journal_file), exist_ok=True)

        pnl_status = "WIN" if trade_record['pnl'] > 0 else "LOSS" if trade_record['pnl'] < 0 else "FLAT"

        entry_text = (
            f"## Trade Diary - Date: {trade_record['date']} ({pnl_status})\n"
            f"- **Entry Time (IST)**: `{trade_record['entry_time']}`\n"
            f"- **Exit Time (IST)**: `{trade_record['exit_time']}`\n"
            f"- **Symbols**: Call: `{trade_record['call_symbol']}` | Put: `{trade_record['put_symbol']}`\n"
            f"- **Size Multiplier**: `{size_multiplier:.2f}x` | **Total Premium Collected**: `${trade_record['premium_collected']:.2f}`\n"
            f"- **Net P&L**: `${trade_record['pnl']:.2f}` | **Exit Reason**: `{trade_record['exit_reason']}`\n"
            f"- **Account Equity After**: `${trade_record['equity_after']:.2f}`\n"
            f"\n"
            f"### Volatility & Market Environment\n"
            f"- **DVOL Index**: `{dvol_status.get('current_dvol', 'N/A')}%` (Percentile: `{dvol_status.get('dvol_percentile', 'N/A')}%`)\n"
            f"- **Current IV**: `{current_iv:.1f}%`\n"
            f"- **Market Regime**: `{'Trending' if trade_record['regime_filter_enabled'] else 'Ranging'}` (ADX: `{trade_record.get('adx', 'N/A')}`)\n"
            f"\n"
            f"### Smart Hedging Telemetry\n"
            f"- **Hedging Triggered**: `{hedge_status.get('hedge_active', False)}` (Type: `{hedge_status.get('hedge_type', 'None')}`)\n"
            f"- **Futures Hedge Size**: `{hedge_status.get('hedge_size_btc', 0.0)} BTC` | **Tightened SL**: `{hedge_status.get('sl_tightened', False)}`\n"
            f"\n---\n\n"
        )

        try:
            file_exists = os.path.exists(journal_file)
            with open(journal_file, 'a', encoding='utf-8') as f:
                if not file_exists:
                    f.write("# Pro Trader Research Journal\n\n---\n\n")
                f.write(entry_text)
        except Exception as e:
            app_logger.error(f"Tracker: Failed to write to pro_trader_journal.md: {e}")

    def log_trade(self, entry_time, call_symbol, put_symbol, premium_collected, pnl, exit_reason, current_equity,
                  regime_filter_enabled=False, current_iv=0.0, dvol_status=None, size_multiplier=1.0, hedge_status=None,
                  adx=0.0, mode='PAPER', call_entry_price=0.0, put_entry_price=0.0, call_exit_price=0.0, put_exit_price=0.0,
                  hedge_pnl=0.0, max_pnl_pct=0.0, min_pnl_pct=0.0, max_pnl_time="", min_pnl_time=""):
        """
        Logs a completed trade to BOTH Cloud DB (permanent) and local JSON (backup).
        """
        today = get_ist_date()
        dvol_status = dvol_status or {}
        hedge_status = hedge_status or {}

        from utils import get_ist_now

        trade_record = {
            "date": today,
            "mode": mode,
            "entry_time": entry_time,
            "exit_time": get_ist_now().isoformat(),
            "call_symbol": call_symbol,
            "put_symbol": put_symbol,
            "call_entry_price": call_entry_price,
            "put_entry_price": put_entry_price,
            "call_exit_price": call_exit_price,
            "put_exit_price": put_exit_price,
            "premium_collected": premium_collected,
            "pnl": pnl,
            "hedge_pnl": hedge_pnl,
            "max_pnl_pct": max_pnl_pct,
            "min_pnl_pct": min_pnl_pct,
            "max_pnl_time": max_pnl_time,
            "min_pnl_time": min_pnl_time,
            "exit_reason": exit_reason,
            "equity_after": current_equity,
            "regime_filter_enabled": regime_filter_enabled,
            "adx": adx
        }

        # Update local state
        self.trades.append(trade_record)
        if current_equity > self.max_equity:
            self.max_equity = current_equity
            
        # Save to Cloud + Local Backup
        self._save()

        app_logger.info(
            f"Tracker: Trade logged [{ 'Cloud DB + Local JSON' if db_manager.is_connected() else 'Local JSON only' }] -> "
            f"{exit_reason} | PnL: ${pnl:.2f}"
        )

        # Write pro-trader journal
        self.log_pro_trader_journal(trade_record, current_iv, dvol_status, size_multiplier, hedge_status)

    def get_metrics(self, current_equity):
        """Calculates advanced performance metrics, splitting Today vs Overall."""
        today = get_ist_date()

        self.update_high_water_mark(current_equity)
        current_drawdown_pct = 0.0
        if self.max_equity > 0:
            current_drawdown_pct = ((self.max_equity - current_equity) / self.max_equity) * 100.0

        # Max drawdown historical
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

        if current_drawdown_pct > max_drawdown_pct:
            max_drawdown_pct = current_drawdown_pct

        today_trades = [t for t in self.trades if t.get("date") == today]
        today_total = len(today_trades)
        today_wins = len([t for t in today_trades if t.get("pnl", 0) > 0])
        today_pnl = sum([t.get("pnl", 0) for t in today_trades])
        today_win_rate = (today_wins / today_total * 100) if today_total > 0 else 0.0

        overall_total = len(self.trades)
        overall_wins = len([t for t in self.trades if t.get("pnl", 0) > 0])
        overall_pnl = sum([t.get("pnl", 0) for t in self.trades])
        overall_win_rate = (overall_wins / overall_total * 100) if overall_total > 0 else 0.0

        trades_filter_off = [t for t in self.trades if not t.get("regime_filter_enabled", False)]
        trades_filter_on = [t for t in self.trades if t.get("regime_filter_enabled", False)]

        def calc_stats(trade_list):
            total = len(trade_list)
            wins = len([t for t in trade_list if t.get("pnl", 0) > 0])
            pnl = sum([t.get("pnl", 0) for t in trade_list])
            win_rate = (wins / total * 100) if total > 0 else 0.0
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
