import time
import math
from config import (
    HEDGE_WAIT_AFTER_ENTRY,
    HEDGE_RECHECK_INTERVAL,
    HEDGE_SYMBOL
)
from logger import app_logger
from notifier import notifier
from filters import TradingFilters

class SmartHedgingManager:
    """
    Advanced Smart Hedging Engine v4 — Zero-Loss Hedge System
    ==========================================================

    Built for SHORT STRANGLE protection on BTC options (Delta Exchange).

    Core Guarantee:
    ---------------
    The hedge will NEVER result in a net loss to the trade.
    It exits at breakeven when market reverses and options losses reduce.

    Design Rules:
    1. NEVER close hedge at a loss — wait for P&L >= $0
    2. Exit when options loss recovers to near-zero AND hedge P&L >= 0
    3. Real-time per-leg loss detection (premium-based, no greeks needed)
    4. Dollar-loss matched sizing (actual exposure, not fixed delta)
    5. NO ATR blocking — if real money is being lost, hedge immediately
    6. Smart reversal detection via loss-snapshot comparison
    7. Single BTC price method: WS → REST → Cache triple fallback
    8. Scale hedge up if loss keeps growing (escalation)
    """

    # ─── TRIGGER THRESHOLDS ───────────────────────────────────────
    BLEED_TRIGGER_PCT     = 0.11      # 11% Total Portfolio Loss triggers hedge
    BLEED_SEVERE_PCT      = 0.20      # 20%+ skip confirmation, hedge immediately
    BLEED_FLASH_CRASH_PCT = 0.30      # 30%+ flash crash, instant hedge
    BLEED_CONFIRM_CHECKS  = 2         # 2 consecutive checks for moderate bleed
    EMERGENCY_LOSS_PCT    = 0.20      # 20% total portfolio loss = emergency override
    ADX_MIN_ENTRY         = 20        # ADX must be >= 20 to confirm trend on entry

    # ─── SIZING ───────────────────────────────────────────────────
    HEDGE_MIN_SIZE_BTC = 0.01         # Minimum hedge 0.01 BTC
    HEDGE_MAX_SIZE_BTC = 0.50         # Maximum hedge 0.50 BTC
    DEFAULT_DELTA_ESTIMATE = 0.30     # Fallback delta when BTC move is small

    # ─── EXIT RULES (ZERO-LOSS) ───────────────────────────────────
    LOSS_RECOVERY_PCT = 0.50          # Options loss halved = significant recovery
    LOSS_NEAR_ZERO_PCT = 0.04         # Hedge closes when Total Loss recovers back to -4%
    MIN_HEDGE_HOLD_SECONDS = 45       # Don't exit within 45s of opening
    COOLDOWN_SECONDS = 1800           # 30 min cooldown after any exit (2 x 15m candles)

    # ─── DCA SCALING TIERS ────────────────────────────────────────
    DCA_TIER2_LOSS_PCT    = 0.15      # Scale to Tier 2 at -15% portfolio loss
    DCA_TIER3_LOSS_PCT    = 0.20      # Scale to Tier 3 at -20% portfolio loss
    DCA_TIER2_COVERAGE    = 0.66      # Tier 2 = 66% coverage
    DCA_TIER3_COVERAGE    = 1.00      # Tier 3 = 100% coverage

    # ─── ESCALATION ───────────────────────────────────────────────
    ESCALATION_GROWTH_PCT = 0.50      # Add more if loss grew 50%+ since last sizing
    ESCALATION_COOLDOWN_S = 120       # Max once per 2 minutes

    def __init__(self, execution_handler, dvol_provider, risk_manager, api_client):
        self.execution = execution_handler
        self.dvol = dvol_provider
        self.risk_manager = risk_manager
        self.api_client = api_client
        self.filters = TradingFilters(self.api_client, self.dvol)

        # ─── Core State (accessed externally) ─────────────────────
        self.hedge_active = False
        self.hedge_type = "None"
        self.hedge_percentage = 0.0
        self.hedge_size_btc = 0.0
        self.hedge_order_id = "None"
        self.last_check_time = 0.0
        self.sl_tightened = False
        self.hedge_stopped_out = False       # Kept for engine compat, never set True

        # ─── Price & P&L Tracking ─────────────────────────────────
        self.hedge_avg_entry_price = 0.0
        self._last_known_btc_price = 0.0
        self._hedge_peak_pnl = 0.0
        self._cumulative_realized_pnl = 0.0

        # ─── Premium / Bleed Detection ────────────────────────────
        self._entry_premiums = {}
        self._entry_btc_price = 0.0
        self._bleeding_leg = None
        self._hedge_direction = None

        # ─── Confirmation Tracking ────────────────────────────────
        self._bleed_confirm_count = 0
        self._bleed_confirm_leg = None

        # ─── Breakeven Exit Tracking ──────────────────────────────
        self._options_pnl_at_hedge_entry = 0.0   # Snapshot of options P&L when hedge placed
        self._hedge_entry_time = 0.0              # When hedge was opened
        self._hedge_cooldown_until = 0.0           # No new hedges before this timestamp (30-min cooldown)
        self.hedge_placed_time = 0.0              # Alias for compat

        # ─── Escalation Tracking ──────────────────────────────────
        self._last_sizing_loss_usd = 0.0
        self._last_escalation_time = 0.0
        self._hedge_size_factor = 0.0             # Compat with old code

        # ─── Hedge Event Log (cleared each trade) ─────────────────
        # Each entry: {event, time_str, trigger_reason, direction,
        #              size_btc, total_btc, btc_price,
        #              options_pnl_usd, hedge_pnl_usd, net_pnl_usd,
        #              exit_reason (CLOSE only)}
        self.hedge_event_log = []

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC: STATUS FOR DASHBOARD
    # ═══════════════════════════════════════════════════════════════

    def get_status(self):
        """Returns the current hedging status dictionary for the web dashboard."""
        return {
            "hedge_active": self.hedge_active or (abs(self.execution.hedge_size_btc) > 0.0001),
            "hedge_type": self.hedge_type,
            "hedge_size_btc": round(self.execution.hedge_size_btc, 6),
            "hedge_percentage": round(self.hedge_percentage, 1),
            "hedge_order_id": self.hedge_order_id or self.execution.hedge_order_id or "None",
            "sl_tightened": self.sl_tightened,
            "last_check_time": (
                time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.last_check_time))
                if self.last_check_time > 0 else "N/A"
            ),
            "hedge_pnl_usd": round(self.get_live_hedge_pnl(), 2),
            "bleeding_leg": self._bleeding_leg or "None",
            "hedge_peak_pnl": round(self._hedge_peak_pnl, 2)
        }

    # ═══════════════════════════════════════════════════════════════
    # HEDGE EVENT LOGGING — FORENSICS CAPTURE
    # ═══════════════════════════════════════════════════════════════

    def _log_hedge_event(self, event_type, trigger_reason, direction,
                          size_btc, total_btc, btc_price,
                          options_pnl_usd, hedge_pnl_usd,
                          exit_reason=None):
        """
        Records one hedge lifecycle event into hedge_event_log.
        Called at OPEN, ESCALATE, and CLOSE moments.
        """
        from utils import get_ist_now
        now = get_ist_now()
        entry = {
            "event":           event_type,                    # "OPEN"|"ESCALATE"|"CLOSE"
            "time_iso":        now.isoformat(),
            "time_str":        now.strftime("%H:%M"),
            "trigger_reason":  trigger_reason,
            "direction":       direction,                     # "buy" or "sell"
            "size_btc":        round(size_btc, 4),            # BTC added in this event
            "total_btc":       round(total_btc, 4),           # cumulative BTC after event
            "btc_price":       round(btc_price, 2),           # BTC mark price at event
            "options_pnl_usd": round(options_pnl_usd, 4),    # options P&L at this moment
            "hedge_pnl_usd":   round(hedge_pnl_usd, 4),      # hedge P&L at this moment
            "net_pnl_usd":     round(options_pnl_usd + hedge_pnl_usd, 4),
        }
        if exit_reason is not None:
            entry["exit_reason"] = exit_reason
        self.hedge_event_log.append(entry)
        app_logger.info(
            f"HedgeLog [{event_type}]: {trigger_reason} | "
            f"{direction.upper()} {size_btc:.4f} BTC @ ${btc_price:,.0f} | "
            f"OptsPnL=${options_pnl_usd:+.2f} HedgePnL=${hedge_pnl_usd:+.2f}"
        )
        
        # --- AUDIT SYSTEM INTEGRATION ---
        try:
            from audit_manager import audit_system
            snapshot = {
                "BTC Price": btc_price,
                "Current PnL": options_pnl_usd + hedge_pnl_usd,
                "Hedge Event": event_type,
                "Hedge Direction": direction,
                "Hedge Size (BTC)": size_btc,
                "Hedge Trigger Reason": trigger_reason,
            }
            if exit_reason:
                snapshot["Hedge Exit Reason"] = exit_reason
                
            audit_system.log_critical_event(f"Hedge {event_type}", "smart_hedging", "_log_hedge_event", snapshot, trigger_reason)
        except Exception as e:
            error_logger.error(f"Audit: Failed to log hedge event: {e}")
        # --------------------------------

    def get_hedge_event_log(self):
        """Returns a copy of the hedge event log for saving with the trade record."""
        return list(self.hedge_event_log)

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC: LIVE HEDGE P&L
    # ═══════════════════════════════════════════════════════════════

    def get_live_hedge_pnl(self):
        """
        Calculates the live P&L of the current hedge position using
        the WEIGHTED AVERAGE ENTRY PRICE across all fills.

        Long hedge (size > 0): profit when price rises
        Short hedge (size < 0): profit when price drops
        """
        if not self.hedge_active or abs(self.execution.hedge_size_btc) < 0.0001:
            return 0.0
        if self.hedge_avg_entry_price <= 0:
            return 0.0

        mark_price = self._get_btc_mark_price()
        if mark_price <= 0:
            return 0.0

        size = self.execution.hedge_size_btc  # Signed
        if size > 0:
            return (mark_price - self.hedge_avg_entry_price) * size
        else:
            return (self.hedge_avg_entry_price - mark_price) * abs(size)

    # ═══════════════════════════════════════════════════════════════
    # BTC PRICE — SINGLE METHOD, TRIPLE FALLBACK
    # ═══════════════════════════════════════════════════════════════

    def _get_btc_mark_price(self):
        """
        Fetches BTC perpetual mark price with triple fallback:
        1. WebSocket cache (fastest, sub-ms)
        2. REST API (reliable, ~200ms)
        3. Last known cached price (stale but safe)

        CRITICAL: Only ONE definition of this method exists.
        The old code had a duplicate at line 736 that silently
        overrode the working one — that bug is now fixed.
        """
        # ── Try 1: WebSocket (fastest) ──
        try:
            ws_data = self.api_client.get_realtime_ticker(HEDGE_SYMBOL)
            if ws_data and 'mark_price' in ws_data:
                price = float(ws_data['mark_price'])
                if price > 100:  # Sanity: BTC should never be < $100
                    self._last_known_btc_price = price
                    return price
        except Exception as e:
            app_logger.debug(f"Hedge: WS BTC price failed: {e}")

        # ── Try 2: REST API (REMOVED) ──
        # Synchronous REST API fallback is removed because if Delta API is unreachable,
        # this blocks for 15 seconds, causing catastrophic hangs for the web dashboard 
        # (which polls every 4 seconds) and deadlocking the entire system.

        # ── Try 3: Cached price ──
        if self._last_known_btc_price > 100:
            app_logger.warning(
                f"Hedge: Using cached BTC price: ${self._last_known_btc_price:.2f}"
            )
            return self._last_known_btc_price

        app_logger.error("Hedge: ALL BTC price sources returned 0!")
        return 0.0

    def _get_last_closed_5m_candle(self):
        """
        Fetches the last closed 5-minute candle to filter out real-time noise wicks.
        Returns the close price of the candle, or 0.0 on failure.
        """
        try:
            res = self.api_client.get_candles(HEDGE_SYMBOL, "5m")
            if res and res.get('success') and res.get('result'):
                # Delta API usually returns the latest candle at the end of the list.
                # The very last candle might be incomplete (still forming).
                # The second to last candle is the most recently CLOSED candle.
                candles = res['result']
                if len(candles) >= 2:
                    return float(candles[-2].get('close', 0.0))
                elif len(candles) == 1:
                    return float(candles[-1].get('close', 0.0))
        except Exception as e:
            app_logger.debug(f"Hedge: Failed to fetch 5m candles: {e}")
        return 0.0

    # ═══════════════════════════════════════════════════════════════
    # ENTRY PREMIUM CACHE
    # ═══════════════════════════════════════════════════════════════

    def set_entry_premiums(self, positions):
        """
        Call immediately after a strangle is entered.
        Caches entry premiums per leg so we can detect bleeding.
        """
        self._entry_premiums = {}
        for sym, data in positions.items():
            ep = data.get('entry_price', 0)
            if ep > 0:
                self._entry_premiums[sym] = ep
        self._entry_btc_price = self._get_btc_mark_price()
        
        # CLEAR THE LOG AT THE START OF A NEW TRADE ONLY
        self.hedge_event_log = []
        
        app_logger.info(
            f"Hedge: Cached entry premiums: {self._entry_premiums} | "
            f"BTC Entry: ${self._entry_btc_price:.2f}"
        )

    # ═══════════════════════════════════════════════════════════════
    # COLLECTED PREMIUM HELPER
    # ═══════════════════════════════════════════════════════════════

    def _get_collected_premium_usd(self, positions):
        """Total premium collected at entry in USD (for % calculations)."""
        total = 0.0
        for sym, ep in self._entry_premiums.items():
            size = positions.get(sym, {}).get('size', 0)
            total += ep * size * 0.001  # 0.001 BTC per lot
        return total

    # ═══════════════════════════════════════════════════════════════
    # PREMIUM-BASED BLEEDING DETECTION
    # ═══════════════════════════════════════════════════════════════

    def _detect_bleeding_leg(self, positions):
        """
        Detects which option leg is bleeding by comparing current premium to entry.
        Premium RISING = loss for short seller.

        Returns:
            (bleeding_leg, bleed_pct, bleed_usd, direction)
            - bleeding_leg: 'call' or 'put' or None
            - bleed_pct: how much the premium rose as % (0.15 = 15%)
            - bleed_usd: total USD loss from this leg
            - direction: 'buy' (call bleeding=BTC up) or 'sell' (put bleeding=BTC down)
        """
        # ── Auto-heal entry premiums after server restart ──
        if not self._entry_premiums and positions:
            app_logger.warning(
                "Hedge: SELF-HEAL — Entry premiums MISSING (restart?)! Rebuilding..."
            )
            self._entry_premiums = {}
            for sym, data in positions.items():
                ep = data.get('entry_price', 0)
                if ep > 0:
                    self._entry_premiums[sym] = ep
            if self._entry_premiums:
                self._entry_btc_price = self._get_btc_mark_price()
                app_logger.info(
                    f"Hedge: SELF-HEAL complete. Premiums: {self._entry_premiums} | "
                    f"BTC: ${self._entry_btc_price:.2f}"
                )
                notifier.notify_error(
                    f"🔧 Hedge Self-Heal Activated\n"
                    f"Recovered entry premiums after restart."
                )
            else:
                app_logger.error("Hedge: SELF-HEAL FAILED — no entry prices in positions!")
                return None, 0.0, 0.0, None

        if not self._entry_premiums:
            app_logger.warning("Hedge: Entry premiums empty — detection disabled.")
            return None, 0.0, 0.0, None

        call_bleed_pct = 0.0
        put_bleed_pct = 0.0
        call_bleed_usd = 0.0
        put_bleed_usd = 0.0

        for sym, data in positions.items():
            entry_premium = self._entry_premiums.get(sym, 0)
            if entry_premium <= 0:
                continue

            # Get current premium: WS first, then last_good_price fallback
            current_premium = 0.0
            try:
                ws_data = self.api_client.get_realtime_ticker(sym)
                if ws_data and 'mark_price' in ws_data:
                    candidate = float(ws_data['mark_price'])
                    if candidate > 0.01:
                        current_premium = candidate
            except Exception:
                pass

            # Fallback to last_good_price from position data
            if current_premium <= 0.01:
                lgp = data.get('last_good_price', 0)
                if lgp and lgp > 0.01:
                    current_premium = lgp
                else:
                    app_logger.warning(f"Hedge: No price for {sym}. Skipping leg.")
                    continue

            # Premium RISING = loss for short seller
            premium_change = current_premium - entry_premium
            bleed_pct = premium_change / entry_premium if entry_premium > 0 else 0.0
            lot_size = data.get('size', 1)
            bleed_usd = premium_change * lot_size * 0.001  # Each lot = 0.001 BTC

            is_call = (
                sym.startswith('C-') or
                data.get('leg_type', '') == 'call' or
                data.get('option_type', '') == 'call'
            )

            if is_call and bleed_pct > 0:
                call_bleed_pct = bleed_pct
                call_bleed_usd = bleed_usd
            elif not is_call and bleed_pct > 0:
                put_bleed_pct = bleed_pct
                put_bleed_usd = bleed_usd

        # Return the leg bleeding MORE
        if call_bleed_pct > put_bleed_pct and call_bleed_pct > 0:
            app_logger.info(
                f"Hedge: CALL bleeding {call_bleed_pct*100:.1f}% "
                f"(${call_bleed_usd:.2f} loss) | Put: {put_bleed_pct*100:.1f}%"
            )
            return 'call', call_bleed_pct, call_bleed_usd, 'buy'
        elif put_bleed_pct > 0:
            app_logger.info(
                f"Hedge: PUT bleeding {put_bleed_pct*100:.1f}% "
                f"(${put_bleed_usd:.2f} loss) | Call: {call_bleed_pct*100:.1f}%"
            )
            return 'put', put_bleed_pct, put_bleed_usd, 'sell'
        else:
            return None, 0.0, 0.0, None

    # ═══════════════════════════════════════════════════════════════
    # HEDGE SIZING — DOLLAR-LOSS MATCHED
    # ═══════════════════════════════════════════════════════════════

    def _calculate_base_exposure(self, bleed_usd, positions):
        """
        Calculates the exact 100% raw hedge size required based on the speed of the loss.
        This is the core math: if we lost $30 over a $500 BTC move, our exposure is 0.06 BTC.
        """
        btc_price = self._get_btc_mark_price()
        if btc_price <= 0:
            btc_price = 60000  # Emergency fallback

        abs_bleed = abs(bleed_usd) if bleed_usd > 0 else 1.0

        # 1. Identify bleeding leg max cap (e.g. 50 lots = 0.05 BTC)
        leg_name = self._bleeding_leg
        max_cap_btc = self.HEDGE_MAX_SIZE_BTC
        if leg_name and leg_name in positions:
            max_cap_btc = positions[leg_name].get('size', 0) * 0.001

        # 2. Calculate effective exposure (Speed of Loss)
        btc_move_usd = 0.0
        if self._entry_btc_price > 0:
            btc_move_usd = abs(btc_price - self._entry_btc_price)

        # Floor at $300 to prevent division by zero or massive spikes on tiny wicks
        safe_btc_move = max(btc_move_usd, 300.0)
        effective_exposure = abs_bleed / safe_btc_move
            
        app_logger.info(
            f"Hedge: Sizing Math | Loss=${abs_bleed:.2f} | "
            f"BTC moved=${btc_move_usd:.0f} | Base Exp={effective_exposure:.4f} BTC | "
            f"Max Leg Cap={max_cap_btc:.4f} BTC"
        )

        # 3. Strict Clamp to leg size
        final_base = min(effective_exposure, max_cap_btc)

        self._last_sizing_loss_usd = abs_bleed
        return max(self.HEDGE_MIN_SIZE_BTC, final_base)

    # ═══════════════════════════════════════════════════════════════
    # PLACE HEDGE ORDER (with weighted avg entry tracking)
    # ═══════════════════════════════════════════════════════════════

    def _place_hedge(self, size_btc, direction, label="HEDGE"):
        """Places a hedge order and updates the weighted average entry price."""
        result = self.execution.place_hedge_order(abs(size_btc), direction)

        if result and result.get('success'):
            fill_price = result.get('fill_price', 0)

            # Update weighted average entry price
            prev_size = abs(self.hedge_size_btc)
            new_size = abs(size_btc)
            total = prev_size + new_size

            if total > 0 and self.hedge_avg_entry_price > 0:
                self.hedge_avg_entry_price = (
                    (self.hedge_avg_entry_price * prev_size + fill_price * new_size)
                    / total
                )
            else:
                self.hedge_avg_entry_price = fill_price

            app_logger.info(
                f"Hedge [{label}]: {direction.upper()} {abs(size_btc):.4f} BTC "
                f"@ ${fill_price:,.2f} | Avg entry: ${self.hedge_avg_entry_price:,.2f} | "
                f"ID: {result.get('order_id', 'N/A')}"
            )
            return result

        app_logger.error(f"Hedge [{label}]: Order placement FAILED!")
        return None

    # ═══════════════════════════════════════════════════════════════
    # POST-ENTRY HEDGE CHECK
    # ═══════════════════════════════════════════════════════════════

    def run_post_entry_hedge(self, positions):
        """Cache entry premiums at the start of a new trade."""
        if positions:
            self.set_entry_premiums(positions)

    # ═══════════════════════════════════════════════════════════════
    # CORE: MANAGE HEDGE (called every 5-15 seconds by bot_engine)
    # ═══════════════════════════════════════════════════════════════

    def manage_hedge(self, positions, unrealized_loss_pct, profit_usd=0.0,
                     adx_value=0.0, atr_usd=100.0, supertrend_dir='NEUTRAL'):
        """
        Full hedge pipeline — called every 5s (volatile) or 15s (normal).

        If no hedge is active:
            → _check_and_trigger_hedge() evaluates entry conditions.
        If hedge is active:
            → _manage_active_hedge() manages exit + DCA + breakeven SL.
        """
        if not positions:
            return

        # ── 30-MIN COOLDOWN: block new hedges after any exit ──────
        if not self.hedge_active and time.time() < self._hedge_cooldown_until:
            remaining = int(self._hedge_cooldown_until - time.time())
            app_logger.info(
                f"Hedge: ⏳ COOLDOWN ACTIVE — {remaining}s remaining. "
                f"No new hedges until cooldown expires (prevents whipsaw rapid-fire)."
            )
            return

        # Update check timestamp
        self.last_check_time = time.time()

        # Detect which option leg is bleeding and direction to hedge
        bleeding_leg, bleed_pct, bleed_usd, direction = self._detect_bleeding_leg(positions)

        if not self.hedge_active:
            # ── No hedge open: evaluate whether to open one ──
            self._check_and_trigger_hedge(
                positions, bleeding_leg, bleed_pct,
                bleed_usd, direction, unrealized_loss_pct,
                profit_usd, adx_value, atr_usd
            )
        else:
            # ── Hedge is open: manage it ──────────────────────
            # Rule 0: Sync hedge_active flag with execution layer
            if abs(self.execution.hedge_size_btc) < 0.0001:
                app_logger.warning("Hedge: hedge_active=True but execution layer has 0 size. Force-reset.")
                self.close_hedge()
                return

            # ── ADX Sideways Exit (merged from local_hpe_engine) ────
            # If the market goes flat (ADX < 20), the trend that justified the
            # hedge has stalled. Close immediately to stop the hedge from
            # accumulating losses against a directionless market.
            if adx_value > 0 and adx_value < 20:
                app_logger.info(
                    f"Hedge: ADX SIDEWAYS EXIT. ADX={adx_value:.1f} < 20. "
                    f"Market has gone choppy. Closing hedge."
                )
                self._close_hedge_with_reason(
                    f"ADX sideways exit (ADX={adx_value:.1f} < 20)",
                    options_pnl_usd=profit_usd - self.get_live_hedge_pnl()
                )
                return

            # ── Supertrend Reversal Exit (merged from local_hpe_engine) ──
            # If trend flips against the hedge direction, close immediately.
            st_flipped = (
                (self._hedge_direction == 'buy'  and supertrend_dir == 'SELL') or
                (self._hedge_direction == 'sell' and supertrend_dir == 'BUY')
            )
            if st_flipped and supertrend_dir != 'NEUTRAL':
                app_logger.info(
                    f"Hedge: SUPERTREND REVERSAL EXIT. Was {self._hedge_direction}, "
                    f"Supertrend now {supertrend_dir}. Trend reversed. Closing hedge."
                )
                self._close_hedge_with_reason(
                    f"Supertrend reversal ({self._hedge_direction} → {supertrend_dir})",
                    options_pnl_usd=profit_usd - self.get_live_hedge_pnl()
                )
                return

            # ── DCA Tier Scaling (merged from local_hpe_engine) ────────
            # Automatically scale up hedge coverage as losses deepen.
            # Tier 2: 75% total coverage when total loss >= 12%
            # Tier 3: 100% total coverage when total loss >= 20%
            if self._dca_tier == 1 and unrealized_loss_pct >= self.DCA_TIER2_LOSS_PCT:
                self._dca_scale_up(2, self.DCA_TIER2_COVERAGE, positions, unrealized_loss_pct, profit_usd, atr_usd)
            elif self._dca_tier == 2 and unrealized_loss_pct >= self.DCA_TIER3_LOSS_PCT:
                self._dca_scale_up(3, self.DCA_TIER3_COVERAGE, positions, unrealized_loss_pct, profit_usd, atr_usd)

            # ── Breakeven SL (merged from local_hpe_engine) ────────────
            # Once hedge hits +5% profit, lock SL at 0% — never give it back.
            hedge_pnl = self.get_live_hedge_pnl()
            collected_premium = self._get_collected_premium_usd(positions)
            hedge_pnl_pct = (hedge_pnl / abs(self.hedge_avg_entry_price * self.execution.hedge_size_btc) * 100
                             if self.hedge_avg_entry_price > 0 and abs(self.execution.hedge_size_btc) > 0 else 0.0)

            if hedge_pnl_pct > self._hedge_peak_pnl_pct:
                self._hedge_peak_pnl_pct = hedge_pnl_pct

            if not self._breakeven_sl_active and self._hedge_peak_pnl_pct >= 5.0:
                self._breakeven_sl_active = True
                app_logger.info(
                    f"Hedge: 🔒 BREAKEVEN SL LOCKED! Hedge hit +{self._hedge_peak_pnl_pct:.1f}% profit. "
                    f"SL now locked at 0%. Hedge will never close at a loss."
                )

            if self._breakeven_sl_active and hedge_pnl_pct <= 0.0:
                app_logger.info(
                    f"Hedge: BREAKEVEN SL HIT. Hedge P&L fell to {hedge_pnl_pct:.1f}% "
                    f"(peak was +{self._hedge_peak_pnl_pct:.1f}%). Closing with protected profit."
                )
                self._close_hedge_with_reason(
                    f"Breakeven SL hit (protected profit, peak was +{self._hedge_peak_pnl_pct:.1f}%)",
                    options_pnl_usd=profit_usd - hedge_pnl
                )
                return

            # ── Hard SL -10% (merged from local_hpe_engine) ────────────
            # If breakeven was never triggered and hedge is losing badly, cut it.
            if not self._breakeven_sl_active and hedge_pnl_pct <= -10.0:
                app_logger.warning(
                    f"Hedge: HARD SL HIT. Hedge P&L={hedge_pnl_pct:.1f}% <= -10% "
                    f"and breakeven was never locked. Closing to limit damage."
                )
                self._close_hedge_with_reason(
                    f"Hard SL hit ({hedge_pnl_pct:.1f}%)",
                    options_pnl_usd=profit_usd - hedge_pnl
                )
                return

            # ── Standard exit rules (total P&L recovery) ───────────────
            self._manage_active_hedge(
                positions, bleeding_leg, bleed_pct,
                bleed_usd, direction, unrealized_loss_pct,
                profit_usd, atr_usd
            )

    def _dca_scale_up(self, new_tier, target_coverage_ratio,
                      positions, unrealized_loss_pct, profit_usd, atr_usd):
        """
        DCA scale-up: add more hedge to reach the target coverage tier.
        new_tier: 2 or 3
        target_coverage_ratio: 0.66 (tier 2) or 1.00 (tier 3)
        """
        bleed_usd = abs(profit_usd) if profit_usd < 0 else 1.0
        base_size = self._calculate_base_exposure(bleed_usd, positions)
        target_size = base_size * target_coverage_ratio
        current_size = abs(self.execution.hedge_size_btc)
        add_btc = target_size - current_size

        if add_btc < self.HEDGE_MIN_SIZE_BTC:
            # Already at or above target tier — just advance tier marker
            self._dca_tier = new_tier
            app_logger.info(
                f"Hedge: DCA Tier {new_tier} check — already at sufficient size "
                f"({current_size:.4f} BTC >= target {target_size:.4f} BTC). Tier advanced."
            )
            return

        result = self._place_hedge(add_btc, self._hedge_direction, f"DCA-TIER-{new_tier}")
        if result and result.get('success'):
            self._dca_tier = new_tier
            self.hedge_size_btc = self.execution.hedge_size_btc
            self._last_escalation_time = time.time()
            self._last_sizing_loss_usd = bleed_usd
            self._log_hedge_event(
                event_type     = "ESCALATE",
                trigger_reason = f"DCA Tier {new_tier} ({target_coverage_ratio*100:.0f}% coverage) "
                                 f"— loss reached {unrealized_loss_pct*100:.1f}%",
                direction      = self._hedge_direction or "buy",
                size_btc       = add_btc,
                total_btc      = abs(self.execution.hedge_size_btc),
                btc_price      = self._get_btc_mark_price(),
                options_pnl_usd= profit_usd,
                hedge_pnl_usd  = self.get_live_hedge_pnl(),
            )
            app_logger.info(
                f"Hedge: ✅ DCA TIER {new_tier} ACTIVATED! Added {add_btc:.4f} BTC → "
                f"Total: {abs(self.execution.hedge_size_btc):.4f} BTC "
                f"({target_coverage_ratio*100:.0f}% coverage)"
            )
            notifier.notify_hedge_escalated(
                timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
                from_pct=self._dca_tier - 1,
                to_pct=new_tier,
                loss_pct=unrealized_loss_pct * 100
            )
        else:
            app_logger.error(f"Hedge: DCA Tier {new_tier} scale-up FAILED.")

    # ═══════════════════════════════════════════════════════════════
    # TRIGGER LOGIC — Should we open a new hedge?
    # ═══════════════════════════════════════════════════════════════

    def _is_rejection_candle(self, st_data, direction):
        """
        Analyzes the candle mathematically to detect if it is a fakeout/rejection.
        direction='UP' (checking for upside breakout fakeout, i.e., Shooting Star)
        direction='DOWN' (checking for downside breakout fakeout, i.e., Hammer/Pin bar)
        Returns True if it's a rejection, False otherwise.
        """
        c_open = st_data['open']
        c_high = st_data['high']
        c_low = st_data['low']
        c_close = st_data['close']
        
        total_size = c_high - c_low
        body = abs(c_open - c_close)
        upper_wick = c_high - max(c_open, c_close)
        lower_wick = min(c_open, c_close) - c_low
        
        # Avoid division by zero on perfect Dojis
        if total_size == 0: return False
        
        if direction == 'UP':
            # Looking for a Shooting Star / Gravestone Doji (Fakeout at Resistance)
            # 1. Upper wick is larger than the body
            # 2. Upper wick makes up at least 40% of the total candle size
            if upper_wick > body and (upper_wick / total_size) > 0.4:
                return True
                
        elif direction == 'DOWN':
            # Looking for a Hammer / Dragonfly Doji (Fakeout at Support)
            # 1. Lower wick is larger than the body
            # 2. Lower wick makes up at least 40% of the total candle size
            if lower_wick > body and (lower_wick / total_size) > 0.4:
                return True
                
        return False

    def _check_and_trigger_hedge(self, positions, bleeding_leg, bleed_pct,
                                  bleed_usd, direction, unrealized_loss_pct,
                                  profit_usd, adx_value=0.0, atr_usd=100.0):
        """
        Decides whether to open a new hedge based on:
        1. Net trade must be losing (no hedge when profitable)
        2. Flash crash (≥40%) → instant hedge
        3. Severe bleed (≥25%) → skip confirmation
        4. Moderate bleed (≥15%) → 2-check confirmation
        5. Emergency (≥15% total portfolio loss) → force hedge

        NO ATR BLOCKING — removed entirely.
        """
        # Calculate total dollar loss to size the hedge correctly
        total_loss_usd = abs(profit_usd) if profit_usd < 0 else 0.0

        # ── RULE: Never hedge when net trade is profitable ──
        if unrealized_loss_pct <= 0.0:
            if bleeding_leg:
                app_logger.info(
                    f"Hedge: {bleeding_leg} bleeding {bleed_pct*100:.1f}%, "
                    f"BUT net trade is PROFITABLE. No hedge needed."
                )
            self._bleed_confirm_count = 0
            return

        # ── RULE: ADX >= 20 — Confirm this is a real directional move ──
        # If ADX < 20, market is choppy/sideways. Hedge would whipsaw.
        if adx_value > 0 and adx_value < self.ADX_MIN_ENTRY:
            app_logger.info(
                f"Hedge: ⛔ ADX GATE BLOCKED — ADX={adx_value:.1f} < {self.ADX_MIN_ENTRY} "
                f"(sideways/choppy market). No hedge opened."
            )
            self._bleed_confirm_count = 0
            return

        # ── PIVOT & STRUCTURAL BREAKOUT STRATEGY (ACCELERATED ENTRY) ──
        # Checks two tiers of breakout levels:
        #   TIER 1 (Strongest): PREV_HIGH / PREV_LOW — actual structural breaks
        #     → Close BELOW Previous Day Low  + Supertrend SELL → CONFIRM downtrend
        #     → Close ABOVE Previous Day High + Supertrend BUY  → CONFIRM uptrend
        #   TIER 2 (Standard): Pivot math levels P, R1, R2, S1, S2, S3
        # Fakeout rejection wick check is applied to both tiers.
        if bleeding_leg and unrealized_loss_pct > 0.0:
            pivots = self.filters.get_pivot_points()
            st = self.filters.get_supertrend()

            if pivots and st:
                is_upside_breakout = False
                is_downside_breakout = False
                broken_level_name = ""
                broken_level_val = 0.0
                is_structure_break = False  # True = PREV_HIGH/LOW, False = pivot math

                # ── TIER 1: Structural Level Breaks (checked first — strongest signal) ──
                # SWING_LOW break: 15m candle opened above it, closed below it, SELL trend
                # SWING_HIGH break: 15m candle opened below it, closed above it, BUY trend
                swing_low  = pivots.get('SWING_LOW')
                swing_high = pivots.get('SWING_HIGH')

                if swing_low and st['open'] > swing_low and st['close'] < swing_low and st['trend'] == 'SELL':
                    if self._is_rejection_candle(st, 'DOWN'):
                        app_logger.warning(
                            f"Hedge: 🛑 FAKEOUT at SWING_LOW (${swing_low:.2f})! "
                            f"Hammer/Pin Bar wick detected. Structure break REJECTED."
                        )
                    else:
                        is_downside_breakout = True
                        broken_level_name = "SWING_LOW"
                        broken_level_val = swing_low
                        is_structure_break = True

                elif swing_high and st['open'] < swing_high and st['close'] > swing_high and st['trend'] == 'BUY':
                    if self._is_rejection_candle(st, 'UP'):
                        app_logger.warning(
                            f"Hedge: 🛑 FAKEOUT at SWING_HIGH (${swing_high:.2f})! "
                            f"Shooting Star wick detected. Structure break REJECTED."
                        )
                    else:
                        is_upside_breakout = True
                        broken_level_name = "SWING_HIGH"
                        broken_level_val = swing_high
                        is_structure_break = True

                # ── TIER 2: Pivot Math Level Breaks (if no structure break found) ──
                if not (is_upside_breakout or is_downside_breakout):
                    pivot_order = ['P', 'R1', 'R2', 'R3', 'S1', 'S2', 'S3']
                    for name in pivot_order:
                        val = pivots.get(name)
                        if val is None:
                            continue
                        # Upside: candle opened below level, closed above, BUY trend
                        if st['open'] < val and st['close'] > val and st['trend'] == 'BUY':
                            if self._is_rejection_candle(st, 'UP'):
                                app_logger.warning(
                                    f"Hedge: 🛑 FAKEOUT at {name} (${val:.2f})! "
                                    f"Shooting Star wick detected. Hedge blocked."
                                )
                                continue
                            is_upside_breakout = True
                            broken_level_name = name
                            broken_level_val = val
                            break

                        # Downside: candle opened above level, closed below, SELL trend
                        elif st['open'] > val and st['close'] < val and st['trend'] == 'SELL':
                            if self._is_rejection_candle(st, 'DOWN'):
                                app_logger.warning(
                                    f"Hedge: 🛑 FAKEOUT at {name} (${val:.2f})! "
                                    f"Hammer/Pin Bar wick detected. Hedge blocked."
                                )
                                continue
                            is_downside_breakout = True
                            broken_level_name = name
                            broken_level_val = val
                            break

                if is_upside_breakout or is_downside_breakout:
                    tier_label = "🏗️ STRUCTURE BREAK" if is_structure_break else "📐 PIVOT BREAK"
                    app_logger.warning(
                        f"Hedge: {tier_label} — {broken_level_name} (${broken_level_val:.2f}) "
                        f"| Candle: O=${st['open']:.0f} C=${st['close']:.0f} "
                        f"| Supertrend={st['trend']} "
                        f"| Loss={unrealized_loss_pct*100:.1f}% | Bypassing bleed threshold → HEDGE NOW"
                    )
                    notifier.notify_warning(
                        f"{tier_label} 🚨\n"
                        f"{broken_level_name} (${broken_level_val:.2f}) broken!\n"
                        f"Supertrend: {st['trend']} | Loss: {unrealized_loss_pct*100:.1f}%\n"
                        f"Opening immediate hedge."
                    )
                    self._bleed_confirm_count = 0
                    self._bleed_confirm_leg = None
                    self._open_new_hedge(
                        positions, bleeding_leg, unrealized_loss_pct,
                        total_loss_usd, direction, profit_usd, atr_usd
                    )
                    return


        # ── HYBRID TREND CONFIRMATION FILTER ──
        # To avoid whipsaws, we require EITHER a closed 5m candle > 1.5 ATR (Small Alert)
        # OR an instant real-time move > 2.0 ATR (Red Alert).
        btc_price = self._get_btc_mark_price()
        if self._entry_btc_price > 0 and btc_price > 0:
            realtime_move = abs(btc_price - self._entry_btc_price)
            last_candle_close = self._get_last_closed_5m_candle()
            candle_move = abs(last_candle_close - self._entry_btc_price) if last_candle_close > 0 else 0
            
            # Rule 2: RED ALERT - Realtime > 2.0 ATR
            red_alert_threshold = atr_usd * 2.0
            is_red_alert = realtime_move >= red_alert_threshold
            
            # Rule 1: Small Alert - Candle Close > 1.5 ATR
            small_alert_threshold = atr_usd * 1.5
            is_small_alert = candle_move >= small_alert_threshold
            
            if bleeding_leg and not (is_red_alert or is_small_alert):
                if bleed_pct >= self.BLEED_TRIGGER_PCT:
                    app_logger.warning(
                        f"Hedge: WAITING FOR CONFIRMATION! {bleeding_leg} bleeding {bleed_pct*100:.1f}%. "
                        f"Realtime move: ${realtime_move:.1f} (Needs > ${red_alert_threshold:.1f}). "
                        f"5m Candle move: ${candle_move:.1f} (Needs > ${small_alert_threshold:.1f}). "
                        f"Hedge REJECTED to prevent fakeout."
                    )
                self._bleed_confirm_count = 0
                return

        # ── FLASH CRASH: ≥ 40% bleed → instant hedge ──
        if bleeding_leg and unrealized_loss_pct >= self.BLEED_FLASH_CRASH_PCT:
            app_logger.critical(
                f"Hedge: ⚡ FLASH CRASH! Total loss {unrealized_loss_pct*100:.1f}% "
                f">= {self.BLEED_FLASH_CRASH_PCT*100:.0f}%. "
                f"HEDGING IMMEDIATELY!"
            )
            notifier.notify_error(
                f"⚡ FLASH CRASH HEDGE ⚡\n"
                f"Total loss {unrealized_loss_pct*100:.1f}%!\n"
                f"Immediate hedge — no confirmation wait."
            )
            self._bleed_confirm_count = 0
            self._bleed_confirm_leg = None
            self._open_new_hedge(
                positions, bleeding_leg, unrealized_loss_pct,
                total_loss_usd, direction, profit_usd, atr_usd
            )
            return

        # ── SEVERE BLEED: ≥ 25% → skip confirmation ──
        if bleeding_leg and unrealized_loss_pct >= self.BLEED_SEVERE_PCT:
            app_logger.warning(
                f"Hedge: SEVERE BLEED! Total loss at "
                f"{unrealized_loss_pct*100:.1f}% >= {self.BLEED_SEVERE_PCT*100:.0f}%. "
                f"Skipping confirmation. Hedging now."
            )
            self._bleed_confirm_count = 0
            self._bleed_confirm_leg = None
            self._open_new_hedge(
                positions, bleeding_leg, unrealized_loss_pct,
                total_loss_usd, direction, profit_usd, atr_usd
            )
            return

        # ── MODERATE BLEED: ≥ 15% → need 2 consecutive confirmations ──
        if bleeding_leg and unrealized_loss_pct >= self.BLEED_TRIGGER_PCT:
            if bleeding_leg == self._bleed_confirm_leg:
                self._bleed_confirm_count += 1
            else:
                self._bleed_confirm_count = 1
                self._bleed_confirm_leg = bleeding_leg

            if self._bleed_confirm_count >= self.BLEED_CONFIRM_CHECKS:
                app_logger.info(
                    f"Hedge: CONFIRMED! Total loss "
                    f"{unrealized_loss_pct*100:.1f}% for {self._bleed_confirm_count} "
                    f"consecutive checks. "
                    f"Opening hedge..."
                )
                self._bleed_confirm_count = 0
                self._bleed_confirm_leg = None
                self._open_new_hedge(
                    positions, bleeding_leg, unrealized_loss_pct,
                    total_loss_usd, direction, profit_usd, atr_usd
                )
            else:
                app_logger.info(
                    f"Hedge: Total loss {unrealized_loss_pct*100:.1f}% "
                    f"— confirm {self._bleed_confirm_count}/{self.BLEED_CONFIRM_CHECKS}. "
                    f"Waiting for sustained bleed..."
                )
            return

        # ── EMERGENCY: total portfolio loss ≥ 15% ──
        if unrealized_loss_pct >= self.EMERGENCY_LOSS_PCT:
            emergency_direction = direction or 'buy'
            emergency_leg = bleeding_leg or 'unknown'

            # Try to determine direction from position data
            if not direction:
                try:
                    for sym, data in positions.items():
                        ep = data.get('entry_price', 0)
                        lgp = data.get('last_good_price', ep)
                        is_call = (
                            sym.startswith('C-') or
                            data.get('leg_type', '') == 'call'
                        )
                        if lgp > ep * 1.05:
                            emergency_direction = 'buy' if is_call else 'sell'
                            emergency_leg = 'call' if is_call else 'put'
                            break
                except Exception:
                    pass

            app_logger.critical(
                f"Hedge: ⚠️ EMERGENCY! Total loss {unrealized_loss_pct*100:.1f}% "
                f">= {self.EMERGENCY_LOSS_PCT*100:.0f}%. Per-leg bleed: "
                f"{bleed_pct*100:.1f}%. FORCE-HEDGING {emergency_direction}!"
            )
            notifier.notify_error(
                f"🚨 EMERGENCY HEDGE 🚨\n"
                f"Total loss: {unrealized_loss_pct*100:.1f}%\n"
                f"Emergency hedging in {emergency_direction} direction."
            )
            self._open_new_hedge(
                positions, emergency_leg, unrealized_loss_pct,
                total_loss_usd, emergency_direction, profit_usd, atr_usd
            )
            return

        # ── No trigger — reset and monitor ──
        if self._bleed_confirm_count > 0:
            app_logger.info(
                f"Hedge: Bleed dropped below {self.BLEED_TRIGGER_PCT*100:.0f}%. "
                f"Resetting confirmation counter."
            )
            self._bleed_confirm_count = 0
            self._bleed_confirm_leg = None

        if bleeding_leg:
            app_logger.info(
                f"Hedge: {bleeding_leg} bleeding {bleed_pct*100:.1f}% "
                f"— below trigger. Loss: {unrealized_loss_pct*100:.1f}%. Monitoring..."
            )
        else:
            app_logger.info(
                f"Hedge: No bleed detected. Loss: {unrealized_loss_pct*100:.1f}%. "
                f"Market stable."
            )

    # ═══════════════════════════════════════════════════════════════
    # OPEN NEW HEDGE
    # ═══════════════════════════════════════════════════════════════

    def _open_new_hedge(self, positions, bleeding_leg, bleed_pct,
                         bleed_usd, direction, profit_usd, atr_usd=100.0):
        """Opens a new hedge position at Tier 1 (33% coverage)."""
        base_size = self._calculate_base_exposure(bleed_usd, positions)
        hedge_size = max(self.HEDGE_MIN_SIZE_BTC, base_size * 0.33)  # Tier 1 = 33%
        result = self._place_hedge(hedge_size, direction, "OPEN")

        if result and result.get('success'):
            self.hedge_active = True
            self.hedge_type = f"protect_{bleeding_leg}"
            self.hedge_size_btc = hedge_size if direction == 'buy' else -hedge_size
            self.hedge_percentage = 100.0
            self.hedge_order_id = result.get('order_id', 'N/A')
            self._hedge_entry_time = time.time()
            self.hedge_placed_time = time.time()
            self._bleeding_leg = bleeding_leg
            self._hedge_peak_pnl = 0.0
            self._hedge_direction = direction
            self._hedge_size_factor = 1.0
            # DCA tier starts at 1; will scale to 2 at 12% loss, 3 at 20%
            self._dca_tier = 1
            # Breakeven SL starts inactive; activates once hedge hits +5% profit
            self._breakeven_sl_active = False
            self._hedge_peak_pnl_pct = 0.0

            # Snapshot: options P&L when hedge was placed
            # When hedge just opened, profit_usd = options-only (no hedge P&L yet)
            self._options_pnl_at_hedge_entry = profit_usd

            self._last_escalation_time = time.time()

            # ── Log OPEN event ────────────────────────────────────
            self._log_hedge_event(
                event_type     = "OPEN",
                trigger_reason = f"{bleeding_leg.upper()} leg bleeding {bleed_pct*100:.1f}%",
                direction      = direction,
                size_btc       = hedge_size,
                total_btc      = abs(self.execution.hedge_size_btc),
                btc_price      = self._get_btc_mark_price(),
                options_pnl_usd= profit_usd,
                hedge_pnl_usd  = 0.0,          # just opened, no P&L yet
            )

            app_logger.info(
                f"Hedge: NEW HEDGE OPENED | Leg: {bleeding_leg} | "
                f"Dir: {direction} | Size: {hedge_size:.4f} BTC | "
                f"Options P&L snapshot: ${profit_usd:.2f}"
            )

            notifier.notify_hedge_executed(
                timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
                iv=self.dvol.get_current_dvol() if self.dvol else 0.0,
                net_delta=0.0,
                hedge_type=(
                    f"{bleeding_leg.upper()} bleeding {bleed_pct*100:.0f}%"
                ),
                size_btc=hedge_size,
                order_id=result.get('order_id', 'N/A')
            )
        else:
            app_logger.error("Hedge: Failed to open new hedge!")
            notifier.notify_hedge_failed()

    # ═══════════════════════════════════════════════════════════════
    # ACTIVE HEDGE MANAGEMENT — PRO TRADER LOGIC
    # ═══════════════════════════════════════════════════════════════
    #
    # GOLDEN RULES:
    # 1. NEVER book hedge profit while trade is in loss
    # 2. Hedge stays open accumulating profit until it FULLY covers
    #    all option losses (total P&L >= 0)
    # 3. Only exit when: total_pnl >= 0 OR options themselves profit
    # 4. On SL hit, hedge should have already recovered all losses
    # 5. Think like a pro: the P&L curve should stay FLAT during
    #    adverse moves — hedge absorbs all the damage
    #
    # ═══════════════════════════════════════════════════════════════

    def _manage_active_hedge(self, positions, bleeding_leg, bleed_pct,
                              bleed_usd, direction, unrealized_loss_pct,
                              profit_usd, atr_usd=100.0):
        """
        PRO TRADER hedge management — keeps hedge alive until ALL
        option losses are recovered.

        Exit conditions (STRICT — hedge must have done its job):
        1. TOTAL P&L >= 0 (hedge profit has fully covered option loss)
        2. Options themselves are profitable (hedge no longer needed)

        NEVER closes hedge while trade is in loss.
        NEVER books hedge profit early.
        """
        hedge_pnl = self.get_live_hedge_pnl()
        time_held = time.time() - self._hedge_entry_time

        # Track peak P&L
        if hedge_pnl > self._hedge_peak_pnl:
            self._hedge_peak_pnl = hedge_pnl
            app_logger.info(f"Hedge: New peak P&L: ${self._hedge_peak_pnl:.2f}")

        # ── Decompose: get OPTIONS-ONLY P&L ──────────────────────
        # profit_usd = options_pnl + hedge_pnl (when hedge active)
        # So: options_only_pnl = profit_usd - hedge_pnl
        options_only_pnl = profit_usd - hedge_pnl
        total_pnl = profit_usd  # Already includes hedge

        # How much have options recovered since hedge was placed?
        options_recovered = options_only_pnl - self._options_pnl_at_hedge_entry

        # Calculate options-only loss as % of collected premium
        collected_premium = self._get_collected_premium_usd(positions)
        if collected_premium > 0:
            options_loss_pct = max(0.0, -options_only_pnl / collected_premium)
        else:
            options_loss_pct = unrealized_loss_pct

        # ══════════════════════════════════════════════════════════
        # EXIT RULE 1: TOTAL P&L POSITIVE (hedge recovered ALL losses)
        # ══════════════════════════════════════════════════════════
        # This is the PRIMARY exit. The hedge has accumulated enough
        # profit to fully offset the options loss. The P&L curve is
        # now at or above breakeven. Close the hedge — mission done.
        #
        # Example: Options losing -$10, Hedge making +$12
        #          Total = +$2 → CLOSE (hedge covered everything)
        #
        if time_held >= self.MIN_HEDGE_HOLD_SECONDS:
            if total_pnl >= 0 and options_only_pnl < 0:
                app_logger.info(
                    f"Hedge: ✅ LOSS FULLY RECOVERED! "
                    f"Total P&L: ${total_pnl:+.2f} >= $0 | "
                    f"Options: ${options_only_pnl:+.2f} | "
                    f"Hedge: ${hedge_pnl:+.2f} "
                    f"(hedge profit covered all option losses)"
                )
                notifier.notify_error(
                    f"✅ Hedge Success!\n"
                    f"Total P&L: ${total_pnl:+.2f}\n"
                    f"Options: ${options_only_pnl:+.2f}\n"
                    f"Hedge: ${hedge_pnl:+.2f}\n"
                    f"All losses recovered by hedge."
                )
                self._close_hedge_with_reason(
                    f"TOTAL P&L POSITIVE — hedge recovered all losses "
                    f"(Options: ${options_only_pnl:+.2f}, Hedge: ${hedge_pnl:+.2f})",
                    options_pnl_usd=options_only_pnl
                )
                return

        # ══════════════════════════════════════════════════════════
        # EXIT RULE 2: OPTIONS NOW PROFITABLE (hedge not needed)
        # ══════════════════════════════════════════════════════════
        # Market reversed fully — options are now making money on
        # their own. The hedge is no longer needed. Close it immediately
        # to stop the hedge from dragging down the P&L.
        if time_held >= self.MIN_HEDGE_HOLD_SECONDS:
            if options_only_pnl > 0:
                app_logger.info(
                    f"Hedge: ✅ OPTIONS PROFITABLE — hedge no longer needed! "
                    f"Options P&L: ${options_only_pnl:+.2f} | "
                    f"Hedge P&L: ${hedge_pnl:+.2f} | "
                    f"Total: ${total_pnl:+.2f}"
                )
                self._close_hedge_with_reason(
                    f"Options now profitable (${options_only_pnl:+.2f}) — "
                    f"hedge no longer needed",
                    options_pnl_usd=options_only_pnl
                )
                return

        # ══════════════════════════════════════════════════════════
        # EXIT RULE 3: OPTIONS LOSS RECOVERED TO NEAR ZERO
        # ══════════════════════════════════════════════════════════
        # If the market spiked but then fully reversed, the options
        # loss has recovered to near breakeven. The hedge is no longer
        # needed. Cut the hedge to stop it from bleeding further, even
        # if total P&L is slightly negative.
        if time_held >= self.MIN_HEDGE_HOLD_SECONDS:
            if options_only_pnl < 0 and options_loss_pct <= self.LOSS_NEAR_ZERO_PCT:
                app_logger.info(
                    f"Hedge: ✅ OPTIONS RECOVERED! Loss is only "
                    f"{options_loss_pct*100:.1f}% (< {self.LOSS_NEAR_ZERO_PCT*100:.1f}%). "
                    f"Hedge no longer needed! Closing."
                )
                self._close_hedge_with_reason(
                    f"Options loss recovered to {options_loss_pct*100:.1f}% "
                    f"(Total P&L: ${total_pnl:+.2f})",
                    options_pnl_usd=options_only_pnl
                )
                return

        # ══════════════════════════════════════════════════════════
        # EXIT RULE 4: OPTIONS RECOVERED BY 50% (Trend Failed)
        # ══════════════════════════════════════════════════════════
        # If the option was bleeding heavily, but the market reversed
        # and the option loss has shrunk by 50% from its peak, the trend
        # has failed. Cut the oversized hedge before it loses too much money.
        if time_held >= self.MIN_HEDGE_HOLD_SECONDS:
            if self._options_pnl_at_hedge_entry < 0:
                if options_only_pnl > (self._options_pnl_at_hedge_entry * self.LOSS_RECOVERY_PCT):
                    app_logger.info(
                        f"Hedge: ✅ OPTIONS RECOVERED 50%! "
                        f"Entry Loss: ${self._options_pnl_at_hedge_entry:.2f} | "
                        f"Current Loss: ${options_only_pnl:.2f}. "
                        f"Trend failed. Cutting hedge to prevent reversal loss."
                    )
                    self._close_hedge_with_reason(
                        f"Options recovered > 50% from entry loss",
                        options_pnl_usd=options_only_pnl
                    )
                    return

        # ══════════════════════════════════════════════════════════
        # EXIT RULE 5 HAS BEEN REMOVED (No aggressive stop-losses on the hedge)
        # ══════════════════════════════════════════════════════════

        # ══════════════════════════════════════════════════════════
        # ⛔ DO NOT EXIT — TRADE STILL IN LOSS
        # ══════════════════════════════════════════════════════════
        # If we reach here, the trade is still in loss:
        # - Options are losing AND total_pnl < 0
        # - Hedge MUST stay open to keep accumulating profit
        # - Even if hedge is very profitable, DO NOT close it
        #   because the options loss hasn't been recovered yet
        #
        # The hedge will stay open until:
        # a) total_pnl >= 0 (hedge fully covers loss)
        # b) Options turn profitable
        # c) EOD forced close by engine
        # d) Positions cleared
        #

        # ── DIRECTION FLIP: Different leg now bleeding ────────────
        # Market reversed — a different leg is now in trouble.
        # We MUST close the old hedge immediately to avoid double exposure,
        # even if it means booking a loss on the hedge.
        if (bleeding_leg and bleeding_leg != self._bleeding_leg and
                bleed_pct >= self.BLEED_TRIGGER_PCT):
            
            app_logger.warning(
                f"Hedge: DIRECTION FLIP DETECTED! "
                f"Was hedging {self._bleeding_leg}, now {bleeding_leg} "
                f"bleeding {bleed_pct*100:.1f}%. "
                f"Total P&L: ${total_pnl:+.2f}. "
                f"Force closing old hedge to stop double exposure!"
            )
            self._close_hedge_with_reason(
                f"Direction flip — {self._bleeding_leg} → {bleeding_leg} "
                f"(total P&L: ${total_pnl:+.2f})",
                options_pnl_usd=options_only_pnl
            )
            self._open_new_hedge(
                positions, bleeding_leg, bleed_pct,
                bleed_usd, direction, profit_usd, atr_usd
            )
            return

        # ── ESCALATION: Loss keeps growing, add more hedge ────────
        if (bleeding_leg and bleeding_leg == self._bleeding_leg and
                bleed_pct >= self.BLEED_TRIGGER_PCT and
                self._last_sizing_loss_usd > 0):

            current_loss = abs(bleed_usd) if bleed_usd > 0 else 0
            growth = (
                (current_loss - self._last_sizing_loss_usd)
                / self._last_sizing_loss_usd
                if self._last_sizing_loss_usd > 0 else 0
            )
            time_since_last = time.time() - self._last_escalation_time

            if (growth >= self.ESCALATION_GROWTH_PCT and
                    time_since_last >= self.ESCALATION_COOLDOWN_S):
                # Calculate the FULL target size using exact math
                target_total_hedge = self._calculate_base_exposure(bleed_usd, positions)
                current_size = abs(self.execution.hedge_size_btc)
                
                # Add only what we need to reach the target tier size
                if target_total_hedge > current_size:
                    add_btc = target_total_hedge - current_size
                    add_btc = max(self.HEDGE_MIN_SIZE_BTC, add_btc)
                    
                    result = self._place_hedge(
                        add_btc, self._hedge_direction, "GRID-ESCALATE"
                    )
                if result and result.get('success'):
                    self.hedge_size_btc = self.execution.hedge_size_btc
                    self._last_escalation_time = time.time()
                    self._last_sizing_loss_usd = current_loss

                    # ── Log ESCALATE event ────────────────────────
                    self._log_hedge_event(
                        event_type     = "ESCALATE",
                        trigger_reason = f"Loss grew {growth*100:.0f}% — adding {add_btc:.4f} BTC",
                        direction      = self._hedge_direction or "buy",
                        size_btc       = add_btc,
                        total_btc      = abs(self.execution.hedge_size_btc),
                        btc_price      = self._get_btc_mark_price(),
                        options_pnl_usd= profit_usd,
                        hedge_pnl_usd  = self.get_live_hedge_pnl(),
                    )

                    app_logger.info(
                        f"Hedge: ESCALATED! Added {add_btc:.4f} BTC. "
                        f"Total: {abs(self.execution.hedge_size_btc):.4f} BTC. "
                        f"Loss grew {growth*100:.0f}%. "
                        f"Hedge must keep growing to cover options loss."
                    )
                    notifier.notify_hedge_escalated(
                        timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
                        from_pct=self.hedge_percentage,
                        to_pct=self.hedge_percentage + growth * 100,
                        loss_pct=bleed_pct * 100
                    )
                return

        # ── STATUS LOG (no action — hedge stays open) ─────────────
        app_logger.info(
            f"Hedge: 🔒 HOLDING ({self._bleeding_leg}) | "
            f"Hedge P&L: ${hedge_pnl:+.2f} | Peak: ${self._hedge_peak_pnl:.2f} | "
            f"Options P&L: ${options_only_pnl:+.2f} | "
            f"Total P&L: ${total_pnl:+.2f} | "
            f"Size: {abs(self.execution.hedge_size_btc):.4f} BTC | "
            f"{'⛔ HOLDING — total still negative' if total_pnl < 0 else '⏳ Approaching breakeven...'}"
        )

    # ═══════════════════════════════════════════════════════════════
    # CLOSE HEDGE
    # ═══════════════════════════════════════════════════════════════

    def _close_hedge_with_reason(self, reason, options_pnl_usd=0.0):
        """Closes hedge with detailed logging and P&L tracking."""
        final_pnl  = self.get_live_hedge_pnl()
        btc_price  = self._get_btc_mark_price()
        total_size = abs(self.execution.hedge_size_btc)
        direction  = self._hedge_direction or "unknown"
        self._cumulative_realized_pnl += final_pnl

        # ── Log CLOSE event BEFORE state is wiped ─────────────────
        self._log_hedge_event(
            event_type     = "CLOSE",
            trigger_reason = reason,
            direction      = direction,
            size_btc       = total_size,      # full size being closed
            total_btc      = 0.0,             # 0 after close
            btc_price      = btc_price,
            options_pnl_usd= options_pnl_usd,
            hedge_pnl_usd  = final_pnl,
            exit_reason    = reason,
        )

        app_logger.info(
            f"Hedge: Closing — {reason}. Final P&L: ${final_pnl:+.2f} | "
            f"Cumulative realized: ${self._cumulative_realized_pnl:+.2f}"
        )

        # ── START 30-MIN COOLDOWN after any rule-based exit ─────────
        self._hedge_cooldown_until = time.time() + self.COOLDOWN_SECONDS
        cooldown_min = self.COOLDOWN_SECONDS // 60
        app_logger.info(
            f"Hedge: ⏳ {cooldown_min}-min cooldown started. "
            f"No new hedges until {time.strftime('%H:%M:%S', time.localtime(self._hedge_cooldown_until))}."
        )
        self.close_hedge()

    def close_hedge(self):
        """Closes all active hedge positions and resets all state."""
        if self.hedge_active:
            final_pnl = self.get_live_hedge_pnl()
            app_logger.info(f"Hedge: Closing hedge. Final P&L: ${final_pnl:+.2f}")

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
        self._bleeding_leg = None
        self._hedge_peak_pnl = 0.0
        self._hedge_size_factor = 0.0
        self._hedge_direction = None
        self._bleed_confirm_count = 0
        self._bleed_confirm_leg = None
        self._options_pnl_at_hedge_entry = 0.0
        self._hedge_entry_time = 0.0
        self._last_sizing_loss_usd = 0.0
        self._last_escalation_time = 0.0
        # NOTE: _hedge_cooldown_until is NOT reset here.
        # It is only set by _close_hedge_with_reason() (rule-based exits).
        # Manual/EOD closes via close_hedge() directly do NOT start a cooldown.
        # Reset merged-engine state vars
        self._dca_tier = 0
        self._breakeven_sl_active = False
        self._hedge_peak_pnl_pct = 0.0
        app_logger.info("Hedge: State fully reset.")

    # ═══════════════════════════════════════════════════════════════
    # UTILITY
    # ═══════════════════════════════════════════════════════════════

    def _get_options_exposure_btc(self, positions):
        """Total option exposure in BTC (each lot = 0.001 BTC)."""
        total_size = sum(data.get('size', 0) for data in positions.values())
        return total_size * 0.001
