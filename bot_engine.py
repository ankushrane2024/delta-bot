import time
import schedule
import threading
from config import BOT_MODE, ENTRY_TIMES, EXIT_TIME_START, MAX_DAILY_LOSS_PCT, HEDGE_DELTA_THRESHOLD, HEDGE_GAMMA_THRESHOLD, STARTING_CAPITAL
from utils import get_ist_now, get_next_expiry_date, should_check_hedge
from logger import app_logger, error_logger
from notifier import notifier
from api_client import DeltaIndiaClient
from risk_manager import RiskManager
from strategy import ShortStrangleStrategy
from execution import ExecutionHandler
from filters import TradingFilters
from performance_tracker import PerformanceTracker
from rule_verifier import verify_all_rules

class DeltaTradingEngine:
    def __init__(self):
        self.api_client = DeltaIndiaClient()
        self.risk_manager = RiskManager(self.api_client)
        self.strategy = ShortStrangleStrategy(self.api_client)
        self.execution = ExecutionHandler(self.api_client, mode=BOT_MODE)
        self.filters = TradingFilters(self.api_client)
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
        self.today_trade_status = "Pending"
        self.today_skip_reason = None
        
        self.market_regime_filter_enabled = False
        self.current_market_regime = "Unknown"
        self.current_adx_value = 0.0

    def start(self):
        app_logger.info(f"Engine: Starting Delta BTC Options Bot in {BOT_MODE} mode with Capital: ${STARTING_CAPITAL}")
        notifier.notify_startup(BOT_MODE, STARTING_CAPITAL)
        
        # Connect WebSockets for zero-latency feeds
        self.api_client.start_ws()
        
        # Record starting equity for daily -3% loss check
        self.risk_manager.update_equity()
        self.daily_start_equity = self.risk_manager.current_equity
        
        # Schedule entry/exit
        for t in ENTRY_TIMES:
            schedule.every().day.at(t).do(self.run_entry_cycle)
        schedule.every().day.at(EXIT_TIME_START).do(self.run_exit_cycle)
        
        # Schedule rule verification
        schedule.every().day.at("09:30").do(self.run_rule_verification)
        schedule.every().day.at("18:00").do(self.run_rule_verification)
        schedule.every().day.at("18:00").do(self.send_daily_report)
        
        # Run rule verification once on startup
        self.run_rule_verification()
        
        # Monitor thread for real-time risk/hedge
        monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        monitor_thread.start()
        
        while self.is_running:
            schedule.run_pending()
            time.sleep(1)

    def run_entry_cycle(self):
        app_logger.info("Engine: Entry cycle triggered")
        
        # Daily Limits Check
        self.risk_manager.update_equity()
        if self.daily_loss_hits >= 2:
            app_logger.warning("Engine: Max daily loss limit hit (2 SLs). Skipping entry.")
            self.today_trade_status = "Trade Skipped"
            self.today_skip_reason = "Daily Loss Limit Hit (2 SLs)"
            return
            
        if self.daily_start_equity > 0:
            loss_pct = (self.daily_start_equity - self.risk_manager.current_equity) / self.daily_start_equity
            if loss_pct >= MAX_DAILY_LOSS_PCT:
                app_logger.warning("Engine: Daily -3% account loss limit hit. Stopping trading for the day.")
                self.today_trade_status = "Trade Skipped"
                self.today_skip_reason = "Daily Loss Limit Hit (-3%)"
                return

        passed, reason = self.filters.get_filter_status()
        if not passed:
            app_logger.info(f"Engine: Filters not passed: {reason}. Skipping entry.")
            self.today_trade_status = "Trade Skipped"
            self.today_skip_reason = reason
            return
            
        # Market Regime Filter Check
        regime, adx = self.filters.get_market_regime()
        self.current_market_regime = regime
        self.current_adx_value = adx
        
        if self.market_regime_filter_enabled:
            if regime == "Trending":
                app_logger.info(f"Engine: Market Regime Filter active. Skipping trade due to Trending market (ADX: {adx:.2f}).")
                self.today_trade_status = "Trade Skipped"
                self.today_skip_reason = f"Market Trending (ADX {adx:.2f} > 25)"
                return
        
        # Find Strikes (Next-day expiry, checks Premium & Delta)
        expiry = get_next_expiry_date()
        call_opt, put_opt = self.strategy.find_strikes(expiry_date=expiry)
        
        if not call_opt or not put_opt:
            app_logger.error("Engine: Could not find suitable strikes.")
            self.today_trade_status = "Trade Skipped"
            self.today_skip_reason = "No suitable strikes found"
            return

        # Calculate Lot Size
        per_entry_size = self.risk_manager.calculate_lot_size()
        
        # Safety check: skip trade if calculated lots < 1
        if per_entry_size < 1:
            app_logger.warning("Engine: Safety check failed. Calculated lot size < 1. Skipping entry.")
            self.today_trade_status = "Trade Skipped"
            self.today_skip_reason = "Insufficient capital for 1 lot"
            return
        
        # Execute
        self.execution.execute_strangle(call_opt, put_opt, per_entry_size)
        self.today_trade_status = "Trade Taken"
        self.today_skip_reason = None
        
        # Save trade details for tracking
        self.current_trade_info["entry_time"] = get_ist_now().isoformat()
        self.current_trade_info["calls"].append(call_opt['symbol'])
        self.current_trade_info["puts"].append(put_opt['symbol'])
        
        # Sub to WebSocket for these new symbols if not already
        self.api_client.subscribe_ws([call_opt['symbol'], put_opt['symbol']])
        
        # Notify
        total_premium_for_this_entry = (call_opt['mark_price'] + put_opt['mark_price']) * per_entry_size
        self.total_entry_premium += total_premium_for_this_entry
        notifier.notify_entry(call_opt['symbol'], put_opt['symbol'], per_entry_size, total_premium_for_this_entry)

    def run_exit_cycle(self):
        app_logger.info("Engine: Exit cycle triggered (Fixed Time Square-off)")
        
        # Calculate PnL for logging before closing
        if self.execution.active_positions and self.total_entry_premium > 0:
            current_total_value = 0
            for sym, data in self.execution.active_positions.items():
                ws_data = self.api_client.get_realtime_ticker(sym)
                if ws_data and 'mark_price' in ws_data:
                    current_total_value += float(ws_data['mark_price']) * data['size']
            
            if current_total_value > 0:
                profit = self.total_entry_premium - current_total_value
                self._log_and_reset_trade(profit, "EOD Square-off")
                notifier.notify_full_exit("End of Day Square-off", profit)
                
        self.execution.close_all(reason="End of Day Square-off")
        self.reset_daily_state()

    def run_test_order(self):
        """Places a real 1-lot order, waits 10s, then closes it. PAPER mode only."""
        app_logger.info("Engine: run_test_order start")
        if getattr(self.execution, 'mode', 'PAPER') == 'LIVE':
            app_logger.warning("Engine: Test order blocked (Mode is LIVE)")
            return False, "Test Order is only allowed in PAPER mode for safety."

        app_logger.info("Engine: Running Test Order (1 Lot)...")
        
        try:
            # 1. Find Strikes (Normal Strategy Logic)
            expiry = get_next_expiry_date()
            app_logger.info(f"Engine: Searching strikes for test order (Expiry: {expiry})...")
            
            # First attempt: Full strategy logic (Target Delta + Premium + Tomorrow's Expiry)
            call_opt, put_opt = self.strategy.find_strikes(expiry_date=expiry, check_premium=True)
            
            # Second attempt: Bypass Premium (helpful for weekends/low vol)
            if not call_opt or not put_opt:
                app_logger.info("Engine: No strikes found with premium filter. Retrying WITHOUT premium check...")
                call_opt, put_opt = self.strategy.find_strikes(expiry_date=expiry, check_premium=False)
                
            # Third attempt: Bypass Expiry (helpful if next-day expiry isn't available yet)
            if not call_opt or not put_opt:
                app_logger.info("Engine: No strikes found for tomorrow's expiry. Retrying on ANY available expiry...")
                call_opt, put_opt = self.strategy.find_strikes(expiry_date=None, check_premium=False)

            if not call_opt or not put_opt:
                return False, "Could not find ANY suitable strikes for test order even after bypassing filters."

            # 2. Place Real Orders (1 Lot)
            # We use api_client.place_order directly to bypass simulated paper execution
            res_call = self.api_client.place_order(call_opt['product_id'], 'sell', 1)
            res_put = self.api_client.place_order(put_opt['product_id'], 'sell', 1)
            
            if not res_call.get('success') or not res_put.get('success'):
                err_call = res_call.get('error', {}).get('message', 'Unknown Error') if not res_call.get('success') else 'Success'
                err_put = res_put.get('error', {}).get('message', 'Unknown Error') if not res_put.get('success') else 'Success'
                return False, f"Failed to place real test orders. Call: {err_call}, Put: {err_put}"
            
            app_logger.info(f"Engine: Test orders placed. Call: {call_opt['symbol']}, Put: {put_opt['symbol']}")
            notifier.notify_error(f"🧪 TEST ORDER PLACED (1 Lot)\nCall: {call_opt['symbol']}\nPut: {put_opt['symbol']}\nWaiting 10s to cancel...")
            
            # 3. Wait 10 seconds
            time.sleep(10)
            
            # 4. Close both legs at market
            res_close_call = self.api_client.place_order(call_opt['product_id'], 'buy', 1)
            res_close_put = self.api_client.place_order(put_opt['product_id'], 'buy', 1)
            
            app_logger.info("Engine: Test orders closed/cancelled.")
            notifier.notify_error("✅ TEST ORDER COMPLETED\nBoth legs squared off successfully after 10s.")
            
            return True, "Test Order Placed & Cancelled Successfully"
            
        except Exception as e:
            app_logger.error(f"Engine: Test order exception: {e}")
            return False, str(e)

    def run_rule_verification(self):
        text_report, results, pct = verify_all_rules()
        app_logger.info(text_report)
        self.latest_rule_report = {
            "results": results,
            "compliance": pct
        }

    def send_daily_report(self):
        metrics = self.performance_tracker.get_metrics(self.risk_manager.current_equity)
        overall = metrics.get('overall', {})
        notifier.notify_compliance_report(overall.get('win_rate', 0), overall.get('pnl', 0), overall.get('current_drawdown', 0))

    def monitor_loop(self):
        """Zero-latency real-time monitoring of PnL, SL/TP, and Hedging using WebSocket (with HTTP fallback)."""
        last_heartbeat = time.time()
        last_http_poll_time = 0
        
        while self.is_running:
            try:
                # 5 minute heartbeat log
                if time.time() - last_heartbeat >= 300:
                    app_logger.info("Engine Heartbeat: Monitor loop is active and running 24/7.")
                    last_heartbeat = time.time()
                    
                # 15s WS Disconnect Alert
                if not self.api_client.ws_connected and self.api_client.ws_last_disconnect_time:
                    if time.time() - self.api_client.ws_last_disconnect_time > 15:
                        if not self.api_client.ws_alert_sent:
                            app_logger.error("Monitor: WebSocket disconnected for > 15s. Sending alert.")
                            notifier.notify_error("⚠️ WebSocket Disconnected > 15s. Bot is operating in HTTP Fallback Mode.")
                            self.api_client.ws_alert_sent = True

                if self.execution.active_positions:
                    # 30-Second Critical Data Failure Safeguard
                    if time.time() - self.api_client.last_price_update_time > 30:
                        app_logger.critical("Engine: TOTAL DATA FAILURE > 30s. Triggering Emergency Auto Square-Off.")
                        notifier.notify_error("🚨 CRITICAL SAFEGUARD TRIGGERED 🚨\nTotal Data Failure (WS & HTTP) > 30s. Emergency Auto Square-Off executed to protect capital.")
                        self.execution.close_all(reason="Critical Data Failure (>30s)")
                        self.today_trade_status = "Emergency Auto Closed"
                        self.today_skip_reason = "Critical Data Failure (>30s)"
                        continue # Skip the rest of this loop iteration

                    # HTTP Polling Fallback Every 2 seconds
                    if time.time() - last_http_poll_time >= 2:
                        for sym in self.execution.active_positions.keys():
                            res = self.api_client.get_tickers({'symbol': sym})
                            if res and res.get('success'):
                                data = res.get('result')
                                self.api_client.update_ticker_from_http(sym, data)
                        last_http_poll_time = time.time()

                    current_total_value = 0
                    net_delta = 0
                    total_gamma = 0
                    all_prices_available = True
                    
                    for sym, data in self.execution.active_positions.items():
                        # Read directly from WebSocket memory cache
                        ws_data = self.api_client.get_realtime_ticker(sym)
                        if ws_data and 'mark_price' in ws_data:
                            current_total_value += float(ws_data['mark_price']) * data['size']
                            greeks = ws_data.get('greeks', {})
                            if greeks:
                                # Short positions -> invert delta/gamma
                                net_delta -= float(greeks.get('delta', 0)) * data['size']
                                total_gamma -= float(greeks.get('gamma', 0)) * data['size']
                        else:
                            all_prices_available = False
                            
                    if all_prices_available and self.total_entry_premium > 0:
                        # PnL Check
                        collected_premium = self.total_entry_premium
                        current_option_value = current_total_value
                        
                        # For short positions, profit = collected_premium - current_option_value
                        profit = collected_premium - current_option_value
                        pnl_pct = profit / collected_premium
                        
                        action = self.risk_manager.check_sl_tp(collected_premium, current_option_value, pnl_pct)
                        
                        if action == "STOP_LOSS_ALL":
                            app_logger.warning("Engine: Combined 150% Stop Loss Hit!")
                            self._log_and_reset_trade(profit, "Stop Loss Hit")
                            self.execution.close_all(reason="Stop Loss Hit")
                            self.daily_loss_hits += 1
                            recost_triggered = (self.re_entry_count < 1)
                            notifier.notify_stop_loss(profit, recost_triggered)
                            self.handle_recost()
                        
                        elif action == "TAKE_PROFIT_ALL":
                            app_logger.info("Engine: Profit Target Hit (70%)!")
                            self._log_and_reset_trade(profit, "Profit Target Hit")
                            self.execution.close_all(reason="Profit Target Hit")
                            notifier.notify_full_exit("Profit Target (70%)", profit)
                        
                        elif action == "PARTIAL_PROFIT" and not self.partial_profit_hit:
                            app_logger.info("Engine: Partial Profit Triggered (50%)")
                            self.execution.partial_close(percentage=0.5)
                            self.partial_profit_hit = True
                            notifier.notify_partial_profit(profit)

                        elif action == "TRAILING_SL_TRIGGERED" and not self.trailing_sl_active:
                            app_logger.info("Engine: Trailing SL to BE active")
                            self.trailing_sl_active = True
                            notifier.notify_trailing_sl()

                    # Hedging Check (Time-based triggers)
                    if should_check_hedge(self.last_hedge_check_time):
                        self.last_hedge_check_time = get_ist_now()
                        if abs(net_delta) > HEDGE_DELTA_THRESHOLD and abs(total_gamma) > HEDGE_GAMMA_THRESHOLD:
                            app_logger.info(f"Engine: Hedge limits exceeded. Net Delta: {net_delta:.4f}, Gamma: {total_gamma:.4f}")
                            self.execution.hedge_with_futures(net_delta)
                            notifier.notify_hedge(BOT_MODE, net_delta, total_gamma, "Rebalancing Futures")
                else:
                    time.sleep(1) # Sleep slightly longer if no positions
                    
                time.sleep(0.5) # High frequency tight loop
            except Exception as e:
                error_logger.error(f"Monitor: Error in monitor loop: {e}")
                notifier.notify_error(f"Bot stopped or error occurred: {e}")
                time.sleep(5)

    def handle_recost(self):
        """1-time re-entry after SL with wider strikes."""
        if self.re_entry_count < 1:
            app_logger.info("Engine: RECOST Re-entry triggered")
            self.re_entry_count += 1
            expiry = get_next_expiry_date()
            call_opt, put_opt = self.strategy.get_recost_strikes(expiry)
            if call_opt and put_opt:
                self.risk_manager.update_equity()
                size = self.risk_manager.calculate_lot_size()
                self.execution.execute_strangle(call_opt, put_opt, size)
                self.api_client.subscribe_ws([call_opt['symbol'], put_opt['symbol']])
                notifier.notify_recost()

    def reset_daily_state(self):
        self.re_entry_count = 0
        self.daily_loss_hits = 0
        self.total_entry_premium = 0
        self.partial_profit_hit = False
        self.trailing_sl_active = False
        self.last_hedge_check_time = None
        self.current_trade_info = {"calls": [], "puts": []}
        self.risk_manager.update_equity()
        self.daily_start_equity = self.risk_manager.current_equity
        self.today_trade_status = "Pending"
        self.today_skip_reason = None
        app_logger.info("Engine: Daily state reset.")

    def _log_and_reset_trade(self, profit, reason):
        if self.current_trade_info.get("calls"):
            c_syms = ",".join(self.current_trade_info["calls"])
            p_syms = ",".join(self.current_trade_info["puts"])
            self.performance_tracker.log_trade(
                entry_time=self.current_trade_info.get("entry_time", ""),
                call_symbol=c_syms,
                put_symbol=p_syms,
                premium_collected=self.total_entry_premium,
                pnl=profit,
                exit_reason=reason,
                current_equity=self.risk_manager.current_equity,
                regime_filter_enabled=self.market_regime_filter_enabled
            )
            self.current_trade_info = {"calls": [], "puts": []}

    def get_schedule_info(self):
        return {
            "today_status": self.today_trade_status,
            "today_reason": self.today_skip_reason,
            "upcoming_schedule": self.filters.get_schedule(days=7)
        }
