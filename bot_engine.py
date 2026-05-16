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
            return
            
        if self.daily_start_equity > 0:
            loss_pct = (self.daily_start_equity - self.risk_manager.current_equity) / self.daily_start_equity
            if loss_pct >= MAX_DAILY_LOSS_PCT:
                app_logger.warning("Engine: Daily -3% account loss limit hit. Stopping trading for the day.")
                return

        if not self.filters.all_passed():
            app_logger.info("Engine: Filters not passed. Skipping entry.")
            return
        
        # Find Strikes (Next-day expiry, checks Premium & Delta)
        expiry = get_next_expiry_date()
        call_opt, put_opt = self.strategy.find_strikes(expiry_date=expiry)
        
        if not call_opt or not put_opt:
            app_logger.error("Engine: Could not find suitable strikes.")
            return

        # Calculate Lot Size
        per_entry_size = self.risk_manager.calculate_lot_size()
        
        # Safety check: skip trade if calculated lots < 1
        if per_entry_size < 1:
            app_logger.warning("Engine: Safety check failed. Calculated lot size < 1. Skipping entry.")
            return
        
        # Execute
        self.execution.execute_strangle(call_opt, put_opt, per_entry_size)
        
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
        """Zero-latency real-time monitoring of PnL, SL/TP, and Hedging using WebSocket."""
        last_heartbeat = time.time()
        while self.is_running:
            try:
                # 5 minute heartbeat log
                if time.time() - last_heartbeat >= 300:
                    app_logger.info("Engine Heartbeat: Monitor loop is active and running 24/7.")
                    last_heartbeat = time.time()

                if self.execution.active_positions:
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
                current_equity=self.risk_manager.current_equity
            )
            self.current_trade_info = {"calls": [], "puts": []}
