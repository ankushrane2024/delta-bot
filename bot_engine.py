import time
import schedule
import threading
import random
import config
from config import (
    BOT_MODE, ENTRY_TIMES, EXIT_TIME_START, MAX_DAILY_LOSS_PCT,
    STARTING_CAPITAL, MANUAL_TOTAL_LOTS,
    MAX_CONSECUTIVE_LOSSES_DAY, DAILY_LOSS_LIMIT_PCT, SL_PERCENT, HEDGE_RECHECK_INTERVAL,
    DVOL_MID_SIZE_BOOST, CONSECUTIVE_LOSS_REDUCE_PCT, CONSECUTIVE_LOSS_THRESHOLD,
    CONSECUTIVE_LOSS_COOLDOWN_TRADES, DAILY_LOSS_REDUCE_THRESHOLD, DAILY_LOSS_REDUCE_PCT,
    MAX_RISK_PER_TRADE_PCT, DAILY_LOSS_PAUSE_THRESHOLD, LOT_TO_BTC
)
from utils import get_ist_now, get_next_expiry_date, should_check_hedge, adjust_time_to_system_tz
from logger import app_logger, error_logger
from notifier import notifier
from api_client import DeltaIndiaClient
from risk_manager import RiskManager
from strategy import ShortStrangleStrategy
from execution import ExecutionHandler
from filters import TradingFilters
from performance_tracker import PerformanceTracker
from rule_verifier import verify_all_rules
from dvol_provider import DVOLProvider
from smart_hedging import SmartHedgingManager


