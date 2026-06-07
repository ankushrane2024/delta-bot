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
    HEDGE_SYMBOL,
    HEDGE_MAX_LOSS_PER_LOT
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
        self.hedge_stopped_out = False

    def get_status(self):
        """Returns the current hedging status dictionary for the web dashboard."""
        return {
            "hedge_active": self.hedge_active or (abs(self.execution.hedge_size_btc) > 0.0001),
            "hedge_type": self.hedge_type,
            "hedge_size_btc": round(self.execution.hedge_size_btc, 6),
            "hedge_percentage": round(self.hedge_percentage, 1),
            "hedge_order_id": self.hedge_order_id or self.execution.hedge_order_id or "None",
            "sl_tightened": self.sl_tightened,
            "last_check_time": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.last_check_time)) if self.last_check_time > 0 else "N/A",
            "hedge_pnl_usd": round(self.get_live_hedge_pnl(), 2)
        }

    def get_live_hedge_pnl(self):
        """Calculates the live PnL of the current hedge."""
        if not self.hedge_active or abs(self.execution.hedge_size_btc) < 0.0001:
            return 0.0
            
        res_ticker = self.api_client.get_tickers()
        mark_price = 0.0
        if res_ticker and res_ticker.get('success') and res_ticker.get('result'):
            for item in res_ticker['result']:
                if item.get('symbol') == HEDGE_SYMBOL:
                    mark_price = float(item.get('mark_price', 0))
                    break
                    
        if mark_price <= 0:
            return 0.0
            
        entry = self.execution.hedge_entry_price
        if entry <= 0:
            return 0.0
            
        size = abs(self.execution.hedge_size_btc)
        if self.execution.hedge_size_btc > 0: # Long hedge
            return (mark_price - entry) * size
        else: # Short hedge
            return (entry - mark_price) * size

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

        CRITICAL FIX: When WebSocket greeks are missing (e.g. right after a
        sudden price move), falls back to the last_known_delta stored in the
        position data. This prevents hedge from silently skipping due to 0.000
        delta during volatile moments.
        """
        net_delta_btc = 0.0
        total_gamma_btc = 0.0
        greeks_available = False
        
        for sym, data in positions.items():
            ws_data = self.api_client.get_realtime_ticker(sym)
            if ws_data:
                greeks = ws_data.get('greeks') or {}
                delta_raw = greeks.get('delta')
                gamma_raw = greeks.get('gamma')
                
                if delta_raw is not None:
                    d = float(delta_raw or 0)
                    g = float(gamma_raw or 0)
                    # Options are SHORT -> invert greeks
                    net_delta_btc -= d * data['size'] * 0.001
                    total_gamma_btc -= g * data['size'] * 0.001
                    # Cache last known good delta per leg
                    if abs(d) > 0.001:  # only cache non-zero values
                        data['last_known_delta'] = d
                        data['last_known_gamma'] = g
                    greeks_available = True
                else:
                    # No greeks in this tick — use last known delta if available
                    last_d = data.get('last_known_delta')
                    last_g = data.get('last_known_gamma', 0)
                    if last_d is not None:
                        app_logger.warning(
                            f"Hedge: No greeks in WS tick for {sym} — "
                            f"using last_known_delta={last_d:.4f} as fallback"
                        )
                        net_delta_btc -= last_d * data['size'] * 0.001
                        total_gamma_btc -= last_g * data['size'] * 0.001
                        greeks_available = True
            else:
                # No WS data at all — try last known delta
                last_d = data.get('last_known_delta')
                last_g = data.get('last_known_gamma', 0)
                if last_d is not None:
                    app_logger.warning(
                        f"Hedge: No WS data for {sym} — "
                        f"using last_known_delta={last_d:.4f} as fallback"
                    )
                    net_delta_btc -= last_d * data['size'] * 0.001
                    total_gamma_btc -= last_g * data['size'] * 0.001
                    greeks_available = True
                    
        if not greeks_available:
            app_logger.warning("Hedge: No delta/gamma data available from WS or cache for any leg.")
                
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

    def _execute_hedge_decision(self, net_delta_btc, dvol, positions, profit_usd=0.0):
        """
        Step 2 & 3: Check current BTC DVOL to decide if hedge should be activated.
        """
        abs_delta = abs(net_delta_btc)
        exposure_btc = self._get_options_exposure_btc(positions)
        
        leg_size = list(positions.values())[0]['size'] if positions else 1
        raw_net_delta = abs_delta / (leg_size * 0.001) if leg_size > 0 else 0.0
        
        if dvol < 45.0:
            trigger_level = HEDGE_IV_THRESHOLDS['low']['delta_trigger'] # 0.20
            tier = "Low (<45%)"
        elif dvol <= 55.0:
            trigger_level = HEDGE_IV_THRESHOLDS['mid']['delta_trigger'] # 0.17
            tier = "Mid (45-55%)"
        else:
            trigger_level = HEDGE_IV_THRESHOLDS['high']['delta_trigger'] # 0.12
            tier = "High (>55%)"

        app_logger.info(f"Hedge: DVOL Regime: {tier} | Trigger Level: {trigger_level:.2f} | Raw Net Delta: {raw_net_delta:.4f}")

        if raw_net_delta > trigger_level:
            app_logger.info(f"Hedge: Triggering 1-to-1 ONE-SHOT hedge since raw net delta {raw_net_delta:.4f} > {trigger_level:.2f}")
            self._execute_oneshot_hedge(net_delta_btc)
        else:
            app_logger.info(f"Hedge: No post-entry hedge needed. Raw Net Delta {raw_net_delta:.4f} <= {trigger_level:.2f}")

    def _execute_oneshot_hedge(self, net_delta_btc):
        """Executes the initial 1.0x Dynamic Delta Hedge."""
        target_hedge_size = abs(net_delta_btc) * 1.0 # STRICT 1.0x 1-to-1 Match
        
        direction = 'sell' if net_delta_btc > 0 else 'buy'
        
        app_logger.info(f"Hedge: Placing INITIAL 1-to-1 Dynamic Hedge of size {target_hedge_size:.4f} BTC in direction: {direction}")
        result = self.execution.place_hedge_order(target_hedge_size, direction)
        
        if result and result['success']:
            self.hedge_active = True
            self.hedge_type = "oneshot_1to1"
            self.hedge_size_btc = target_hedge_size if direction == 'buy' else -target_hedge_size
            self.hedge_percentage = 100.0
            self.hedge_order_id = result['order_id']
            self.last_check_time = time.time()
            
            notifier.notify_hedge_executed(
                timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
                iv=self.dvol.get_current_dvol(),
                net_delta=net_delta_btc,
                hedge_type="ONE-SHOT 1.0x",
                size_btc=target_hedge_size,
                order_id=result['order_id']
            )
        else:
            app_logger.error("Hedge: Initial dynamic hedge placement failed!")
            notifier.notify_hedge_failed()

    def manage_hedge(self, positions, unrealized_loss_pct, profit_usd=0.0):
        """
        Step 4: Continuous hedge management. Called from monitor_loop.
        Interval is dynamic: 10s after 3PM or when losing >10%, 30s otherwise.
        """
        self.last_check_time = time.time()
        if not positions:
            # Positions cleared -> unwind hedge if active
            if self.hedge_active:
                app_logger.info("Hedge: Option positions cleared. Closing futures hedge...")
                self.close_hedge()
            return
            
        if self.hedge_stopped_out:
            return
            
        # 3.9: Hedge Stop-Loss Check
        if self.hedge_active:
            hedge_pnl = self.get_live_hedge_pnl()
            
            # Calculate dynamic stop loss based on option exposure (lots)
            exposure_btc = self._get_options_exposure_btc(positions)
            total_lots = exposure_btc * 1000
            dynamic_max_loss = HEDGE_MAX_LOSS_PER_LOT * total_lots
            
            if hedge_pnl < -dynamic_max_loss:
                app_logger.warning(f"Hedge: STOP LOSS HIT! Hedge PnL is {hedge_pnl:.2f} (<-{dynamic_max_loss:.2f}). Closing hedge and disabling for this trade.")
                self.close_hedge()
                self.hedge_stopped_out = True
                notifier.notify_error(f"⚠️ Hedge Stop-Loss Hit!\nLoss: ${hedge_pnl:.2f}\nHedge is now disabled for the remainder of this trade.")
                return

        # 4.0: Loss-based emergency hedge trigger (CRITICAL FIX)
        # If position is losing > 30% of entry premium AND no hedge is active,
        # trigger a full emergency hedge IMMEDIATELY regardless of delta value.
        # This catches sudden BTC moves where greeks haven't updated yet.
        if not self.hedge_active and unrealized_loss_pct >= 0.30:
            app_logger.warning(
                f"Hedge: EMERGENCY loss-based trigger — unrealized_loss={unrealized_loss_pct:.1%} "
                f">= 30% and no hedge active. Triggering emergency full hedge NOW."
            )
            net_delta_btc, _ = self._fetch_net_delta_and_gamma(positions)
            exposure_btc = self._get_options_exposure_btc(positions)
            # Strict 1-to-1 Emergency Hedge
            hedge_size = abs(net_delta_btc) if abs(net_delta_btc) > 0.0001 else 0.0
            direction = 'sell' if net_delta_btc >= 0 else 'buy'
            
            if hedge_size > 0:
                app_logger.info(
                    f"Hedge [EMERGENCY]: 1-to-1 DYNAMIC Hedging {hedge_size:.4f} BTC in direction {direction} "
                    f"(net_delta={net_delta_btc:.4f})"
                )
                result = self.execution.place_hedge_order(hedge_size, direction)
                if result and result['success']:
                    self.hedge_active = True
                    self.hedge_type = "oneshot_1to1"
                    self.hedge_size_btc = hedge_size if direction == 'buy' else -hedge_size
                    self.hedge_percentage = 100.0
                    self.hedge_order_id = result['order_id']
                    if not self.sl_tightened:
                        from config import HEDGE_EMERGENCY_SL_TIGHTEN
                        self.risk_manager.tighten_stop_loss(HEDGE_EMERGENCY_SL_TIGHTEN)
                        self.sl_tightened = True
                    notifier.notify_hedge_escalated(
                        timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
                        from_pct=0.0,
                        to_pct=100.0,
                        loss_pct=unrealized_loss_pct * 100
                    )
                else:
                    app_logger.error("Hedge [EMERGENCY]: Emergency loss-trigger hedge failed!")
                    notifier.notify_hedge_failed()
            return  # Don't continue to regular checks after emergency hedge

        # 4.1: Unrealized Loss > 25% check (Tighten SL)
        if unrealized_loss_pct >= HEDGE_EMERGENCY_LOSS_PCT:
            # Tighten option SL via Risk Manager
            if not self.sl_tightened:
                app_logger.warning(f"Hedge: Critical unrealized loss detected ({unrealized_loss_pct:.1%}). Tightening SL.")
                self.risk_manager.tighten_stop_loss(HEDGE_EMERGENCY_SL_TIGHTEN)
                self.sl_tightened = True

        # 4.2: Regular continuous delta rebalancing
        net_delta_btc, total_gamma_btc = self._fetch_net_delta_and_gamma(positions)
        abs_delta = abs(net_delta_btc)
        current_dvol = self.dvol.get_current_dvol()
        
        # Convert absolute net delta in BTC terms back to raw option contract delta terms for comparison
        leg_size = list(positions.values())[0]['size'] if positions else 1
        raw_net_delta = abs_delta / (leg_size * 0.001) if leg_size > 0 else 0.0
        
        if not self.hedge_active:
            # No hedge active — check standard delta triggers
            app_logger.info(
                f"Hedge: Standard delta check — raw_net_delta={raw_net_delta:.4f} | "
                f"dvol={current_dvol:.1f}% | hedge_active={self.hedge_active} | loss={unrealized_loss_pct:.1%}"
            )
            self._execute_hedge_decision(net_delta_btc, current_dvol, positions, profit_usd)
        else:
            # Hedge is active. We must dynamically rebalance to remain delta-neutral.
            target_hedge = -net_delta_btc
            current_hedge = self.execution.hedge_size_btc
            hedge_diff = target_hedge - current_hedge
            
            # UNWIND CHECK: If delta drops back to neutral, the market mean-reverted. We MUST close the hedge.
            if raw_net_delta < 0.05:
                app_logger.info(f"Hedge: Option delta has neutralized (raw={raw_net_delta:.4f} < 0.05). Unwinding hedge to capture reversion profit and restore naked strangle.")
                self.close_hedge()
                return

            # REBALANCE CHECK: If the required hedge drifts from our current hedge by > 0.02 BTC, adjust it.
            if abs(hedge_diff) >= 0.02:
                direction = 'buy' if hedge_diff > 0 else 'sell'
                app_logger.info(f"Hedge [REBALANCE]: Portfolio delta drifted. Adjusting hedge by {abs(hedge_diff):.4f} BTC ({direction}) to restore 1-to-1 neutrality.")
                
                result = self.execution.place_hedge_order(abs(hedge_diff), direction)
                if result and result['success']:
                    self.hedge_size_btc = target_hedge
                    self.hedge_type = "dynamic_rebalance"
                    # Notify update
                    notifier.notify_hedge_executed(
                        timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
                        iv=current_dvol,
                        net_delta=net_delta_btc,
                        hedge_type="REBALANCE 1.0x",
                        size_btc=abs(hedge_diff),
                        order_id=result['order_id']
                    )

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

