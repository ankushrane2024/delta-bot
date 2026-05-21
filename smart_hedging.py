import time
import threading
import math
from config import (
    HEDGE_WAIT_AFTER_ENTRY,
    HEDGE_RECHECK_INTERVAL,
    HEDGE_IV_THRESHOLDS,
    HEDGE_PARTIAL_INITIAL_PCT,
    HEDGE_PARTIAL_ESCALATE_PCT,
    HEDGE_PARTIAL_WAIT,
    HEDGE_EMERGENCY_LOSS_PCT,
    HEDGE_EMERGENCY_SL_TIGHTEN,
    HEDGE_SYMBOL
)
from logger import app_logger
from notifier import notifier

class SmartHedgingManager:
    """
    Implements the complete Smart Partial Hedging Pipeline (Sections 3.1-3.5)
    for the Delta BTC Options Bot.
    """
    def __init__(self, execution_handler, dvol_provider, risk_manager, api_client):
        self.execution = execution_handler
        self.dvol = dvol_provider
        self.risk_manager = risk_manager
        self.api_client = api_client
        
        # State variables
        self.hedge_active = False
        self.hedge_type = "None"      # "None", "full", "partial"
        self.hedge_percentage = 0.0   # Current hedge scaling (0 - 100%)
        self.hedge_size_btc = 0.0     # Current hedge size in BTC
        self.hedge_order_id = "None"
        self.last_check_time = 0.0
        self.sl_tightened = False

    def get_status(self):
        """Returns the current hedging status dictionary for the web dashboard."""
        return {
            "hedge_active": self.hedge_active or (abs(self.execution.hedge_size_btc) > 0.0001),
            "hedge_type": self.hedge_type,
            "hedge_size_btc": round(self.execution.hedge_size_btc, 6),
            "hedge_percentage": round(self.hedge_percentage, 1),
            "hedge_order_id": self.hedge_order_id or self.execution.hedge_order_id or "None",
            "sl_tightened": self.sl_tightened,
            "last_check_time": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.last_check_time)) if self.last_check_time > 0 else "N/A"
        }

    def _get_options_exposure_btc(self, positions):
        """Calculates total option contract size in BTC terms."""
        # 1 contract of options on Delta Exchange = 0.001 BTC.
        total_size = sum(data.get('size', 0) for data in positions.values())
        return total_size * 0.001

    def _fetch_net_delta_and_gamma(self, positions):
        """
        Calculates absolute net delta and total gamma of options positions in BTC.
        Option delta is unscaled in API (from -1 to +1).
        So BTC Delta exposure = Option Delta * Size * 0.001.
        """
        net_delta_btc = 0.0
        total_gamma_btc = 0.0
        
        for sym, data in positions.items():
            ws_data = self.api_client.get_realtime_ticker(sym)
            if ws_data and 'greeks' in ws_data:
                greeks = ws_data.get('greeks') or {}
                # Options are SHORT in a Short Strangle Strategy -> we are SHORT the greeks
                net_delta_btc -= float(greeks.get('delta', 0) or 0) * data['size'] * 0.001
                total_gamma_btc -= float(greeks.get('gamma', 0) or 0) * data['size'] * 0.001
                
        return net_delta_btc, total_gamma_btc

    def run_post_entry_hedge(self, positions):
        """
        Step 1: Post-entry hedging check.
        Waits 5 seconds after entry, then runs first check.
        """
        app_logger.info(f"Hedge: Scheduling post-entry hedge check in {HEDGE_WAIT_AFTER_ENTRY}s...")
        time.sleep(HEDGE_WAIT_AFTER_ENTRY)
        
        if not positions:
            app_logger.info("Hedge: Post-entry check cancelled - no active positions.")
            return

        current_dvol = self.dvol.get_current_dvol()
        net_delta_btc, total_gamma_btc = self._fetch_net_delta_and_gamma(positions)
        app_logger.info(f"Hedge: Post-entry metrics check - DVOL: {current_dvol:.2f}%, Net Delta BTC: {net_delta_btc:.4f}")
        
        self._execute_hedge_decision(net_delta_btc, current_dvol, positions)

    def _execute_hedge_decision(self, net_delta_btc, dvol, positions):
        """
        Step 2 & 3: Check current BTC DVOL to decide hedge size and execute it.
        """
        abs_delta = abs(net_delta_btc)
        exposure_btc = self._get_options_exposure_btc(positions)
        
        # Decide threshold and action based on DVOL
        if dvol < 45.0:
            trigger_level = HEDGE_IV_THRESHOLDS['low']['delta_trigger'] # 0.20
            action = HEDGE_IV_THRESHOLDS['low']['action'] # full
            tier = "Low (<45%)"
        elif dvol <= 55.0:
            trigger_level = HEDGE_IV_THRESHOLDS['mid']['delta_trigger'] # 0.17
            action = HEDGE_IV_THRESHOLDS['mid']['action'] # full
            tier = "Mid (45-55%)"
        else:
            trigger_level = HEDGE_IV_THRESHOLDS['high']['delta_trigger'] # 0.12
            action = HEDGE_IV_THRESHOLDS['high']['action'] # partial
            tier = "High (>55%)"

        app_logger.info(f"Hedge: DVOL Regime: {tier} | Trigger Level: {trigger_level:.2f} | Action: {action}")

        if abs_delta > trigger_level:
            if action == 'full':
                app_logger.info(f"Hedge: Triggering FULL hedge since net delta {abs_delta:.4f} > {trigger_level:.2f}")
                self._execute_full_hedge(net_delta_btc, exposure_btc)
            elif action == 'partial':
                app_logger.info(f"Hedge: Triggering PARTIAL hedge since net delta {abs_delta:.4f} > {trigger_level:.2f}")
                self._execute_partial_hedge_sequence(net_delta_btc, exposure_btc, positions)
        else:
            app_logger.info(f"Hedge: No post-entry hedge needed. Delta {abs_delta:.4f} <= {trigger_level:.2f}")

    def _execute_full_hedge(self, net_delta_btc, exposure_btc):
        """Executes a 100% hedge of option delta exposure."""
        # Hedge size matches option delta exposure in BTC
        required_hedge_btc = abs(net_delta_btc)
        direction = 'buy' if net_delta_btc > 0 else 'sell' # If delta is positive (long options delta), we need to SHORT futures?
        # Wait, if net delta is positive (e.g. Call side is tested, we are long delta), we need to SHORT futures to neutralize.
        # Let's check execution.py:
        # "If target_delta is positive, we are long delta -> Need to SHORT futures.
        #  If target_delta is negative, we are short delta -> Need to LONG futures."
        # Correct! direction = 'sell' if net_delta_btc > 0 else 'buy'.
        direction = 'sell' if net_delta_btc > 0 else 'buy'
        
        app_logger.info(f"Hedge: Placing FULL hedge order of size {required_hedge_btc:.4f} BTC in direction: {direction}")
        result = self.execution.place_hedge_order(required_hedge_btc, direction)
        
        if result and result['success']:
            self.hedge_active = True
            self.hedge_type = "full"
            self.hedge_size_btc = required_hedge_btc
            self.hedge_percentage = 100.0
            self.hedge_order_id = result['order_id']
            self.last_check_time = time.time()
            
            # Send telegram notification
            notifier.notify_hedge_executed(
                timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
                iv=self.dvol.get_current_dvol(),
                net_delta=net_delta_btc,
                hedge_type="FULL",
                size_btc=required_hedge_btc,
                order_id=result['order_id']
            )
        else:
            app_logger.error("Hedge: FULL hedge placement failed!")
            notifier.notify_hedge_failed()

    def _execute_partial_hedge_sequence(self, net_delta_btc, exposure_btc, positions):
        """
        Executes a partial hedge sequence:
        Starts at 50%, waits 10s, rechecks, and escalates to 80-100% if delta > 0.10.
        """
        # Step 1: Initial 50% partial hedge
        initial_hedge_btc = abs(net_delta_btc) * HEDGE_PARTIAL_INITIAL_PCT # 50% of delta
        direction = 'sell' if net_delta_btc > 0 else 'buy'
        
        app_logger.info(f"Hedge: Placing PARTIAL hedge (50%) of size {initial_hedge_btc:.4f} BTC in direction: {direction}")
        result = self.execution.place_hedge_order(initial_hedge_btc, direction)
        
        if result and result['success']:
            self.hedge_active = True
            self.hedge_type = "partial"
            self.hedge_size_btc = initial_hedge_btc
            self.hedge_percentage = 50.0
            self.hedge_order_id = result['order_id']
            self.last_check_time = time.time()
            
            notifier.notify_hedge_executed(
                timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
                iv=self.dvol.get_current_dvol(),
                net_delta=net_delta_btc,
                hedge_type="PARTIAL (50%)",
                size_btc=initial_hedge_btc,
                order_id=result['order_id']
            )
        else:
            app_logger.error("Hedge: Initial PARTIAL hedge placement failed!")
            notifier.notify_hedge_failed()
            return

        # Start a background thread to wait and recheck for escalation
        def recheck_escalation():
            time.sleep(HEDGE_PARTIAL_WAIT) # Wait 10 seconds
            if not positions:
                return
                
            new_delta, _ = self._fetch_net_delta_and_gamma(positions)
            app_logger.info(f"Hedge: Rechecking partial hedge after 10s. New Delta BTC: {new_delta:.4f}")
            
            if abs(new_delta) > 0.10:
                # Escalate to 80% (Section 3.3)
                escalation_hedge_btc = abs(new_delta) * HEDGE_PARTIAL_ESCALATE_PCT
                esc_direction = 'sell' if new_delta > 0 else 'buy'
                
                app_logger.info(f"Hedge: ESCALATING partial hedge to 80% of current exposure ({escalation_hedge_btc:.4f} BTC)")
                esc_result = self.execution.place_hedge_order(escalation_hedge_btc, esc_direction)
                
                if esc_result and esc_result['success']:
                    self.hedge_percentage = 80.0
                    self.hedge_type = "partial (escalated)"
                    self.hedge_size_btc += escalation_hedge_btc
                    self.hedge_order_id = esc_result['order_id']
                    
                    notifier.notify_hedge_executed(
                        timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
                        iv=self.dvol.get_current_dvol(),
                        net_delta=new_delta,
                        hedge_type="ESCALATION (80%)",
                        size_btc=escalation_hedge_btc,
                        order_id=esc_result['order_id']
                    )
                else:
                    app_logger.error("Hedge: Escalation order failed!")
                    notifier.notify_hedge_failed()
            else:
                app_logger.info(f"Hedge: No escalation needed. Delta {abs(new_delta):.4f} <= 0.10")

        threading.Thread(target=recheck_escalation, daemon=True).start()

    def manage_hedge(self, positions, unrealized_loss_pct):
        """
        Step 4: Continuous hedge management. Called every 30 seconds from monitor_loop.
        """
        self.last_check_time = time.time()
        if not positions:
            # Positions cleared -> unwind hedge if active
            if self.hedge_active:
                app_logger.info("Hedge: Option positions cleared. Closing futures hedge...")
                self.close_hedge()
            return

        # 4.1: Unrealized Loss > 60% check (Emergency Escalation & SL tightening)
        if unrealized_loss_pct >= HEDGE_EMERGENCY_LOSS_PCT and self.hedge_percentage < 100.0:
            app_logger.warning(f"Hedge: Critical unrealized loss detected ({unrealized_loss_pct:.1%}). Escalating to FULL hedge immediately.")
            
            # Tighten option SL via Risk Manager
            if not self.sl_tightened:
                self.risk_manager.tighten_stop_loss(HEDGE_EMERGENCY_SL_TIGHTEN)
                self.sl_tightened = True
                
            # Escalate hedge
            net_delta_btc, _ = self._fetch_net_delta_and_gamma(positions)
            exposure_btc = self._get_options_exposure_btc(positions)
            direction = 'sell' if net_delta_btc > 0 else 'buy'
            
            # Calculate remaining hedge size to reach 100% full hedge
            remaining_hedge = abs(net_delta_btc) - abs(self.execution.hedge_size_btc)
            if remaining_hedge > 0.0001:
                app_logger.info(f"Hedge: Placing emergency escalation order of size {remaining_hedge:.4f} BTC")
                result = self.execution.place_hedge_order(remaining_hedge, direction)
                if result and result['success']:
                    self.hedge_active = True
                    self.hedge_type = "emergency_full"
                    self.hedge_percentage = 100.0
                    self.hedge_size_btc = abs(net_delta_btc)
                    self.hedge_order_id = result['order_id']
                    
                    notifier.notify_hedge_escalated(
                        timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
                        from_pct=50.0,
                        to_pct=100.0,
                        loss_pct=unrealized_loss_pct * 100
                    )
                else:
                    app_logger.error("Hedge: Emergency escalation failed!")
                    notifier.notify_hedge_failed()

        # 4.2: Regular continuous delta rebalancing
        net_delta_btc, total_gamma_btc = self._fetch_net_delta_and_gamma(positions)
        abs_delta = abs(net_delta_btc)
        current_dvol = self.dvol.get_current_dvol()
        
        # Hysteresis check: If delta is neutral (< 0.05) and hedge is active, keep active hedge intact (no whipsawing)
        if self.hedge_active and abs_delta < 0.05:
            app_logger.info(f"Hedge: Option delta is neutral ({abs_delta:.4f} < 0.05). Keeping existing hedge intact to avoid whipsawing.")
            return
            
        # Re-balancing check: If delta exceeds 0.15 in opposite direction while hedge is active, adjust it.
        # Or if no hedge is active, but net delta exceeds threshold, trigger entry hedge.
        if self.hedge_active:
            # Check if active hedge matches the current delta direction.
            # If current delta is positive, we need a SHORT hedge (negative size).
            # If current delta is negative, we need a LONG hedge (positive size).
            expected_hedge_sign = -1.0 if net_delta_btc > 0 else 1.0
            actual_hedge_sign = 1.0 if self.execution.hedge_size_btc > 0 else -1.0
            
            if expected_hedge_sign != actual_hedge_sign and abs_delta > 0.15:
                app_logger.info(f"Hedge: Delta reversed ({net_delta_btc:.4f}) while hedge active. Re-adjusting hedge position.")
                self.close_hedge()
                self._execute_hedge_decision(net_delta_btc, current_dvol, positions)
        else:
            # No hedge active, check standard triggers
            self._execute_hedge_decision(net_delta_btc, current_dvol, positions)

    def close_hedge(self):
        """Step 4: Close all active hedges and reset states."""
        app_logger.info("Hedge: Closing all smart hedge positions...")
        self.execution.close_hedge()
        
        # Reset state
        self.hedge_active = False
        self.hedge_type = "None"
        self.hedge_percentage = 0.0
        self.hedge_size_btc = 0.0
        self.hedge_order_id = "None"
        self.sl_tightened = False
        app_logger.info("Hedge: Smart hedge state reset successfully.")

    def get_status(self):
        """Returns the current hedging status dictionary for the web dashboard."""
        return {
            "hedge_active": self.hedge_active,
            "hedge_type": self.hedge_type,
            "hedge_percentage": round(self.hedge_percentage, 1),
            "hedge_size_btc": round(self.hedge_size_btc, 6),
            "hedge_order_id": self.hedge_order_id,
            "sl_tightened": self.sl_tightened
        }

