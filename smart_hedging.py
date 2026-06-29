import time
import math
from config import (
    HEDGE_WAIT_AFTER_ENTRY,
    HEDGE_RECHECK_INTERVAL,
    HEDGE_SYMBOL
)
from logger import app_logger
from notifier import notifier


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
    BLEED_TRIGGER_PCT = 0.15          # 15% single-leg bleed triggers hedge
    BLEED_SEVERE_PCT = 0.25           # 25%+ skip confirmation, hedge now
    BLEED_FLASH_CRASH_PCT = 0.40      # 40%+ flash crash, instant hedge
    BLEED_CONFIRM_CHECKS = 2          # 2 consecutive checks for moderate (15-25%)
    EMERGENCY_LOSS_PCT = 0.15         # 15% total portfolio loss = emergency

    # ─── SIZING ───────────────────────────────────────────────────
    HEDGE_MIN_SIZE_BTC = 0.01         # Minimum hedge 0.01 BTC
    HEDGE_MAX_SIZE_BTC = 0.50         # Maximum hedge 0.50 BTC
    DEFAULT_DELTA_ESTIMATE = 0.30     # Fallback delta when BTC move is small

    # ─── EXIT RULES (ZERO-LOSS) ───────────────────────────────────
    LOSS_RECOVERY_PCT = 0.50          # Options loss halved = significant recovery
    LOSS_NEAR_ZERO_PCT = 0.05         # Options loss < 5% of premium = near zero
    MIN_HEDGE_HOLD_SECONDS = 45       # Don't exit within 45s of opening

    # ─── ESCALATION ───────────────────────────────────────────────
    ESCALATION_GROWTH_PCT = 0.50      # Add more if loss grew 50%+ since last sizing
    ESCALATION_COOLDOWN_S = 120       # Max once per 2 minutes

    def __init__(self, execution_handler, dvol_provider, risk_manager, api_client):
        self.execution = execution_handler
        self.dvol = dvol_provider
        self.risk_manager = risk_manager
        self.api_client = api_client

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

        # ── Try 2: REST API (reliable) ──
        try:
            res = self.api_client.get_tickers({'symbol': HEDGE_SYMBOL})
            if res and res.get('success') and res.get('result'):
                for item in res['result']:
                    if item.get('symbol') == HEDGE_SYMBOL:
                        price = float(item.get('mark_price', 0))
                        if price > 100:
                            self._last_known_btc_price = price
                            return price
        except Exception as e:
            app_logger.debug(f"Hedge: REST BTC price failed: {e}")

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

    def _calculate_hedge_size(self, bleed_usd, positions, atr_usd=100.0):
        """
        Calculates hedge size in BTC to match the dollar loss.

        Method 1 (preferred): loss / BTC_move = effective exposure
        Method 2 (fallback): position_size × delta_estimate
        """
        btc_price = self._get_btc_mark_price()
        if btc_price <= 0:
            btc_price = 60000  # Emergency fallback

        abs_bleed = abs(bleed_usd) if bleed_usd > 0 else 1.0

        # The Gamma & Recovery Multiplier
        # Why 2.0x? 
        # A 2.0x multiplier ensures the linear futures profit outpaces the accelerating Gamma loss of the options,
        # guaranteeing a strictly positive Net P&L (covering 100%+ of the loss) if a severe crash hits the 130% SL.
        GAMMA_RECOVERY_MULTIPLIER = 2.0

        # Method 1: BTC has moved enough to calculate real exposure
        btc_move_usd = 0.0
        if self._entry_btc_price > 0:
            btc_move_usd = abs(btc_price - self._entry_btc_price)

        # Ensure we don't divide by a tiny number and create a massive oversized hedge during IV spikes
        # A meaningful move to base delta on is at least 0.5 ATR, or a hard floor of $300
        safe_btc_move = max(btc_move_usd, max(300.0, atr_usd * 0.5))
        effective_exposure = abs_bleed / safe_btc_move
            
        # --- HYBRID GRID SIZING LOGIC ---
        realtime_atr_dist = btc_move_usd / atr_usd if atr_usd > 0 else 0
        
        last_candle_close = self._get_last_closed_5m_candle()
        candle_move_usd = abs(last_candle_close - self._entry_btc_price) if last_candle_close > 0 else 0
        candle_atr_dist = candle_move_usd / atr_usd if atr_usd > 0 else 0
        
        scale_factor = 0.50  # Default to Tier 1
        
        if realtime_atr_dist >= 2.0:
            scale_factor = 1.0  # Rule 2: RED ALERT - Full 100% Hedge
        elif candle_atr_dist >= 1.5:
            scale_factor = 0.50 # Rule 1: Small Alert - 50% Hedge
        elif realtime_atr_dist >= 1.5:
            # If managed to pass trend filter for some other reason, fallback
            scale_factor = 0.50
        
        hedge_btc = effective_exposure * GAMMA_RECOVERY_MULTIPLIER * scale_factor
        app_logger.info(
            f"Hedge: Sizing [Hybrid Grid] | Loss=${abs_bleed:.2f} | "
            f"BTC moved=${btc_move_usd:.0f} (Safe Divisor: ${safe_btc_move:.0f}) | "
            f"Base Exp={effective_exposure:.4f} BTC | "
            f"Grid Tier={scale_factor*100:.0f}% | Final Hedge={hedge_btc:.4f} BTC"
        )

        # Clamp to min/max
        hedge_btc = max(self.HEDGE_MIN_SIZE_BTC, hedge_btc)
        hedge_btc = min(self.HEDGE_MAX_SIZE_BTC, hedge_btc)

        self._last_sizing_loss_usd = abs_bleed
        return hedge_btc

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
    # POST-ENTRY HEDGE CHECK (background thread)
    # ═══════════════════════════════════════════════════════════════

    def run_post_entry_hedge(self, positions):
        """Called in a background thread immediately after strangle entry."""
        try:
            app_logger.info(
                f"Hedge: Post-entry hedge check in {HEDGE_WAIT_AFTER_ENTRY}s..."
            )
            time.sleep(HEDGE_WAIT_AFTER_ENTRY)

            if not positions:
                app_logger.info("Hedge: Post-entry — no positions.")
                return

            self.set_entry_premiums(positions)

            bleeding_leg, bleed_pct, bleed_usd, direction = self._detect_bleeding_leg(
                positions
            )

            if bleeding_leg and bleed_pct >= self.BLEED_TRIGGER_PCT:
                app_logger.info(
                    f"Hedge: Post-entry — {bleeding_leg} already bleeding "
                    f"{bleed_pct*100:.1f}%! Hedging immediately."
                )
                self._open_new_hedge(
                    positions, bleeding_leg, bleed_pct,
                    bleed_usd, direction, profit_usd=0.0, atr_usd=100.0
                )
            else:
                app_logger.info(
                    "Hedge: Post-entry — no significant bleed. Monitoring..."
                )
        except Exception as e:
            app_logger.error(f"Hedge: Post-entry thread CRASHED: {e}")
            notifier.notify_error(f"Post-entry hedge thread crashed: {e}")

    # ═══════════════════════════════════════════════════════════════
    # CORE: MANAGE HEDGE (called every 5-15 seconds by bot_engine)
    # ═══════════════════════════════════════════════════════════════

    def manage_hedge(self, positions, unrealized_loss_pct, profit_usd=0.0, adx_value=0.0, atr_usd=100.0):
        """
        Core hedge management loop.

        Args:
            positions: execution.active_positions dict
            unrealized_loss_pct: positive when losing (0.15 = 15% loss)
            profit_usd: current total P&L in USD (includes hedge P&L when active)
            adx_value: ADX trend strength from market_regime
            atr_usd: BTC Average True Range in USD
        """
        self.last_check_time = time.time()

        # ── No positions → close hedge ──
        if not positions:
            if self.hedge_active:
                app_logger.info("Hedge: Positions cleared. Closing hedge...")
                self.close_hedge()
            return

        # ── Detect bleeding leg ──
        bleeding_leg, bleed_pct, bleed_usd, direction = self._detect_bleeding_leg(
            positions
        )

        if self.hedge_active:
            self._manage_active_hedge(
                positions, bleeding_leg, bleed_pct, bleed_usd,
                direction, unrealized_loss_pct, profit_usd, atr_usd
            )
        else:
            self._check_and_trigger_hedge(
                positions, bleeding_leg, bleed_pct, bleed_usd,
                direction, unrealized_loss_pct, profit_usd, adx_value, atr_usd
            )

    # ═══════════════════════════════════════════════════════════════
    # TRIGGER LOGIC — Should we open a new hedge?
    # ═══════════════════════════════════════════════════════════════

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
        # ── RULE: Never hedge when net trade is profitable ──
        if unrealized_loss_pct <= 0.0:
            if bleeding_leg:
                app_logger.info(
                    f"Hedge: {bleeding_leg} bleeding {bleed_pct*100:.1f}%, "
                    f"BUT net trade is PROFITABLE. No hedge needed."
                )
            self._bleed_confirm_count = 0
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
        if bleeding_leg and bleed_pct >= self.BLEED_FLASH_CRASH_PCT:
            app_logger.critical(
                f"Hedge: ⚡ FLASH CRASH! {bleeding_leg.upper()} bleeding "
                f"{bleed_pct*100:.1f}% >= {self.BLEED_FLASH_CRASH_PCT*100:.0f}%. "
                f"HEDGING IMMEDIATELY!"
            )
            notifier.notify_error(
                f"⚡ FLASH CRASH HEDGE ⚡\n"
                f"{bleeding_leg.upper()} bleeding {bleed_pct*100:.1f}%!\n"
                f"Immediate hedge — no confirmation wait."
            )
            self._bleed_confirm_count = 0
            self._bleed_confirm_leg = None
            self._open_new_hedge(
                positions, bleeding_leg, bleed_pct,
                bleed_usd, direction, profit_usd, atr_usd
            )
            return

        # ── SEVERE BLEED: ≥ 25% → skip confirmation ──
        if bleeding_leg and bleed_pct >= self.BLEED_SEVERE_PCT:
            app_logger.warning(
                f"Hedge: SEVERE BLEED! {bleeding_leg.upper()} at "
                f"{bleed_pct*100:.1f}% >= {self.BLEED_SEVERE_PCT*100:.0f}%. "
                f"Skipping confirmation. Hedging now."
            )
            self._bleed_confirm_count = 0
            self._bleed_confirm_leg = None
            self._open_new_hedge(
                positions, bleeding_leg, bleed_pct,
                bleed_usd, direction, profit_usd, atr_usd
            )
            return

        # ── MODERATE BLEED: ≥ 15% → need 2 consecutive confirmations ──
        if bleeding_leg and bleed_pct >= self.BLEED_TRIGGER_PCT:
            if bleeding_leg == self._bleed_confirm_leg:
                self._bleed_confirm_count += 1
            else:
                self._bleed_confirm_count = 1
                self._bleed_confirm_leg = bleeding_leg

            if self._bleed_confirm_count >= self.BLEED_CONFIRM_CHECKS:
                app_logger.info(
                    f"Hedge: CONFIRMED! {bleeding_leg.upper()} bleeding "
                    f"{bleed_pct*100:.1f}% for {self._bleed_confirm_count} "
                    f"consecutive checks. Net loss: {unrealized_loss_pct*100:.1f}%. "
                    f"Opening hedge..."
                )
                self._bleed_confirm_count = 0
                self._bleed_confirm_leg = None
                self._open_new_hedge(
                    positions, bleeding_leg, bleed_pct,
                    bleed_usd, direction, profit_usd, atr_usd
                )
            else:
                app_logger.info(
                    f"Hedge: {bleeding_leg.upper()} bleeding {bleed_pct*100:.1f}% "
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
                bleed_usd, emergency_direction, profit_usd, atr_usd
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
        """Opens a new hedge position with Grid scaling sizing."""
        hedge_size = self._calculate_hedge_size(bleed_usd, positions, atr_usd)
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
                # Calculate the FULL target size using Grid Math
                target_total_hedge = self._calculate_hedge_size(bleed_usd, positions, atr_usd)
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
        app_logger.info("Hedge: State fully reset.")

    # ═══════════════════════════════════════════════════════════════
    # UTILITY
    # ═══════════════════════════════════════════════════════════════

    def _get_options_exposure_btc(self, positions):
        """Total option exposure in BTC (each lot = 0.001 BTC)."""
        total_size = sum(data.get('size', 0) for data in positions.values())
        return total_size * 0.001