class DeltaTradingEngine:
    def __init__(self):
        self.api_client = DeltaIndiaClient()
        self.dvol_provider = DVOLProvider()
        self.dvol_provider.start()
        self.risk_manager = RiskManager(self.api_client)
        self.strategy = ShortStrangleStrategy(self.api_client)
        self.execution = ExecutionHandler(self.api_client, mode=BOT_MODE)
        self.filters = TradingFilters(self.api_client, dvol_provider=self.dvol_provider)
        self.smart_hedging = SmartHedgingManager(self.execution, self.dvol_provider, self.risk_manager, self.api_client)
        self.performance_tracker = PerformanceTracker()
        self.current_trade_info = {"calls": [], "puts": []}
        
        self.is_running = True
        self.re_entry_count = 0
        self.daily_loss_hits = 0
        self.total_entry_premium = 0
        self.partial_profit_hit = False
        self.trailing_sl_active = False
        self.last_hedge_check_time = None
        self.daily_start_equity = 0
        self.latest_rule_report = None
        
        # New state variables for advanced position sizing & money management
        self.consecutive_loss_count = 0
        self.reduced_size_trades_remaining = 0
        self.size_multiplier = 1.0
        self.next_day_paused = False
        self.manual_pause = False  # Telegram manual pause
        self.daily_loss_pct = 0.0

        self.today_trade_status = "Pending"
        self.today_skip_reason = None
        self.skip_history = []  # List of {time, reason, status} for last 10 skips
        self.pnl_chart_data = []  # Live P&L chart snapshots: [{t, pnl, hedge_pnl}]
        
        self.market_regime_filter_enabled = False
        self.smart_hedging_enabled = True  # Hedging toggle
        self.current_market_regime = "Unknown"
        self.current_adx_value = 0.0
        self.adx_history = []
        self.hedging_triggered_today = False
        
        # PAPER mode enhancements
        self.paper_lot_multiplier = 1.0
        self.consecutive_losses = 0
        self.paper_trading_paused = False
        self.btc_price_history = []
        
        # IV Status fields
        self.current_iv = 0.0
        self.avg_7d_iv = 0.0
        self.iv_status = "Normal"
        self.last_iv_fetch_time = 0.0
        
        # 24/7 Option Chain Monitor Cache (NEW)
        self.cached_option_chain = []
        self.last_cache_time = 0.0
        self.trades_taken_today = 0
        
        # Populate rule report immediately for the UI
        self.run_rule_verification()

    def start(self):
        app_logger.info(f"Engine: Starting Delta BTC Options Bot in {BOT_MODE} mode with Capital: ${STARTING_CAPITAL}")
        notifier.notify_startup(BOT_MODE, STARTING_CAPITAL)
        
        # Connect WebSockets for zero-latency feeds
        self.api_client.start_ws()
        
        # Record starting equity for daily -3% loss check
        self.risk_manager.update_equity()
        self.daily_start_equity = self.risk_manager.current_equity
        
        # Schedule entry/exit adjusted dynamically to the Asia/Kolkata timezone (Section 5)
        for t in ENTRY_TIMES:
            schedule.every().day.at(t, "Asia/Kolkata").do(self.run_entry_cycle)
            app_logger.info(f"Engine: Scheduled daily morning entry {t} IST (Asia/Kolkata timezone)")
            
        schedule.every().day.at(EXIT_TIME_START, "Asia/Kolkata").do(self.run_exit_cycle)
        app_logger.info(f"Engine: Scheduled daily EOD hard exit {EXIT_TIME_START} IST (Asia/Kolkata timezone)")
        
        # Schedule rule verification & reporting adjusted dynamically
        schedule.every().day.at("09:30", "Asia/Kolkata").do(self.run_rule_verification)
        schedule.every().day.at("18:00", "Asia/Kolkata").do(self.run_rule_verification)
        schedule.every().day.at("17:30", "Asia/Kolkata").do(self.send_daily_report)
        schedule.every().day.at("17:30", "Asia/Kolkata").do(self.auto_backup_history)
        
        app_logger.info("Engine: Scheduled verification at 09:30/18:00 IST (Asia/Kolkata timezone)")
        app_logger.info("Engine: Scheduled daily report & backup at 17:30 IST (Asia/Kolkata timezone)")
        
        # Run rule verification once on startup (Moved to __init__)
        
        # Monitor thread for 24/7 option chain fetching
        chain_thread = threading.Thread(target=self.option_chain_monitor_loop, daemon=True)
        chain_thread.start()
        
        # Monitor thread for real-time risk/hedge
        monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        monitor_thread.start()
        
        while self.is_running:
            schedule.run_pending()
            time.sleep(1)

    def get_saved_lot_size(self):
        """Read lot_size.json if exists, else fallback to MANUAL_TOTAL_LOTS from config."""
        import json, os
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            path = os.path.join(base_dir, 'lot_size.json')
            if os.path.exists(path):
                with open(path, 'r') as f:
                    data = json.load(f)
                return int(data.get('total_lots', MANUAL_TOTAL_LOTS))
        except Exception as e:
            app_logger.error(f"Engine: Failed to read lot_size.json – {e}")
        return int(MANUAL_TOTAL_LOTS)

    def run_entry_cycle(self, force=False):
        app_logger.info(f"Engine: Entry cycle triggered (force={force})")
        
        if self.execution.active_positions:
            app_logger.warning("Engine: Trade already active. Cannot start a new entry cycle.")
            return
        if not force and self.manual_pause:
            app_logger.warning("Engine: Trading manually paused via Telegram. Skipping entry.")
            self.today_trade_status = "Trade Skipped"
            self.today_skip_reason = "Trading manually paused via Telegram"
            self._record_skip("Trading manually paused via Telegram")
            return

        # 1. Maximum 1 trade per day safety check (no same-day re-entry or RECOST)
        if not force and self.trades_taken_today >= 1:
            app_logger.warning("Engine: Maximum 1 trade per day rule met. Skipping entry.")
            self.today_trade_status = "Trade Skipped"
            self.today_skip_reason = "Maximum 1 trade per day limit met"
            self._record_skip("Maximum 1 trade per day limit met")
            return
            
        # Guard 3: Next day pause check (NEW — Section 5)
        if not force and self.next_day_paused:
            app_logger.warning("Engine: Paused today due to yesterday's >2.5% loss pause trigger")
            self.today_trade_status = "Trade Skipped"
            self.today_skip_reason = "Next day pause active (yesterday loss > 2.5%)"
            self._record_skip("Next day pause active (yesterday loss > 2.5%)")
            return
            
        # Guard 4: Daily consecutive loss stop (NEW — Section 5)
        if not force and self.daily_loss_hits >= MAX_CONSECUTIVE_LOSSES_DAY:
            app_logger.warning("Engine: Max consecutive losses hit today. Skipping entry.")
            self.today_trade_status = "Trade Skipped"
            self.today_skip_reason = "Max daily consecutive losses reached"
            self._record_skip("Max daily consecutive losses reached")
            return

        # Verify and Auto-Reconnect API in PAPER mode
        if getattr(self.execution, 'mode', 'PAPER') == 'PAPER':
            api_ok = self.verify_and_reconnect_api()
            app_logger.info(f"Engine [PAPER]: API connection status before trade entry: {'Connected' if api_ok else 'Disconnected'}")
            if not api_ok:
                app_logger.error("Engine [PAPER]: API connection failed after 3 attempts. Skipping trade!")
                notifier.notify_error("🚨 API connection failed - Trade skipped")
                self.today_trade_status = "Trade Skipped"
                self.today_skip_reason = "API connection failed - Trade skipped"
                self._record_skip("API connection failed — check internet/API key")
                return
        # 2. Daily Loss Limit Check
        self.risk_manager.update_equity()
        if not force and self.daily_start_equity > 0:
            loss_pct = (self.daily_start_equity - self.risk_manager.current_equity) / self.daily_start_equity
            self.daily_loss_pct = max(0.0, loss_pct)
            if loss_pct >= DAILY_LOSS_LIMIT_PCT:
                app_logger.warning("Engine: Daily -3% account loss limit hit. Stopping trading for the day.")
                self.today_trade_status = "Trade Skipped"
                self.today_skip_reason = "Daily Loss Limit Hit (-3%)"
                self._record_skip("Daily Loss Limit Hit (-3%) — trading stopped for today")
                return
        # 3. Filters
        if not force:
            passed, reason = self.filters.get_filter_status()
            if not passed:
                app_logger.info(f"Engine: Filters not passed: {reason}. Skipping entry.")
                self.today_trade_status = "Trade Skipped"
                self.today_skip_reason = reason
                self._record_skip(reason)
                return
            # Market Regime Filter
            regime, adx, history = self.filters.get_market_regime()
            self.current_market_regime = regime
            self.current_adx_value = adx
            self.adx_history = history
            if self.market_regime_filter_enabled:
                if regime == "Trending":
                    app_logger.info(f"Engine: Market Regime Filter active. Skipping trade due to Trending market (ADX: {adx:.2f}).")
                    self.today_trade_status = "Trade Skipped"
                    self.today_skip_reason = f"Market Trending (ADX {adx:.2f} > 25)"
                    self._record_skip(f"Market Regime = TRENDING (ADX {adx:.2f} > 25) — Sideways market required")
                    return
        # Find Strikes with DVOL Integration (MODIFIED)
        expiry = get_next_expiry_date()
        call_opt, put_opt = self.strategy.find_strikes(expiry_date=expiry, dvol_provider=self.dvol_provider)
        
        # User requested: "If no suitable strikes found → Skip the trade (do not force entry)"
        # Removed all fallback mechanisms that bypass premium filters.
        if not call_opt or not put_opt:
            app_logger.error("Engine: Could not find suitable strikes.")
            self.today_trade_status = "Trade Skipped"
            self.today_skip_reason = "No suitable strikes found"
            self._record_skip("No suitable strikes found matching DVOL premium targets")
            return
            
        # 4. Dynamic Position Sizing (NEW — Section 4)
        base_lots = self.get_saved_lot_size()
        adjusted_lots = self._apply_dynamic_sizing(base_lots)
        
        # Max risk per trade check (NEW — Section 5)
        if not force and not self._check_max_risk(adjusted_lots, call_opt, put_opt):
            app_logger.warning("Engine: Max risk check failed. Skipping entry.")
            self.today_trade_status = "Trade Skipped"
            self.today_skip_reason = "Max 1.5% risk per trade exceeded"
            self._record_skip("Max risk per trade (1.5% of equity) exceeded — position size too large")
            return
            
        per_entry_size = max(1, int(adjusted_lots / 2))
        
        # Execute
        self.execution.execute_strangle(call_opt, put_opt, per_entry_size)
        self.today_trade_status = "Trade Taken"
        self.today_skip_reason = None
        self.trades_taken_today += 1

        # Save trade details for tracking
        self.current_trade_info["entry_time"] = get_ist_now().isoformat()
        self._trade_start_ts = time.time()
        self.current_trade_info["calls"].append(call_opt['symbol'])
        self.current_trade_info["puts"].append(put_opt['symbol'])
        self.current_trade_info["max_pnl_pct"] = 0.0
        self.current_trade_info["min_pnl_pct"] = 0.0
        self.current_trade_info["max_pnl_time"] = ""
        self.current_trade_info["min_pnl_time"] = ""

        # Sub to WebSocket for these new symbols if not already
        self.api_client.subscribe_ws([call_opt['symbol'], put_opt['symbol']])

        # Fetch the exact entry prices that were simulated in active_positions (includes slippage)
        call_entry = self.execution.active_positions.get(call_opt['symbol'], {}).get('entry_price', call_opt['mark_price'])
        put_entry  = self.execution.active_positions.get(put_opt['symbol'], {}).get('entry_price', put_opt['mark_price'])
        # P&L Formula: Total_PnL = (Entry_Premium - Current_Premium) * Lots * LOT_TO_BTC
        # LOT_TO_BTC = 0.001 BTC per lot (Delta Exchange BTC Options contract size)
        btc_quantity = per_entry_size * LOT_TO_BTC
        total_premium_for_this_entry = (call_entry + put_entry) * btc_quantity
        self.total_entry_premium = total_premium_for_this_entry

        # Reset the watchdog timer on new trade entry so WebSocket has time to fetch the new symbols
        self.api_client.last_price_update_time = time.time()

        # Notify
        notifier.notify_entry(call_opt['symbol'], put_opt['symbol'], per_entry_size, total_premium_for_this_entry)

        # Smart Hedging Pipeline — Step 1
        # Cache entry premiums immediately for premium-direction fallback
        self.smart_hedging.set_entry_premiums(self.execution.active_positions)
        threading.Thread(target=self.smart_hedging.run_post_entry_hedge,
                         args=(self.execution.active_positions,), daemon=True).start()


    def run_exit_cycle(self):
        app_logger.info("Engine: Exit cycle triggered (Fixed Time Square-off)")
        
        # Calculate PnL for logging before closing
        if self.execution.active_positions:
            current_total_value = 0
            for sym, data in self.execution.active_positions.items():
                price = None
                ws_data = self.api_client.get_realtime_ticker(sym)
                if ws_data and 'mark_price' in ws_data:
                    price = float(ws_data['mark_price'])
                else:
                    res = self.api_client.get_tickers()
                    if res and res.get('success') and res.get('result'):
                        for item in res['result']:
                            if item.get('symbol') == sym:
                                price = float(item.get('mark_price', 0))
                                break
                
                if price is None or price <= 0:
                    price = data.get('entry_price', 0)
                    
                # P&L Formula: value = price * lots * LOT_TO_BTC (0.001 BTC per lot)
                current_total_value += price * data['size'] * LOT_TO_BTC
            
            # Always log the trade, even if total_entry_premium was somehow reset to 0
            entry_prem = self.total_entry_premium if self.total_entry_premium > 0 else current_total_value
            profit = entry_prem - current_total_value
            self._log_and_reset_trade(profit, "EOD Square-off")
            notifier.notify_full_exit("End of Day Square-off", profit)
                
        self.execution.close_all(reason="End of Day Square-off")
        self.smart_hedging.close_hedge()
        self.reset_daily_state()

    def run_test_order(self):
        """
        PAPER MODE ONLY — Pure simulation of a 1-lot strangle.
        Never places any real order on Delta Exchange.
        Applies realistic slippage + execution delay for accuracy.
        """
        app_logger.info("Engine [TEST]: run_test_order triggered")
        if getattr(self.execution, 'mode', 'PAPER') != 'PAPER':
            app_logger.warning("Engine [TEST]: Blocked — mode is LIVE")
            return False, "Test Order is only allowed in PAPER mode for safety."

        try:
            # ── Step 1: Find Strikes (3-attempt fallback, bypasses all entry filters) ──
            expiry = get_next_expiry_date()
            app_logger.info(f"Engine [TEST]: Searching strikes (Expiry: {expiry})...")

            call_opt, put_opt = self.strategy.find_strikes(expiry_date=expiry, check_premium=True)

            # User requested: "If no suitable strikes found → Skip the trade (do not force entry)"
            # Removed all fallback mechanisms that bypass premium filters for tests.
            if not call_opt or not put_opt:
                return False, "Could not find any suitable strikes even after bypassing all filters."

            call_sym  = call_opt['symbol']
            put_sym   = put_opt['symbol']
            call_entry = float(call_opt.get('mark_price', 0))
            put_entry  = float(put_opt.get('mark_price', 0))

            app_logger.info(
                f"Engine [TEST]: Strikes found — Call: {call_sym} @ {call_entry}, "
                f"Put: {put_sym} @ {put_entry}"
            )

            # ── Step 2: Simulated Entry (no API call, no margin check) ──
            # Always use the latest saved lot size from the dashboard panel (lot_size.json)
            saved_total = self.get_saved_lot_size()
            lots = int(saved_total / 2) if saved_total > 0 else 1
            if lots < 1:
                lots = 1
            app_logger.info(f"Engine [TEST]: Using saved lot size — total: {saved_total}, per leg: {lots}")
            entry_slippage = random.uniform(0.3, 1.2)   # small entry slippage
            simulated_call_entry = call_entry + entry_slippage
            simulated_put_entry  = put_entry  + entry_slippage
            # P&L Formula: PnL = (Entry_Premium - Exit_Premium) * Lots * LOT_TO_BTC
            # where LOT_TO_BTC = 0.001 BTC per lot (Delta Exchange BTC options contract)
            btc_quantity = lots * LOT_TO_BTC
            entry_premium_total  = (simulated_call_entry + simulated_put_entry) * btc_quantity

            app_logger.info(
                f"Engine [TEST]: PAPER Entry simulated. "
                f"Call entry: {simulated_call_entry:.4f}, Put entry: {simulated_put_entry:.4f} "
                f"(lots per leg: {lots}, entry slippage: +{entry_slippage:.2f})"
            )

            # ── Step 3: Simulated execution delay ──
            delay_ms = random.randint(200, 500)
            app_logger.info(f"Engine [TEST]: Simulating execution delay: {delay_ms}ms")
            time.sleep(delay_ms / 1000.0)

            # ── Step 4: Telegram alert — order placed ──
            notifier.notify_error(
                f"🧪 TEST ORDER SIMULATED (PAPER)\n"
                f"Call: {call_sym} @ ~{simulated_call_entry:.2f}\n"
                f"Put:  {put_sym} @ ~{simulated_put_entry:.2f}\n"
                f"Lots per leg: {lots}\n"
                f"Total Entry Premium: ~{entry_premium_total:.2f} USDT\n"
                f"Waiting 10s then auto-cancelling..."
            )

            # ── Step 5: Wait 10 seconds (simulating position hold) ──
            app_logger.info("Engine [TEST]: Waiting 10 seconds before simulated exit...")
            time.sleep(10)

            # ── Step 6: Simulated Exit with slippage ──
            avg_exit = (call_entry + put_entry) / 2
            exit_slippage = self.calculate_paper_slippage(is_sl=False, base_price=avg_exit)
            simulated_call_exit = call_entry + exit_slippage
            simulated_put_exit  = put_entry  + exit_slippage
            # Apply same BTC_Quantity conversion for exit premium
            exit_premium_total  = (simulated_call_exit + simulated_put_exit) * btc_quantity

            simulated_pnl = entry_premium_total - exit_premium_total
            pnl_inr       = simulated_pnl * 83.0   # USD → INR approx

            app_logger.info(
                f"Engine [TEST]: PAPER Exit simulated. "
                f"Exit slippage: {exit_slippage:.2f} pts. "
                f"Call exit: {simulated_call_exit:.4f}, Put exit: {simulated_put_exit:.4f}. "
                f"Simulated P&L: {simulated_pnl:+.4f} USDT (~Rs. {pnl_inr:+.2f})"
            )

            # ── Step 7: Final Telegram alert ──
            notifier.notify_error(
                f"✅ TEST ORDER COMPLETED (PAPER SIMULATION)\n"
                f"Call exit: {call_sym} @ ~{simulated_call_exit:.2f}\n"
                f"Put exit:  {put_sym} @ ~{simulated_put_exit:.2f}\n"
                f"Slippage applied: {exit_slippage:.2f} pts\n"
                f"Simulated P&L: {simulated_pnl:+.4f} USDT (~Rs. {pnl_inr:+.2f})\n"
                f"No real orders were placed."
            )

            return True, (
                f"Simulated successfully with slippage ({exit_slippage:.2f} pts). "
                f"Call: {call_sym}, Put: {put_sym}. "
                f"Simulated P&L: {simulated_pnl:+.4f} USDT (~Rs. {pnl_inr:+.2f})"
            )

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            app_logger.error(f"Engine [TEST]: Exception in run_test_order: {e}\n{tb}")
            return False, str(e)

    def option_chain_monitor_loop(self):
        """24/7 background Option Chain Monitor Loop."""
        app_logger.info("Engine: Starting 24/7 background Option Chain Monitor...")
        while self.is_running:
            try:
                res = self.api_client.get_tickers({
                    'contract_types': 'call_options,put_options',
                    'underlying_asset_symbol': 'BTC'
                })
                if res and res.get('success'):
                    tickers = res.get('result', [])
                    self.cached_option_chain = tickers
                    self.last_cache_time = time.time()
                    
                    # Update live IV — mark_iv is nested inside t['quotes']
                    ivs = []
                    for t in tickers:
                        quotes = t.get('quotes') or {}
                        iv_val = float(quotes.get('mark_iv', 0) or t.get('mark_vol', 0) or 0)
                        if iv_val > 0:
                            ivs.append(iv_val)
                    if ivs:
                        current_avg_iv = sum(ivs) / len(ivs)
                        self.current_iv = round(current_avg_iv * 100, 2)
                        
                    # Calculate 5d Average IV via filters
                    c_iv, a_iv = self.filters._update_and_get_iv()
                    if a_iv > 0:
                        self.avg_7d_iv = round(a_iv * 100, 2)
                        
                    # Bypassed for testing as requested by user
                    self.iv_status = "Bypassed"
                        
            except Exception as e:
                error_logger.error(f"Engine [Option Chain Monitor]: Fetch error: {e}")
                
            time.sleep(12)

    def run_rule_verification(self):
        text_report, results, pct = verify_all_rules()
        app_logger.info(text_report)
        self.latest_rule_report = {
            "results": results,
            "compliance": pct
        }

    def auto_backup_history(self):
        """Automatically backs up the primary cloud DB to the secondary cloud DB daily."""
        try:
            import db_manager
            primary_data = db_manager.load_all_data()
            if not primary_data or not primary_data.get('trades'):
                app_logger.warning("Auto-Backup: Primary database is empty or failed to load. Skipping backup.")
                return

            success = db_manager.save_backup_data(primary_data)
            if success:
                app_logger.info(f"Auto-Backup: Successfully backed up {len(primary_data['trades'])} trades to Secondary Cloud DB.")
                from notifier import notifier
                notifier.notify_info(f"💾 Auto-Backup Successful: {len(primary_data['trades'])} trades securely saved to Secondary Cloud DB.")
            else:
                app_logger.error("Auto-Backup: Failed to save to Secondary Cloud DB.")
                from notifier import notifier
                notifier.notify_error("⚠️ Auto-Backup Failed: Could not save to Secondary Cloud DB.")
        except Exception as e:
            app_logger.error(f"Auto-Backup Exception: {e}")

    def send_daily_report(self):
        """Automatically called at 17:30 IST to generate and send report."""
        success, msg = self.generate_actual_report()
        if success:
            metrics = self.performance_tracker.get_metrics(self.risk_manager.current_equity)
            overall = metrics.get('overall', {})
            notifier.notify_compliance_report(overall.get('win_rate', 0), overall.get('pnl', 0), overall.get('current_drawdown', 0))
        else:
            app_logger.error(f"Engine: Scheduled report failed: {msg}")
            notifier.notify_error(f"⚠️ Daily Report Generation FAILED\nReason: {msg}\nPlease check logs.")

    def generate_actual_report(self, date_str=None):
        """Builds the report data, generates PDF/Excel, and saves metadata."""
        import report_generator
        from utils import get_ist_now
        
        if date_str is None:
            date_str = get_ist_now().strftime('%Y-%m-%d')
            
        current_mode = getattr(self.execution, 'mode', 'PAPER')
        app_logger.info(f"Engine: Generating Actual Report for {date_str} (Mode: {current_mode})...")
        
        try:
            # 1. Collect trades for the date, filtered by current execution mode
            today_trades_raw = [
                t for t in self.performance_tracker.trades 
                if t.get("date") == date_str and t.get("mode", "PAPER") == current_mode
            ]
            
            # Map to report generator format
            today_trades = []
            for t in today_trades_raw:
                today_trades.append({
                    "entry_time": t.get("entry_time", ""),
                    "exit_time": t.get("exit_time", ""),
                    "call_strike": t.get("call_symbol", "N/A"),
                    "put_strike": t.get("put_symbol", "N/A"),
                    "call_entry_price": t.get("call_entry_price", 0.0),
                    "put_entry_price": t.get("put_entry_price", 0.0),
                    "call_exit_price": t.get("call_exit_price", 0.0),
                    "put_exit_price": t.get("put_exit_price", 0.0),
                    "entry_premium": t.get("premium_collected", 0),
                    "exit_reason": t.get("exit_reason", ""),
                    "pnl_usd": t.get("pnl", 0),
                    "mode": t.get("mode", "PAPER")
                })
                
            # 2. Calculate summary
            total_trades = len(today_trades)
            wins = len([t for t in today_trades if t.get("pnl_usd", 0) > 0])
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
            net_pnl_usd = sum([t.get("pnl_usd", 0) for t in today_trades])
            net_pnl_inr = net_pnl_usd * report_generator.USD_INR_RATE
            
            metrics = self.performance_tracker.get_metrics(self.risk_manager.current_equity)
            max_dd = metrics.get('overall', {}).get('max_drawdown', 0.0)
            
            # 3. Market conditions
            news_summary = "None"
            try:
                passed, reason = self.filters.get_filter_status()
                if not passed and "News" in reason:
                    news_summary = reason
            except: pass

            data = {
                "date": date_str,
                "mode": current_mode,
                "summary": {
                    "total_trades": total_trades,
                    "win_rate": win_rate,
                    "net_pnl_usd": net_pnl_usd,
                    "net_pnl_inr": net_pnl_inr,
                    "max_drawdown": max_dd,
                    "market_regime": self.current_market_regime,
                    "regime_filter_enabled": self.market_regime_filter_enabled
                },
                "trades": today_trades,
                "risk": {
                    "daily_loss_limit_hit": (self.daily_loss_hits >= 2),
                    "sl_hits": len([t for t in today_trades if "Stop Loss" in t['exit_reason']]),
                    "hedging_activity": "Active" if self.hedging_triggered_today else "None"
                },
                "market": {
                    "adx": self.current_adx_value,
                    "iv": self.filters._update_and_get_iv()[0],
                    "news": news_summary
                },
                "pdf_path": f"/reports/Daily_Report_{date_str}.pdf",
                "xlsx_path": f"/reports/Daily_Report_{date_str}.xlsx"
            }
            
            # 4. Generate files
            pdf_file = f"reports/Daily_Report_{date_str}.pdf"
            xlsx_file = f"reports/Daily_Report_{date_str}.xlsx"
            
            report_generator.generate_pdf_report(data, pdf_file)
            report_generator.generate_xlsx_report(data, xlsx_file)
            report_generator.save_report_data(data)
            
            # Send the actual files to Telegram for permanent off-server backup
            if os.path.exists(pdf_file):
                notifier.send_document(pdf_file, caption=f"📄 Daily Report PDF ({date_str})")
            if os.path.exists(xlsx_file):
                notifier.send_document(xlsx_file, caption=f"📊 Daily Report Excel ({date_str})")
            
            return True, f"Report for {date_str} generated successfully."
            
        except Exception as e:
            app_logger.error(f"Engine: Report generation error: {e}")
            return False, str(e)

    def monitor_loop(self):
        """Zero-latency real-time monitoring of PnL, SL/TP, and Hedging using WebSocket (with HTTP fallback)."""
        last_heartbeat = time.time()
        last_http_poll_time = 0
        last_regime_update = 0
        
        while self.is_running:
            try:
                # 5 minute heartbeat log
                if time.time() - last_heartbeat >= 300:
                    app_logger.info("Engine Heartbeat: Monitor loop is active and running 24/7.")
                    last_heartbeat = time.time()
                    
                # 60 second Market Regime live update
                if time.time() - last_regime_update >= 60:
                    try:
                        regime, adx, history = self.filters.get_market_regime()
                        self.current_market_regime = regime
                        self.current_adx_value = adx
                        self.adx_history = history
                    except Exception as e:
                        error_logger.error(f"Engine: Error updating Market Regime: {e}")
                    last_regime_update = time.time()

                
                # Maintain BTC Price History for 5-minute slippage checks (600s history)
                try:
                    btc_ws = self.api_client.get_realtime_ticker("BTCUSD")
                    if btc_ws and 'mark_price' in btc_ws:
                        current_btc_p = float(btc_ws['mark_price'])
                        self.btc_price_history.append((time.time(), current_btc_p))
                        self.btc_price_history = [x for x in self.btc_price_history if x[0] >= (time.time() - 600)]
                except Exception as btc_err:
                    error_logger.error(f"Error maintaining BTC history: {btc_err}")
                    
                # 15s WS Disconnect Alert
                if not self.api_client.ws_connected and self.api_client.ws_last_disconnect_time:
                    if time.time() - self.api_client.ws_last_disconnect_time > 15:
                        if not self.api_client.ws_alert_sent:
                            app_logger.error("Monitor: WebSocket disconnected for > 15s. Sending alert.")
                            notifier.notify_error("⚠️ WebSocket Disconnected > 15s. Bot is operating in HTTP Fallback Mode.")
                            self.api_client.ws_alert_sent = True
 
                if self.execution.active_positions:
                    # EOD Hard Exit Square-off Safeguard starting at 16:55 IST Same Day
                    try:
                        now_ist = get_ist_now()
                        current_time_minutes = now_ist.hour * 60 + now_ist.minute
                        # 16:55 IST is 1015 minutes, 17:00 IST is 1020 minutes
                        if current_time_minutes >= 1015:
                            app_logger.info(f"Engine Monitor Safeguard: Time is {now_ist.strftime('%H:%M')} IST (>= 16:55 IST) with active positions. Triggering EOD Force Square-off.")
                            self.run_exit_cycle()
                            continue
                    except Exception as time_err:
                        error_logger.error(f"Error checking time safeguard in monitor loop: {time_err}")
 
                    # 30-Second Critical Data Failure Safeguard (Only in LIVE mode to prevent paper simulation skips)
                    if self.execution.mode == 'LIVE' and time.time() - self.api_client.last_price_update_time > 30:
                        app_logger.critical("Engine: TOTAL DATA FAILURE > 30s. Triggering Emergency Auto Square-Off.")
                        notifier.notify_error("🚨 CRITICAL SAFEGUARD TRIGGERED 🚨\nTotal Data Failure (WS & HTTP) > 30s. Emergency Auto Square-Off executed to protect capital.")
                        self.execution.close_all(reason="Critical Data Failure (>30s)")
                        self.today_trade_status = "Emergency Auto Closed"
                        self.today_skip_reason = "Critical Data Failure (>30s)"
                        continue # Skip the rest of this loop iteration
 
                    # HTTP Polling Fallback Every 2 seconds
                    if time.time() - last_http_poll_time >= 2:
                        res = self.api_client.get_tickers()
                        if res and res.get('success') and res.get('result'):
                            data_list = res.get('result')
                            for sym in self.execution.active_positions.keys():
                                self.api_client.update_ticker_from_http(sym, data_list)
                        last_http_poll_time = time.time()
 
                    current_total_value = 0
                    net_delta = 0
                    total_gamma = 0
                    
                    any_leg_hit_sl = False
                    
                    for sym, data in self.execution.active_positions.items():
                        entry_price = data.get('entry_price', 0)
                        current_price = entry_price  # default fallback
                        price_is_valid = False
                        
                        # Read directly from WebSocket memory cache
                        ws_data = self.api_client.get_realtime_ticker(sym)
                        if ws_data and 'mark_price' in ws_data:
                            candidate_price = float(ws_data['mark_price'])
                            
                            # Price Sanity Guard: allow up to 1000% spikes so SL can trigger
                            price_is_valid = (
                                candidate_price > 0.01 and
                                entry_price > 0 and
                                abs(candidate_price - entry_price) / entry_price < 10.0
                            )
                            
                            if price_is_valid:
                                current_price = candidate_price
                                data['last_good_price'] = candidate_price
                                
                                greeks = ws_data.get('greeks') or {}
                                if 'delta' in greeks:
                                    d = float(greeks.get('delta', 0))
                                    g = float(greeks.get('gamma', 0))
                                    # Short positions -> invert delta/gamma
                                    net_delta -= d * data['size']
                                    total_gamma -= g * data['size']
                                    # Cache greeks
                                    data['last_known_delta'] = d
                                    data['last_known_gamma'] = g
                                else:
                                    # Fallback to cached greeks if raw greeks are missing in this tick
                                    last_d = data.get('last_known_delta')
                                    last_g = data.get('last_known_gamma', 0)
                                    if last_d is not None:
                                        net_delta -= last_d * data['size']
                                        total_gamma -= last_g * data['size']
                                        
                        if not price_is_valid:
                            # Try last good price, otherwise absolute fallback to entry_price
                            lgp = data.get('last_good_price')
                            if lgp and lgp > 0.01:
                                current_price = lgp
                            else:
                                current_price = entry_price
                            
                            # Fallback to cached greeks
                            last_d = data.get('last_known_delta')
                            last_g = data.get('last_known_gamma', 0)
                            if last_d is not None:
                                net_delta -= last_d * data['size']
                                total_gamma -= last_g * data['size']
                                
                        # Check Single Leg Stop Loss (Loss is negative profit, e.g. -1.30)
                        if entry_price > 0:
                            leg_loss_pct = (entry_price - current_price) / entry_price
                            if leg_loss_pct <= -config.SL_PERCENT:
                                any_leg_hit_sl = True
                                
                        # P&L Formula: value = price * lots * LOT_TO_BTC (0.001 BTC per lot)
                        current_total_value += current_price * data['size'] * LOT_TO_BTC
                    profit = 0.0
                    pnl_pct = 0.0
                    
                    if self.total_entry_premium > 0:
                        # PnL Check
                        collected_premium = self.total_entry_premium
                        current_option_value = current_total_value
                        
                        # For short positions, options profit = collected_premium - current_option_value
                        options_profit = collected_premium - current_option_value
                        
                        # Add Hedge Profit to represent True Total PnL
                        hedge_pnl = self.smart_hedging.get_live_hedge_pnl() if getattr(self, 'smart_hedging', None) and self.smart_hedging.hedge_active else 0.0
                        profit = options_profit + hedge_pnl
                        
                        pnl_pct = profit / collected_premium
                        
                        # Emergency Trade Loss Limit (-45% on the active trade)
                        if pnl_pct <= -0.45:
                            app_logger.critical(f"Engine: EMERGENCY 45% LOSS LIMIT HIT on active trade! Loss: {pnl_pct*100:.2f}%. Triggering immediate full square-off.")
                            notifier.notify_error(f"🚨 EMERGENCY 45% LOSS LIMIT HIT 🚨\nTrade loss reached {pnl_pct*100:.2f}%. Triggering immediate full square-off of all legs and hedges.")
                            self.execution.close_all(reason="Emergency 45% Trade Loss Hit")
                            self.reset_daily_state()
                            self.today_trade_status = "Emergency Auto Closed"
                            self.today_skip_reason = "Emergency 45% Trade Loss Hit"
                            self.daily_loss_hits += 2 # Block future trades for the day
                            continue
                            
                        # Continuous Daily Loss Limit Check (2% at any time)
                        if self.daily_start_equity > 0:
                            floating_equity = self.risk_manager.current_equity + profit
                            loss_pct = (self.daily_start_equity - floating_equity) / self.daily_start_equity
                            if loss_pct >= 0.02:
                                app_logger.critical(f"Engine: Daily -2% loss limit hit on floating equity! Floating loss: {loss_pct*100:.2f}%. Triggering immediate emergency full square-off.")
                                notifier.notify_error(f"🚨 DAILY LOSS LIMIT HIT (-2%) 🚨\nFloating equity loss reached {loss_pct*100:.2f}%. Triggering immediate full square-off.")
                                self.execution.close_all(reason="Daily Loss Limit Hit (-2%)")
                                self.reset_daily_state()
                                self.today_trade_status = "Emergency Auto Closed"
                                self.today_skip_reason = "Daily 2% Floating Loss Hit"
                                self.daily_loss_hits += 2 # Block future trades for the day
                                continue
                        
                        action = self.risk_manager.check_sl_tp(collected_premium, current_option_value, pnl_pct)
                        
                        # Override action if ANY individual leg hit the Stop Loss
                        if any_leg_hit_sl:
                            action = "STOP_LOSS_ALL"
                        
                        # Safely compute time in trade (fallback to time.time() if None to yield 0s)
                        start_ts = getattr(self, '_trade_start_ts', None) or time.time()
                        time_in_trade_seconds = time.time() - start_ts
                        
                        # Detailed debug logging required for profit verification
                        hedge_log = f" | Hedge PnL: +${self.smart_hedging.get_live_hedge_pnl():.2f}" if self.smart_hedging.hedge_active else ""
                        app_logger.info(f"Engine [DEBUG] Profit Check: entry_total={collected_premium:.4f} | current_total={current_option_value:.4f} | pnl_pct={pnl_pct*100:.2f}% | target={config.EXIT_PROFIT_TARGET*100:.2f}% | time_in_trade={time_in_trade_seconds:.1f}s{hedge_log}")
                        
                        # Update Max/Min Excursion Tracking
                        if pnl_pct > self.current_trade_info.get("max_pnl_pct", -999.0):
                            self.current_trade_info["max_pnl_pct"] = pnl_pct
                            self.current_trade_info["max_pnl_time"] = get_ist_now().isoformat()
                        if pnl_pct < self.current_trade_info.get("min_pnl_pct", 999.0):
                            self.current_trade_info["min_pnl_pct"] = pnl_pct
                            self.current_trade_info["min_pnl_time"] = get_ist_now().isoformat()

                        # ── Live P&L Chart Snapshot (1 point per 60s) ──
                        # Stores 1 point per minute → max 480 pts for a full 9AM-5PM day.
                        # NEVER deletes old data so 9AM entry is always visible on chart.
                        _now_ts = time.time()
                        _last_chart_ts = getattr(self, '_last_chart_snapshot_ts', 0)
                        if _now_ts - _last_chart_ts >= 60 or len(self.pnl_chart_data) == 0:
                            self._last_chart_snapshot_ts = _now_ts
                            hedge_pnl_now = self.smart_hedging.get_live_hedge_pnl() if self.smart_hedging.hedge_active else 0.0
                            # FIX: Use options_profit (not profit) because profit already includes hedge_pnl
                            self.pnl_chart_data.append({
                                "t": get_ist_now().strftime("%H:%M"),
                                "pnl": round(options_profit, 4),
                                "hedge": round(hedge_pnl_now, 4),
                                "total": round(options_profit + hedge_pnl_now, 4)
                            })

                        if self.trailing_sl_active and pnl_pct <= 0.0:
                            action = "TRAILING_SL_EXIT"
                            
                        # Prevent premature profit target execution (Race Condition / Price Stability Guard)
                        if time_in_trade_seconds < getattr(config, 'MIN_HOLD_SECONDS', 30):
                            if action in ["TAKE_PROFIT_ALL", "PARTIAL_PROFIT"]:
                                app_logger.info(f"Engine [DEBUG] Suppressing {action} because time_in_trade ({time_in_trade_seconds:.1f}s) < {getattr(config, 'MIN_HOLD_SECONDS', 30)}s")
                                action = None
                            
                            # Hard-suppress ALL exits (including Stop Loss and Trailing SL) for the first 15 seconds to survive initial spread crossing
                            if action is not None and time_in_trade_seconds < 15:
                                app_logger.warning(f"Engine [DEBUG] Hard-Suppressing {action} because time_in_trade ({time_in_trade_seconds:.1f}s) < 15s (spread stabilization)")
                                action = None
                        
                        if action in ["STOP_LOSS_ALL", "TAKE_PROFIT_ALL", "TRAILING_SL_EXIT"]:
                            # Apply slippage and execution delay in PAPER mode
                            if getattr(self.execution, 'mode', 'PAPER') == 'PAPER':
                                is_sl = (action == "STOP_LOSS_ALL")
                                total_size = sum([d['size'] for d in self.execution.active_positions.values()])
                                avg_price = current_option_value / (total_size * LOT_TO_BTC) if total_size > 0 else None
                                slippage_per_lot = self.calculate_paper_slippage(is_sl, base_price=avg_price)
                                total_slippage = slippage_per_lot * total_size * LOT_TO_BTC
                                adjusted_profit = profit - total_slippage
                                
                                # Execution delay of 200-500 milliseconds
                                delay = random.uniform(0.2, 0.5)
                                app_logger.info(f"Engine [PAPER]: Delaying trade exit by {delay*1000:.0f}ms...")
                                time.sleep(delay)
                                
                                # Log the decision
                                app_logger.info(f"Engine [PAPER] Slippage Log: timestamp={time.time()} | original_price={current_option_value:.4f} | price_after_slippage={current_option_value + total_slippage:.4f} | lot_size={total_size} | reason_for_change={action} | api_connected={'Connected' if self.api_client.ws_connected else 'Disconnected'}")
                                
                                profit = adjusted_profit
                        
                        if action == "STOP_LOSS_ALL":
                            sl_pct = int(config.SL_PERCENT * 100)
                            app_logger.warning(f"Engine: Combined {sl_pct}% Stop Loss Hit!")
                            self._log_and_reset_trade(profit, f"Stop Loss Hit (-{sl_pct}%)")
                            self.execution.close_all(reason=f"Stop Loss Hit (-{sl_pct}%)")
                            notifier.notify_stop_loss(profit, False) # RECOST is completely disabled
                        
                        elif action == "TAKE_PROFIT_ALL":
                            pt_pct = int(config.EXIT_PROFIT_TARGET * 100)
                            app_logger.info(f"Engine: Profit Target Hit ({pt_pct}%)!")
                            self._log_and_reset_trade(profit, f"Profit Target Hit ({pt_pct}%)")
                            self.execution.close_all(reason=f"Profit Target Hit ({pt_pct}%)")
                            notifier.notify_full_exit(f"Profit Target ({pt_pct}%)", profit)
                            
                        elif action == "TRAILING_SL_EXIT":
                            app_logger.info("Engine: Trailing Stop Loss Hit (Breakeven)!")
                            self._log_and_reset_trade(profit, "Trailing SL Hit")
                            self.execution.close_all(reason="Trailing SL Hit")
                            notifier.notify_full_exit("Trailing SL Hit (Breakeven)", profit)
                        
                        elif action == "PARTIAL_PROFIT" and not self.partial_profit_hit:
                            app_logger.info("Engine: Partial Profit Triggered (50%)")
                            self.execution.partial_close(percentage=0.5)
                            self.partial_profit_hit = True
                            notifier.notify_partial_profit(profit)
  
                        elif action == "TRAILING_SL_TRIGGERED" and not self.trailing_sl_active:
                            app_logger.info("Engine: Trailing SL to BE active")
                            self.trailing_sl_active = True
                            notifier.notify_trailing_sl()
 
                    # ── Smart Hedge Management ──────────────────────────────────────
                    # CRITICAL FIX: Hedge check runs INDEPENDENTLY of all_prices_available.
                    # Even if WebSocket prices are partially missing, we still attempt to hedge
                    # based on whatever delta/loss data we DO have.
                    #
                    # Dynamic interval: 5s when losing >10% or after 3PM, 15s otherwise.
                    # This ensures we catch sudden BTC spikes (like the 3PM move) quickly.
                    _now_ist_h = get_ist_now().hour
                    _is_volatile = (_now_ist_h >= 15) or (pnl_pct < -0.10)
                    _hedge_interval = 5 if _is_volatile else 15  # 5s volatile / 15s normal

                    if not self.last_hedge_check_time or (time.time() - self.last_hedge_check_time >= _hedge_interval):
                        self.last_hedge_check_time = time.time()
                        # unrealized_loss_pct is positive when losing
                        unrealized_loss_pct = max(0.0, -pnl_pct)
                        app_logger.info(
                            f"Hedge: Running manage_hedge | interval={_hedge_interval}s | "
                            f"unrealized_loss={unrealized_loss_pct*100:.2f}% | "
                            f"loss_usd={-profit:.2f} | "
                            f"volatile={'YES' if _is_volatile else 'NO'}"
                        )
                        adx_value = self.current_adx_value if hasattr(self, 'current_adx_value') else 0.0
                        atr_usd = self.filters.get_btc_atr() if hasattr(self, 'filters') and self.filters else 100.0
                        if self.smart_hedging_enabled:
                            try:
                                self.smart_hedging.manage_hedge(
                                    self.execution.active_positions, unrealized_loss_pct, profit, adx_value, atr_usd
                                )
                                self.hedging_triggered_today = self.smart_hedging.hedge_active
                            except Exception as hedge_err:
                                error_logger.error(f"Monitor: HEDGE ERROR (isolated): {hedge_err}")
                                notifier.notify_error(f"⚠️ Hedge check error (non-fatal): {hedge_err}")
                        else:
                            app_logger.info("Hedge: Skipped - Smart Hedging is DISABLED.")
                    # ────────────────────────────────────────────────────────────────

                else:
                    time.sleep(1) # Sleep slightly longer if no positions
                    
                time.sleep(0.5) # High frequency tight loop
            except Exception as e:
                error_logger.error(f"Monitor: Error in monitor loop: {e}")
                notifier.notify_error(f"Bot stopped or error occurred: {e}")
                time.sleep(5)

    def reset_daily_state(self):
        self.re_entry_count = 0
        self.daily_loss_hits = 0
        self.total_entry_premium = 0
        self.partial_profit_hit = False
        self.trailing_sl_active = False
        self.smart_hedging.hedge_stopped_out = False
        self.last_hedge_check_time = None
        self.hedging_triggered_today = False
        self._trade_start_ts = None
        self.current_trade_info = {"calls": [], "puts": []}
        self.risk_manager.update_equity()
        self.daily_start_equity = self.risk_manager.current_equity
        self.today_trade_status = "Pending"
        self.today_skip_reason = None
        self.trades_taken_today = 0
        self.next_day_paused = False  # CRITICAL FIX: Must reset so bot can trade the next day
        
        # Reset PAPER-specific state at EOD
        self.consecutive_losses = 0
        self.paper_trading_paused = False
        app_logger.info("Engine: Daily state reset.")

    def _log_and_reset_trade(self, profit, reason):
        if self.current_trade_info.get("calls"):
            c_syms = ",".join(self.current_trade_info["calls"])
            p_syms = ",".join(self.current_trade_info["puts"])
            
            # Capture entry and exit prices for reporting
            call_entry_price = 0.0
            put_entry_price = 0.0
            call_exit_price = 0.0
            put_exit_price = 0.0
            
            for sym in self.current_trade_info.get("calls", []):
                data = self.execution.active_positions.get(sym, {})
                call_entry_price += data.get('entry_price', 0.0)
                ws_data = self.api_client.get_realtime_ticker(sym)
                if ws_data and 'mark_price' in ws_data:
                    call_exit_price += float(ws_data['mark_price'])
                else:
                    call_exit_price += data.get('entry_price', 0.0)

            for sym in self.current_trade_info.get("puts", []):
                data = self.execution.active_positions.get(sym, {})
                put_entry_price += data.get('entry_price', 0.0)
                ws_data = self.api_client.get_realtime_ticker(sym)
                if ws_data and 'mark_price' in ws_data:
                    put_exit_price += float(ws_data['mark_price'])
                else:
                    put_exit_price += data.get('entry_price', 0.0)
            
            # Calculate realized Hedge PnL if hedge is active before we close it
            hedge_pnl = self.smart_hedging.get_live_hedge_pnl() if self.smart_hedging.hedge_active else 0.0
            
            # Update simulated equity and lot multiplier in PAPER mode
            if getattr(self.execution, 'mode', 'PAPER') == 'PAPER':
                self.risk_manager.current_equity += profit + hedge_pnl
                
                # Check if it is a winning trade or losing trade
                if (profit + hedge_pnl) > 0:
                    # Win: Increase by +5%, cap at 1.30 (130%)
                    self.paper_lot_multiplier = min(1.30, self.paper_lot_multiplier + 0.05)
                    self.consecutive_losses = 0
                    app_logger.info(f"Engine [PAPER]: Winning trade (+${profit+hedge_pnl:.2f}). New Lot Multiplier: {self.paper_lot_multiplier*100:.1f}%. Consecutive Losses reset to 0.")
                else:
                    # Loss
                    self.consecutive_losses += 1
                    if self.consecutive_losses == 1:
                        self.paper_lot_multiplier = max(0.10, self.paper_lot_multiplier - 0.10)
                        app_logger.info(f"Engine [PAPER]: Losing trade (-${abs(profit+hedge_pnl):.2f}). 1st loss. New Lot Multiplier: {self.paper_lot_multiplier*100:.1f}%.")
                    elif self.consecutive_losses == 2:
                        self.paper_lot_multiplier = max(0.10, self.paper_lot_multiplier - 0.20)
                        app_logger.info(f"Engine [PAPER]: Losing trade (-${abs(profit+hedge_pnl):.2f}). 2nd consecutive loss. New Lot Multiplier: {self.paper_lot_multiplier*100:.1f}%.")
                    elif self.consecutive_losses >= 3:
                        self.paper_trading_paused = True
                        app_logger.warning(f"Engine [PAPER]: 3 consecutive losses! Pausing paper trading for the rest of the day. Lot Multiplier remains: {self.paper_lot_multiplier*100:.1f}%.")
                        notifier.notify_error("⚠️ PAPER TRADING PAUSED ⚠️\n3 consecutive losses reached in PAPER mode. Trading paused for today.")

            # Advanced Money Management state updates
            if profit <= 0:
                self.consecutive_loss_count += 1
                self.daily_loss_hits += 1
                if self.consecutive_loss_count >= CONSECUTIVE_LOSS_THRESHOLD:
                    self.reduced_size_trades_remaining = CONSECUTIVE_LOSS_COOLDOWN_TRADES
                    app_logger.info(f"Engine: {self.consecutive_loss_count} consecutive losses. Cooldown of {self.reduced_size_trades_remaining} trades activated.")
            else:
                self.consecutive_loss_count = 0
                
            if self.reduced_size_trades_remaining > 0:
                self.reduced_size_trades_remaining -= 1
                app_logger.info(f"Engine: Decremented cooldown trades remaining to {self.reduced_size_trades_remaining}")

            self.risk_manager.update_equity()
            if self.daily_start_equity > 0:
                loss_pct = (self.daily_start_equity - self.risk_manager.current_equity) / self.daily_start_equity
                self.daily_loss_pct = max(0.0, loss_pct)
                
                if self.daily_loss_pct >= DAILY_LOSS_PAUSE_THRESHOLD:
                    self.next_day_paused = True
                    app_logger.warning(f"Engine: Daily loss {self.daily_loss_pct*100:.2f}% >= 2.5%. Next day trading paused.")
                    notifier.notify_next_day_paused(self.daily_loss_pct * 100)
                    
                if self.daily_loss_pct >= DAILY_LOSS_LIMIT_PCT:
                    app_logger.critical(f"Engine: Daily loss limit hit: {self.daily_loss_pct*100:.2f}%")
                    notifier.notify_daily_loss_limit(self.daily_loss_pct * 100, self.risk_manager.current_equity)
                    
                if self.daily_loss_pct >= DAILY_LOSS_REDUCE_THRESHOLD:
                    self.size_multiplier = min(1.0, self.size_multiplier)

            dvol_status = self.dvol_provider.get_status() if getattr(self, 'dvol_provider', None) else {}
            hedge_status = self.smart_hedging.get_status() if getattr(self, 'smart_hedging', None) else {}
            self.performance_tracker.log_trade(
                entry_time=self.current_trade_info.get("entry_time", ""),
                call_symbol=c_syms,
                put_symbol=p_syms,
                premium_collected=self.total_entry_premium,
                pnl=profit,
                exit_reason=reason,
                current_equity=self.risk_manager.current_equity,
                regime_filter_enabled=self.market_regime_filter_enabled,
                current_iv=getattr(self, 'current_iv', 0.0),
                dvol_status=dvol_status,
                size_multiplier=getattr(self, 'size_multiplier', 1.0),
                hedge_status=hedge_status,
                adx=getattr(self, 'current_adx_value', 0.0),
                mode=getattr(self.execution, 'mode', 'PAPER'),
                call_entry_price=call_entry_price,
                put_entry_price=put_entry_price,
                call_exit_price=call_exit_price,
                put_exit_price=put_exit_price,
                hedge_pnl=hedge_pnl,
                max_pnl_pct=self.current_trade_info.get("max_pnl_pct", 0.0),
                min_pnl_pct=self.current_trade_info.get("min_pnl_pct", 0.0),
                max_pnl_time=self.current_trade_info.get("max_pnl_time", ""),
                min_pnl_time=self.current_trade_info.get("min_pnl_time", ""),
                chart_data=list(self.pnl_chart_data)  # Snapshot saved permanently with trade
            )
            self.current_trade_info = {"calls": [], "puts": []}
            self.pnl_chart_data = []  # Clear chart for next trade
            self.total_entry_premium = 0
            self.partial_profit_hit = False
            self.trailing_sl_active = False
            self.last_hedge_check_time = None
            self.hedging_triggered_today = False
            self._trade_start_ts = None
            
            # Automatically generate actual report for today immediately upon trade square-off/logging
            try:
                self.generate_actual_report()
                app_logger.info("Engine: Successfully generated automatic daily report post-trade close.")
            except Exception as rep_err:
                app_logger.error(f"Engine: Automatic report post-close failed: {rep_err}")

            # Generate P&L chart screenshot and send to Telegram as permanent record
            try:
                import chart_generator
                current_trade_info = {
                    'pnl': profit,
                    'hedge_pnl': hedge_pnl,
                    'exit_reason': reason,
                    'call_symbol': c_syms,
                    'put_symbol': p_syms,
                }
                chart_path = chart_generator.generate_trade_close_chart(
                    trades=self.performance_tracker.trades,
                    current_trade=current_trade_info
                )
                if chart_path and os.path.exists(chart_path):
                    from utils import get_ist_now
                    ist_now = get_ist_now()
                    date_str = ist_now.strftime('%Y-%m-%d')
                    pnl_sign = '+' if profit >= 0 else ''
                    caption = (
                        f"📊 <b>Trade Close Chart — {date_str}</b>\n"
                        f"Exit: {reason}\n"
                        f"P&L: {pnl_sign}${profit:.2f} | Hedge: ${hedge_pnl:.2f}\n"
                        f"Equity: ${self.risk_manager.current_equity:.2f}"
                    )
                    notifier.send_document(chart_path, caption=caption)
                    app_logger.info(f"Engine: Trade close chart sent to Telegram: {chart_path}")
            except Exception as chart_err:
                app_logger.error(f"Engine: Chart generation/send failed: {chart_err}")

            # Send full trade_history.json to Telegram as ultimate backup
            try:
                history_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trade_history.json')
                if os.path.exists(history_file):
                    trade_count = len(self.performance_tracker.trades)
                    notifier.send_document(history_file, caption=f"💾 <b>Trade History Backup</b>\n{trade_count} trades saved | Equity: ${self.risk_manager.current_equity:.2f}")
                    app_logger.info("Engine: trade_history.json backup sent to Telegram.")
            except Exception as backup_err:
                app_logger.error(f"Engine: History backup send failed: {backup_err}")

    def _apply_dynamic_sizing(self, base_lots):
        """Hardcoded to 500 lots per leg for testing, skipping all money management."""
        app_logger.info(f"Engine: Dynamic sizing and money management bypassed for testing. Forced 500 lots.")
        return 500

    def _check_max_risk(self, lots, call_opt, put_opt):
        """Bypassed for testing. Always returns True."""
        app_logger.info("Engine: Risk check bypassed for testing. Allowing trade.")
        return True

    def _record_skip(self, reason, status="Trade Skipped"):
        """Records a skip event to the history list (max 10 entries)."""
        from utils import get_ist_now
        entry = {
            "time": get_ist_now().strftime("%d %b %Y %I:%M %p IST"),
            "reason": reason,
            "status": status
        }
        self.skip_history.insert(0, entry)
        self.skip_history = self.skip_history[:10]  # Keep last 10 only

    def get_schedule_info(self):
        return {
            "today_status": self.today_trade_status,
            "today_reason": self.today_skip_reason,
            "skip_history": self.skip_history,
            "upcoming_schedule": self.filters.get_schedule(days=7)
        }

    def verify_and_reconnect_api(self):
        """
        PAPER MODE ONLY: Safety Check to verify API & WS connection.
        Attempts auto-reconnection up to 3 times if down.
        """
        app_logger.info("Engine [PAPER]: Verifying API connection before trade...")
        for attempt in range(1, 4):
            rest_ok = False
            try:
                res = self.api_client.get_tickers({'symbol': 'BTCUSD'})
                if res and res.get('success'):
                    rest_ok = True
            except Exception:
                pass
            
            ws_ok = self.api_client.ws_connected
            
            app_logger.info(f"Engine [PAPER]: API Status (REST: {'OK' if rest_ok else 'DOWN'}, WS: {'OK' if ws_ok else 'DOWN'}) - Attempt {attempt}/3")
            
            if rest_ok and ws_ok:
                return True
                
            app_logger.warning(f"Engine [PAPER]: Connection down. Attempting reconnect (Attempt {attempt})...")
            try:
                if not ws_ok:
                    if self.api_client.ws:
                        try:
                            self.api_client.ws.close()
                        except:
                            pass
                    self.api_client.start_ws()
            except Exception as ws_err:
                app_logger.error(f"Engine [PAPER]: Failed to restart WS: {ws_err}")
                
            try:
                self.api_client.sync_time()
            except Exception:
                pass
                
            time.sleep(2)
            
        return False

    def calculate_paper_slippage(self, is_sl=False, base_price=None):
        """
        PAPER MODE ONLY: Calculates random slippage per lot based on volatility/regime/SL rules.
        """
        slippage = random.uniform(0.5, 2.5)
        if base_price is not None and base_price > 0:
            slippage = min(slippage, base_price * 0.01)
        
        iv = 0.0
        try:
            iv, _ = self.filters._update_and_get_iv()
        except Exception:
            pass
            
        btc_moved_high = False
        pct_move = 0.0
        try:
            if len(self.btc_price_history) >= 2:
                current_price = self.btc_price_history[-1][1]
                five_mins_ago = time.time() - 300
                price_5m = None
                for t, p in self.btc_price_history:
                    if t >= five_mins_ago:
                        price_5m = p
                        break
                if price_5m is None:
                    price_5m = self.btc_price_history[0][1]
                
                pct_move = abs(current_price - price_5m) / price_5m * 100.0
                if pct_move > 1.5:
                    btc_moved_high = True
        except Exception as e:
            app_logger.error(f"Engine [PAPER]: Slippage BTC move check error: {e}")
            
        if iv > 0.80 or btc_moved_high:
            slippage *= 2.5
            app_logger.info(f"Engine [PAPER]: Dynamic slippage multiplier active! IV: {iv*100:.1f}%, BTC 5m Move: {pct_move:.2f}%. Slippage multiplied by 2.5x to {slippage:.2f}")
            
        if is_sl:
            extra = random.uniform(0.5, 1.5)
            slippage += extra
            app_logger.info(f"Engine [PAPER]: SL Slippage added: +{extra:.2f}. Total slippage per lot: {slippage:.2f}")
            
        return slippage
