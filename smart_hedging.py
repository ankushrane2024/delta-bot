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


# ─────────────────────────────────────────────────────────────────
# NEW V2 CONSTANTS (Premium-Based Smart Hedging)
# ─────────────────────────────────────────────────────────────────
HEDGE_BLEED_TRIGGER_PCT = 0.12        # Hedge fires when any leg bleeds 12%+
HEDGE_ESCALATE_BLEED_PCT = 0.25       # Escalate to full size at 25%+ bleed
HEDGE_INITIAL_SIZE_FACTOR = 0.50      # Start hedge at 50% of calculated size
HEDGE_FULL_SIZE_FACTOR = 1.00         # Full hedge size
HEDGE_BREAKEVEN_BUFFER = 0.30         # Close hedge if P&L drops below $0.30 after being profitable
HEDGE_MIN_PROFIT_TO_TRAIL = 0.50      # Start trailing breakeven after $0.50 profit
HEDGE_REVERSAL_THRESHOLD = 0.10       # Other leg must bleed 10%+ to trigger reversal
HEDGE_MAX_LOSS_ABSOLUTE = -1.00       # Hard stop: close hedge if it loses more than $1.00


class SmartHedgingManager:
    """
    Advanced Smart Hedging Engine v2 — Premium-Based Detection
    ===========================================================
    
    Core Philosophy:
    ----------------
    NEVER trust API greeks (they return 0 in paper mode).
    Instead, watch which option leg's premium is RISING (= we are losing money 
    as sellers). The rising leg tells us the market direction.
    
    Key Features:
    1. Premium-based bleeding detection (works even when greeks=0)
    2. Loss-proportional hedge sizing (bigger loss = bigger hedge)
    3. Trailing breakeven stop (hedge can never bleed)
    4. Reversal detection (closes and re-hedges in opposite direction)
    5. Graduated entry (50% → 100% escalation)
    """

    def __init__(self, execution_handler, dvol_provider, risk_manager, api_client):
        self.execution = execution_handler
        self.dvol = dvol_provider
        self.risk_manager = risk_manager
        self.api_client = api_client

        # --- State Variables ---
        self.hedge_active = False
        self.hedge_type = "None"
        self.hedge_percentage = 0.0
        self.hedge_size_btc = 0.0       # Signed: negative = short, positive = long
        self.hedge_order_id = "None"
        self.last_check_time = 0.0
        self.hedge_placed_time = 0.0
        self.sl_tightened = False
        self.hedge_stopped_out = False

        # --- Precise PnL tracking ---
        self.hedge_avg_entry_price = 0.0
        self.hedge_total_cost_btc = 0.0

        # --- Premium tracking ---
        self._entry_premiums = {}          # {symbol: entry_price_per_lot}
        self._bleeding_leg = None          # 'call' or 'put'
        self._hedge_peak_pnl = 0.0        # Track peak P&L for trailing stop
        self._hedge_size_factor = 0.0     # Current size factor (0.5 or 1.0)
        self._hedge_direction = None       # 'buy' or 'sell'

    # ─────────────────────────────────────────────────────────────────
    # PUBLIC STATUS
    # ─────────────────────────────────────────────────────────────────

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
            "hedge_pnl_usd": round(self.get_live_hedge_pnl(), 2),
            "bleeding_leg": self._bleeding_leg or "None",
            "hedge_peak_pnl": round(self._hedge_peak_pnl, 2)
        }

    # ─────────────────────────────────────────────────────────────────
    # PNL CALCULATION
    # ─────────────────────────────────────────────────────────────────

    def get_live_hedge_pnl(self):
        """
        Calculates the live PnL of the current hedge position using
        the WEIGHTED AVERAGE ENTRY PRICE across all fills.
        """
        if not self.hedge_active or abs(self.execution.hedge_size_btc) < 0.0001:
            return 0.0
        if self.hedge_avg_entry_price <= 0:
            return 0.0

        mark_price = self._get_btc_mark_price()
        if mark_price <= 0:
            return 0.0

        size = self.execution.hedge_size_btc  # Signed
        avg_entry = self.hedge_avg_entry_price

        # Short hedge (size < 0): profit when price drops
        # Long hedge (size > 0): profit when price rises
        if size < 0:
            pnl = (avg_entry - mark_price) * abs(size)
        else:
            pnl = (mark_price - avg_entry) * size
        return pnl

    def _get_btc_mark_price(self):
        """Fetch current BTC perpetual mark price."""
        try:
            res_ticker = self.api_client.get_tickers({'symbol': HEDGE_SYMBOL})
            if res_ticker and res_ticker.get('success') and res_ticker.get('result'):
                for item in res_ticker['result']:
                    if item.get('symbol') == HEDGE_SYMBOL:
                        return float(item.get('mark_price', 0))
        except Exception as e:
            app_logger.warning(f"Hedge: Could not fetch BTC mark price: {e}")
        return 0.0

    # ─────────────────────────────────────────────────────────────────
    # ENTRY PREMIUM CACHE
    # ─────────────────────────────────────────────────────────────────

    def set_entry_premiums(self, positions):
        """
        Call this immediately after a strangle is entered.
        Caches entry premiums per leg so we can detect bleeding.
        """
        self._entry_premiums = {}
        for sym, data in positions.items():
            self._entry_premiums[sym] = data.get('entry_price', 0)
        app_logger.info(f"Hedge: Cached entry premiums: {self._entry_premiums}")

    # ─────────────────────────────────────────────────────────────────
    # PREMIUM-BASED BLEEDING DETECTION (Core v2 Innovation)
    # ─────────────────────────────────────────────────────────────────

    def _detect_bleeding_leg(self, positions):
        """
        Detects which leg is bleeding by comparing current premium to entry.
        
        Returns:
            (bleeding_leg, bleed_pct, bleed_usd, direction)
            - bleeding_leg: 'call' or 'put' or None
            - bleed_pct: how much the premium rose as a percentage (0.15 = 15%)
            - bleed_usd: total USD loss from this leg
            - direction: 'buy' (call bleeding, BTC up) or 'sell' (put bleeding, BTC down)
        """
        if not self._entry_premiums:
            return None, 0.0, 0.0, None

        call_bleed_pct = 0.0
        put_bleed_pct = 0.0
        call_bleed_usd = 0.0
        put_bleed_usd = 0.0

        for sym, data in positions.items():
            entry_premium = self._entry_premiums.get(sym, 0)
            if entry_premium <= 0:
                continue

            # Get current premium
            ws_data = self.api_client.get_realtime_ticker(sym)
            if not ws_data or 'mark_price' not in ws_data:
                continue

            current_premium = float(ws_data['mark_price'])
            
            # Premium RISING = we are losing (we sold the option)
            premium_change = current_premium - entry_premium
            bleed_pct = premium_change / entry_premium if entry_premium > 0 else 0.0
            
            # Calculate USD loss from this leg
            lot_size = data.get('size', 1)
            bleed_usd = premium_change * lot_size * 0.001  # Each lot = 0.001 BTC notional

            is_call = sym.startswith('C-') or data.get('leg_type', '') == 'call' or data.get('option_type', '') == 'call'
            
            if is_call and bleed_pct > 0:
                call_bleed_pct = bleed_pct
                call_bleed_usd = bleed_usd
            elif not is_call and bleed_pct > 0:
                put_bleed_pct = bleed_pct
                put_bleed_usd = bleed_usd

        # Determine which leg is bleeding more
        if call_bleed_pct > put_bleed_pct and call_bleed_pct > 0:
            app_logger.info(
                f"Hedge: CALL bleeding {call_bleed_pct*100:.1f}% (${call_bleed_usd:.2f} loss) | "
                f"Put bleed: {put_bleed_pct*100:.1f}%"
            )
            return 'call', call_bleed_pct, call_bleed_usd, 'buy'  # BTC went UP → BUY futures
        elif put_bleed_pct > 0:
            app_logger.info(
                f"Hedge: PUT bleeding {put_bleed_pct*100:.1f}% (${put_bleed_usd:.2f} loss) | "
                f"Call bleed: {call_bleed_pct*100:.1f}%"
            )
            return 'put', put_bleed_pct, put_bleed_usd, 'sell'  # BTC went DOWN → SELL futures
        else:
            return None, 0.0, 0.0, None

    # ─────────────────────────────────────────────────────────────────
    # LOSS-PROPORTIONAL HEDGE SIZING
    # ─────────────────────────────────────────────────────────────────

    def _calculate_hedge_size(self, bleed_usd, positions, size_factor=0.50):
        """
        Calculate how much BTC to hedge based on the current USD loss.
        
        The idea: if we're losing $X from options, we need a BTC position that
        will gain ~$X if BTC continues moving in the same direction by the same amount.
        
        We use the total option exposure as a baseline and scale by size_factor.
        """
        total_size = sum(data.get('size', 0) for data in positions.values())
        exposure_btc = total_size * 0.001  # Total BTC exposure
        
        # Size the hedge proportional to the exposure, scaled by factor
        hedge_btc = exposure_btc * size_factor
        
        # Minimum hedge size: at least 0.001 BTC
        hedge_btc = max(0.001, hedge_btc)
        
        app_logger.info(
            f"Hedge: Sizing — exposure={exposure_btc:.4f} BTC | "
            f"factor={size_factor:.0%} | hedge_size={hedge_btc:.4f} BTC"
        )
        return hedge_btc

    # ─────────────────────────────────────────────────────────────────
    # HEDGE EXECUTION (with weighted avg entry tracking)
    # ─────────────────────────────────────────────────────────────────

    def _place_hedge(self, size_btc, direction, label="HEDGE"):
        """
        Places a hedge order and updates the weighted average entry price.
        """
        result = self.execution.place_hedge_order(abs(size_btc), direction)

        if result and result.get('success'):
            fill_price = result.get('fill_price', 0)

            # Update weighted average entry price
            prev_abs_size = abs(self.hedge_size_btc)
            new_abs_size = abs(size_btc)
            total_abs = prev_abs_size + new_abs_size

            if total_abs > 0 and self.hedge_avg_entry_price > 0:
                self.hedge_avg_entry_price = (
                    (self.hedge_avg_entry_price * prev_abs_size + fill_price * new_abs_size) / total_abs
                )
            else:
                self.hedge_avg_entry_price = fill_price

            app_logger.info(
                f"Hedge [{label}]: {direction.upper()} {abs(size_btc):.4f} BTC @ ${fill_price:,.2f} | "
                f"Avg entry: ${self.hedge_avg_entry_price:,.2f} | "
                f"ID: {result.get('order_id', 'N/A')}"
            )
            return result

        app_logger.error(f"Hedge [{label}]: Order placement failed!")
        return None

    # ─────────────────────────────────────────────────────────────────
    # POST-ENTRY INITIAL CHECK
    # ─────────────────────────────────────────────────────────────────

    def run_post_entry_hedge(self, positions):
        """
        Called in a background thread immediately after strangle entry.
        """
        app_logger.info(f"Hedge: Scheduling post-entry hedge check in {HEDGE_WAIT_AFTER_ENTRY}s...")
        time.sleep(HEDGE_WAIT_AFTER_ENTRY)

        if not positions:
            app_logger.info("Hedge: Post-entry check cancelled — no active positions.")
            return

        self.set_entry_premiums(positions)
        
        # Check if any leg is already bleeding
        bleeding_leg, bleed_pct, bleed_usd, direction = self._detect_bleeding_leg(positions)
        
        if bleeding_leg and bleed_pct >= HEDGE_BLEED_TRIGGER_PCT:
            app_logger.info(f"Hedge: Post-entry — {bleeding_leg} already bleeding {bleed_pct*100:.1f}%. Hedging immediately.")
            self._open_new_hedge(positions, bleeding_leg, bleed_pct, bleed_usd, direction)
        else:
            app_logger.info(f"Hedge: Post-entry — No significant bleed detected. Monitoring...")

    # ─────────────────────────────────────────────────────────────────
    # CORE HEDGE MANAGEMENT (called every 10-15 seconds)
    # ─────────────────────────────────────────────────────────────────

    def manage_hedge(self, positions, unrealized_loss_pct, profit_usd=0.0):
        """
        Core hedge management loop — called from bot_engine monitor.
        
        v2 Logic:
        1. No positions → close hedge
        2. If stopped out → skip
        3. If hedge active → protect P&L (trailing breakeven), check for reversal, escalate
        4. If no hedge → detect bleeding and trigger if needed
        """
        self.last_check_time = time.time()

        # Step 1: No positions → close hedge
        if not positions:
            if self.hedge_active:
                app_logger.info("Hedge: Positions cleared. Closing hedge...")
                self.close_hedge()
            return

        # Step 2: Stopped out → skip
        if self.hedge_stopped_out:
            app_logger.info("Hedge: Stopped out — skipping management for this trade.")
            return

        # Detect which leg is bleeding
        bleeding_leg, bleed_pct, bleed_usd, direction = self._detect_bleeding_leg(positions)

        if self.hedge_active:
            # ── ACTIVE HEDGE MANAGEMENT ──
            self._manage_active_hedge(positions, bleeding_leg, bleed_pct, bleed_usd, direction)
        else:
            # ── NO HEDGE — CHECK IF WE NEED ONE ──
            self._check_and_trigger(positions, bleeding_leg, bleed_pct, bleed_usd, direction, unrealized_loss_pct)

    def _check_and_trigger(self, positions, bleeding_leg, bleed_pct, bleed_usd, direction, unrealized_loss_pct):
        """Check if we should open a new hedge."""
        
        if not bleeding_leg or bleed_pct < HEDGE_BLEED_TRIGGER_PCT:
            if bleeding_leg:
                app_logger.info(
                    f"Hedge: {bleeding_leg} bleeding {bleed_pct*100:.1f}% — below trigger ({HEDGE_BLEED_TRIGGER_PCT*100:.0f}%). Monitoring..."
                )
            else:
                app_logger.info("Hedge: No bleeding detected. Market stable.")
            return

        # Bleeding exceeds trigger threshold — HEDGE NOW
        app_logger.info(
            f"Hedge: TRIGGER! {bleeding_leg.upper()} bleeding {bleed_pct*100:.1f}% >= {HEDGE_BLEED_TRIGGER_PCT*100:.0f}% threshold. "
            f"Loss: ${bleed_usd:.2f}. Opening hedge..."
        )
        self._open_new_hedge(positions, bleeding_leg, bleed_pct, bleed_usd, direction)

    def _open_new_hedge(self, positions, bleeding_leg, bleed_pct, bleed_usd, direction):
        """Open a new hedge position."""
        
        # Determine size factor based on bleed severity
        if bleed_pct >= HEDGE_ESCALATE_BLEED_PCT:
            size_factor = HEDGE_FULL_SIZE_FACTOR
            label = "FULL"
        else:
            size_factor = HEDGE_INITIAL_SIZE_FACTOR
            label = "INITIAL"

        hedge_size = self._calculate_hedge_size(bleed_usd, positions, size_factor)
        
        result = self._place_hedge(hedge_size, direction, label)
        if result and result.get('success'):
            self.hedge_active = True
            self.hedge_type = f"premium_{label.lower()}"
            self.hedge_size_btc = hedge_size if direction == 'buy' else -hedge_size
            self.hedge_percentage = size_factor * 100
            self.hedge_order_id = result.get('order_id', 'N/A')
            self.hedge_placed_time = time.time()
            self._bleeding_leg = bleeding_leg
            self._hedge_peak_pnl = 0.0
            self._hedge_size_factor = size_factor
            self._hedge_direction = direction

            notifier.notify_hedge_executed(
                timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
                iv=self.dvol.get_current_dvol(),
                net_delta=0.0,
                hedge_type=f"PREMIUM {label} ({bleeding_leg.upper()} bleeding {bleed_pct*100:.0f}%)",
                size_btc=hedge_size,
                order_id=result.get('order_id', 'N/A')
            )
        else:
            app_logger.error("Hedge: Failed to open new hedge!")
            notifier.notify_hedge_failed()

    # ─────────────────────────────────────────────────────────────────
    # ACTIVE HEDGE MANAGEMENT
    # ─────────────────────────────────────────────────────────────────

    def _manage_active_hedge(self, positions, bleeding_leg, bleed_pct, bleed_usd, direction):
        """
        Manage an existing active hedge:
        1. Protect P&L (trailing breakeven stop)
        2. Detect reversal (market flipped direction)
        3. Escalate (increase size if bleed worsens)
        """
        hedge_pnl = self.get_live_hedge_pnl()
        
        # ── STEP 1: PROTECT HEDGE P&L ──────────────────────────────
        # Track peak P&L
        if hedge_pnl > self._hedge_peak_pnl:
            self._hedge_peak_pnl = hedge_pnl
            app_logger.info(f"Hedge: New peak P&L: ${self._hedge_peak_pnl:.2f}")

        # Hard stop: if hedge loses more than $1, close immediately
        if hedge_pnl <= HEDGE_MAX_LOSS_ABSOLUTE:
            app_logger.warning(
                f"Hedge: HARD STOP! P&L ${hedge_pnl:.2f} <= ${HEDGE_MAX_LOSS_ABSOLUTE:.2f}. "
                f"Closing to prevent further bleed."
            )
            self.close_hedge()
            self.hedge_stopped_out = True
            notifier.notify_error(
                f"Hedge Hard Stop Hit!\nHedge P&L: ${hedge_pnl:.2f}\n"
                f"Closed to prevent further loss."
            )
            return

        # Trailing breakeven: if hedge was profitable but now dropping back to zero
        if self._hedge_peak_pnl >= HEDGE_MIN_PROFIT_TO_TRAIL:
            if hedge_pnl <= HEDGE_BREAKEVEN_BUFFER:
                app_logger.info(
                    f"Hedge: TRAILING BREAKEVEN triggered! Peak was ${self._hedge_peak_pnl:.2f}, "
                    f"now ${hedge_pnl:.2f} <= ${HEDGE_BREAKEVEN_BUFFER:.2f}. Closing at breakeven."
                )
                self.close_hedge()
                notifier.notify_error(
                    f"Hedge closed at breakeven\n"
                    f"Peak profit was ${self._hedge_peak_pnl:.2f}, closed at ${hedge_pnl:.2f}"
                )
                return

        # ── STEP 2: REVERSAL DETECTION ─────────────────────────────
        if bleeding_leg and bleeding_leg != self._bleeding_leg and bleed_pct >= HEDGE_REVERSAL_THRESHOLD:
            # Market direction flipped — the OTHER leg is now bleeding
            app_logger.warning(
                f"Hedge: REVERSAL detected! Was hedging {self._bleeding_leg}, "
                f"now {bleeding_leg} is bleeding {bleed_pct*100:.1f}%. "
                f"Closing current hedge and re-hedging."
            )
            
            # Close current hedge (lock in whatever P&L it has)
            old_pnl = hedge_pnl
            self.close_hedge()
            
            # Only re-hedge if the new bleed is significant enough
            if bleed_pct >= HEDGE_BLEED_TRIGGER_PCT:
                app_logger.info(f"Hedge: Re-hedging in opposite direction ({direction})...")
                self._open_new_hedge(positions, bleeding_leg, bleed_pct, bleed_usd, direction)
            else:
                app_logger.info(f"Hedge: New bleed {bleed_pct*100:.1f}% below trigger. Monitoring...")
            return

        # ── STEP 3: ESCALATE ───────────────────────────────────────
        if (self._hedge_size_factor < HEDGE_FULL_SIZE_FACTOR and 
            bleed_pct >= HEDGE_ESCALATE_BLEED_PCT and 
            self._bleeding_leg == bleeding_leg):
            
            # Bleed has worsened — increase hedge from 50% to 100%
            additional_factor = HEDGE_FULL_SIZE_FACTOR - self._hedge_size_factor
            additional_size = self._calculate_hedge_size(bleed_usd, positions, additional_factor)
            
            result = self._place_hedge(additional_size, self._hedge_direction, "ESCALATE")
            if result and result.get('success'):
                current_signed = self.execution.hedge_size_btc
                self.hedge_size_btc = current_signed
                self._hedge_size_factor = HEDGE_FULL_SIZE_FACTOR
                self.hedge_type = "premium_full"
                self.hedge_percentage = 100.0
                
                app_logger.info(
                    f"Hedge: ESCALATED from 50% to 100%. Total size: {abs(current_signed):.4f} BTC"
                )
                notifier.notify_hedge_escalated(
                    timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
                    from_pct=50.0,
                    to_pct=100.0,
                    loss_pct=bleed_pct * 100
                )
            return

        # ── NO ACTION NEEDED ──
        app_logger.info(
            f"Hedge: Active ({self._bleeding_leg} hedge). P&L: ${hedge_pnl:+.2f} | "
            f"Peak: ${self._hedge_peak_pnl:.2f} | Size: {abs(self.execution.hedge_size_btc):.4f} BTC | "
            f"Bleed: {self._bleeding_leg}={bleed_pct*100:.1f}%"
        )

    # ─────────────────────────────────────────────────────────────────
    # CLOSE HEDGE
    # ─────────────────────────────────────────────────────────────────

    def close_hedge(self):
        """Closes all active hedge positions and resets all state."""
        if self.hedge_active:
            final_pnl = self.get_live_hedge_pnl()
            app_logger.info(f"Hedge: Closing hedge. Final P&L: ${final_pnl:+.2f}")
        else:
            app_logger.info("Hedge: Closing all smart hedge positions...")
        
        self.execution.close_hedge()

        # Reset ALL state
        self.hedge_active = False
        self.hedge_type = "None"
        self.hedge_percentage = 0.0
        self.hedge_size_btc = 0.0
        self.hedge_order_id = "None"
        self.sl_tightened = False
        self.hedge_placed_time = 0.0
        self.hedge_avg_entry_price = 0.0
        self.hedge_total_cost_btc = 0.0
        self._bleeding_leg = None
        self._hedge_peak_pnl = 0.0
        self._hedge_size_factor = 0.0
        self._hedge_direction = None
        app_logger.info("Hedge: Smart hedge state fully reset.")

    def _get_options_exposure_btc(self, positions):
        """Total option exposure in BTC (each lot = 0.001 BTC)."""
        total_size = sum(data.get('size', 0) for data in positions.values())
        return total_size * 0.001
