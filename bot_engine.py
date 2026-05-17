import time
import schedule
import threading
import random
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
        self.hedging_triggered_today = False
        
        # PAPER mode enhancements
        self.paper_lot_multiplier = 1.0
        self.consecutive_losses = 0
        self.paper_trading_paused = False
        self.btc_price_history = []

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
        schedule.every().day.at("17:30").do(self.send_daily_report)
        
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
        
        # Verify and Auto-Reconnect API in PAPER mode
        if getattr(self.execution, 'mode', 'PAPER') == 'PAPER':
            api_ok = self.verify_and_reconnect_api()
            app_logger.info(f"Engine [PAPER]: API connection status before trade entry: {'Connected' if api_ok else 'Disconnected'}")
            if not api_ok:
                app_logger.error("Engine [PAPER]: API connection failed after 3 attempts. Skipping trade!")
                notifier.notify_error("🚨 API connection failed - Trade skipped")
                self.today_trade_status = "Trade Skipped"
                self.today_skip_reason = "API connection failed - Trade skipped"
                return
        
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
        
        # Apply PAPER dynamic lot size if in PAPER mode
        if getattr(self.execution, 'mode', 'PAPER') == 'PAPER':
            if self.paper_trading_paused:
                app_logger.warning("Engine [PAPER]: Trading is paused for today due to 3 consecutive losses. Skipping entry.")
                self.today_trade_status = "Trade Skipped"
                self.today_skip_reason = "Paper Trading Paused (3 consecutive losses)"
                return
            
            original_size = per_entry_size
            per_entry_size = int(per_entry_size * self.paper_lot_multiplier)
            app_logger.info(f"Engine [PAPER]: Dynamic lot sizing applied: {original_size} lots * {self.paper_lot_multiplier*100:.1f}% = {per_entry_size} lots")
        
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

            if not call_opt or not put_opt:
                app_logger.info("Engine [TEST]: Retrying without premium filter...")
                call_opt, put_opt = self.strategy.find_strikes(expiry_date=expiry, check_premium=False)

            if not call_opt or not put_opt:
                app_logger.info("Engine [TEST]: Retrying on any available expiry...")
                call_opt, put_opt = self.strategy.find_strikes(expiry_date=None, check_premium=False)

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
            entry_slippage = random.uniform(0.3, 1.2)   # small entry slippage
            simulated_call_entry = call_entry + entry_slippage
            simulated_put_entry  = put_entry  + entry_slippage
            entry_premium_total  = (simulated_call_entry + simulated_put_entry) * 1   # 1 lot

            app_logger.info(
                f"Engine [TEST]: PAPER Entry simulated. "
                f"Call entry: {simulated_call_entry:.4f}, Put entry: {simulated_put_entry:.4f} "
                f"(entry slippage: +{entry_slippage:.2f})"
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
                f"Total Entry Premium: ~{entry_premium_total:.2f} USDT\n"
                f"Waiting 10s then auto-cancelling..."
            )

            # ── Step 5: Wait 10 seconds (simulating position hold) ──
            app_logger.info("Engine [TEST]: Waiting 10 seconds before simulated exit...")
            time.sleep(10)

            # ── Step 6: Simulated Exit with slippage ──
            exit_slippage = self.calculate_paper_slippage(is_sl=False)
            simulated_call_exit = call_entry + exit_slippage
            simulated_put_exit  = put_entry  + exit_slippage
            exit_premium_total  = (simulated_call_exit + simulated_put_exit) * 1

            simulated_pnl = entry_premium_total - exit_premium_total
            pnl_inr       = simulated_pnl * 83.0   # USD → INR approx

            app_logger.info(
                f"Engine [TEST]: PAPER Exit simulated. "
                f"Exit slippage: {exit_slippage:.2f} pts. "
                f"Call exit: {simulated_call_exit:.4f}, Put exit: {simulated_put_exit:.4f}. "
                f"Simulated P&L: {simulated_pnl:+.4f} USDT (~₹{pnl_inr:+.2f})"
            )

            # ── Step 7: Final Telegram alert ──
            notifier.notify_error(
                f"✅ TEST ORDER COMPLETED (PAPER SIMULATION)\n"
                f"Call exit: {call_sym} @ ~{simulated_call_exit:.2f}\n"
                f"Put exit:  {put_sym} @ ~{simulated_put_exit:.2f}\n"
                f"Slippage applied: {exit_slippage:.2f} pts\n"
                f"Simulated P&L: {simulated_pnl:+.4f} USDT (~₹{pnl_inr:+.2f})\n"
                f"No real orders were placed."
            )

            return True, (
                f"Simulated successfully with slippage ({exit_slippage:.2f} pts). "
                f"Call: {call_sym}, Put: {put_sym}. "
                f"Simulated P&L: {simulated_pnl:+.4f} USDT (~₹{pnl_inr:+.2f})"
            )

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            app_logger.error(f"Engine [TEST]: Exception in run_test_order: {e}\n{tb}")
            return False, str(e)

    def run_rule_verification(self):
        text_report, results, pct = verify_all_rules()
        app_logger.info(text_report)
        self.latest_rule_report = {
            "results": results,
            "compliance": pct
        }

    def send_daily_report(self):
        """Automatically called at 17:30 IST to generate and send report."""
        success, msg = self.generate_actual_report()
        if success:
            metrics = self.performance_tracker.get_metrics(self.risk_manager.current_equity)
            overall = metrics.get('overall', {})
            notifier.notify_compliance_report(overall.get('win_rate', 0), overall.get('pnl', 0), overall.get('current_drawdown', 0))
        else:
            app_logger.error(f"Engine: Scheduled report failed: {msg}")

    def generate_actual_report(self, date_str=None):
        """Builds the report data, generates PDF/Excel, and saves metadata."""
        import report_generator
        from utils import get_ist_now
        
        if date_str is None:
            date_str = get_ist_now().strftime('%Y-%m-%d')
            
        app_logger.info(f"Engine: Generating Actual Report for {date_str}...")
        
        try:
            # 1. Collect trades for the date
            today_trades_raw = [t for t in self.performance_tracker.trades if t.get("date") == date_str]
            
            # Map to report generator format
            today_trades = []
            for t in today_trades_raw:
                today_trades.append({
                    "entry_time": t.get("entry_time", ""),
                    "exit_time": t.get("exit_time", ""),
                    "call_strike": t.get("call_symbol", "N/A"),
                    "put_strike": t.get("put_symbol", "N/A"),
                    "entry_premium": t.get("premium_collected", 0),
                    "exit_reason": t.get("exit_reason", ""),
                    "pnl_usd": t.get("pnl", 0)
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
            
            return True, f"Report for {date_str} generated successfully."
            
        except Exception as e:
            app_logger.error(f"Engine: Report generation error: {e}")
            return False, str(e)

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
                        
                        if self.trailing_sl_active and pnl_pct <= 0.0:
                            action = "TRAILING_SL_EXIT"
                        
                        if action in ["STOP_LOSS_ALL", "TAKE_PROFIT_ALL", "TRAILING_SL_EXIT"]:
                            # Apply slippage and execution delay in PAPER mode
                            if getattr(self.execution, 'mode', 'PAPER') == 'PAPER':
                                is_sl = (action == "STOP_LOSS_ALL")
                                slippage_per_lot = self.calculate_paper_slippage(is_sl)
                                total_size = sum([d['size'] for d in self.execution.active_positions.values()])
                                total_slippage = slippage_per_lot * total_size
                                adjusted_profit = profit - total_slippage
                                
                                # Execution delay of 200-500 milliseconds
                                delay = random.uniform(0.2, 0.5)
                                app_logger.info(f"Engine [PAPER]: Delaying trade exit by {delay*1000:.0f}ms...")
                                time.sleep(delay)
                                
                                # Log the decision
                                app_logger.info(f"Engine [PAPER] Slippage Log: timestamp={time.time()} | original_price={current_option_value:.4f} | price_after_slippage={current_option_value + total_slippage:.4f} | lot_size={total_size} | reason_for_change={action} | api_connected={'Connected' if self.api_client.ws_connected else 'Disconnected'}")
                                
                                profit = adjusted_profit
                        
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

                    # Hedging Check (Time-based triggers)
                    if should_check_hedge(self.last_hedge_check_time):
                        self.last_hedge_check_time = get_ist_now()
                        if abs(net_delta) > HEDGE_DELTA_THRESHOLD and abs(total_gamma) > HEDGE_GAMMA_THRESHOLD:
                            app_logger.info(f"Engine: Hedge limits exceeded. Net Delta: {net_delta:.4f}, Gamma: {total_gamma:.4f}")
                            self.execution.hedge_with_futures(net_delta)
                            self.hedging_triggered_today = True
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
                if getattr(self.execution, 'mode', 'PAPER') == 'PAPER':
                    size = int(size * self.paper_lot_multiplier)
                    app_logger.info(f"Engine [PAPER]: Re-entry lot sizing applied: {size} lots")
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
        self.hedging_triggered_today = False
        self.current_trade_info = {"calls": [], "puts": []}
        self.risk_manager.update_equity()
        self.daily_start_equity = self.risk_manager.current_equity
        self.today_trade_status = "Pending"
        self.today_skip_reason = None
        
        # Reset PAPER-specific state at EOD
        self.consecutive_losses = 0
        self.paper_trading_paused = False
        app_logger.info("Engine: Daily state reset.")

    def _log_and_reset_trade(self, profit, reason):
        if self.current_trade_info.get("calls"):
            c_syms = ",".join(self.current_trade_info["calls"])
            p_syms = ",".join(self.current_trade_info["puts"])
            
            # Update simulated equity and lot multiplier in PAPER mode
            if getattr(self.execution, 'mode', 'PAPER') == 'PAPER':
                self.risk_manager.current_equity += profit
                
                # Check if it is a winning trade or losing trade
                if profit > 0:
                    # Win: Increase by +5%, cap at 1.30 (130%)
                    self.paper_lot_multiplier = min(1.30, self.paper_lot_multiplier + 0.05)
                    self.consecutive_losses = 0
                    app_logger.info(f"Engine [PAPER]: Winning trade (+${profit:.2f}). New Lot Multiplier: {self.paper_lot_multiplier*100:.1f}%. Consecutive Losses reset to 0.")
                else:
                    # Loss
                    self.consecutive_losses += 1
                    if self.consecutive_losses == 1:
                        self.paper_lot_multiplier = max(0.10, self.paper_lot_multiplier - 0.10)
                        app_logger.info(f"Engine [PAPER]: Losing trade (-${abs(profit):.2f}). 1st loss. New Lot Multiplier: {self.paper_lot_multiplier*100:.1f}%.")
                    elif self.consecutive_losses == 2:
                        self.paper_lot_multiplier = max(0.10, self.paper_lot_multiplier - 0.20)
                        app_logger.info(f"Engine [PAPER]: Losing trade (-${abs(profit):.2f}). 2nd consecutive loss. New Lot Multiplier: {self.paper_lot_multiplier*100:.1f}%.")
                    elif self.consecutive_losses >= 3:
                        self.paper_trading_paused = True
                        app_logger.warning(f"Engine [PAPER]: 3 consecutive losses! Pausing paper trading for the rest of the day. Lot Multiplier remains: {self.paper_lot_multiplier*100:.1f}%.")
                        notifier.notify_error("⚠️ PAPER TRADING PAUSED ⚠️\n3 consecutive losses reached in PAPER mode. Trading paused for today.")

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

    def calculate_paper_slippage(self, is_sl=False):
        """
        PAPER MODE ONLY: Calculates random slippage per lot based on volatility/regime/SL rules.
        """
        slippage = random.uniform(0.5, 2.5)
        
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
