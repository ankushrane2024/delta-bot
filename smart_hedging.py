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
    Delta-Neutral Smart Hedging Engine for the Delta BTC Options Bot.

    Core Principle:
    ---------------
    We sell a SHORT STRANGLE (short call + short put).
    When BTC moves strongly in one direction, one leg bleeds.
    The hedge BUYS or SELLS BTC perpetual futures to offset the delta exposure,
    so that the losing option leg is partially offset by a futures profit.

    Key Fixes (v3 rewrite):
    -----------------------
    1. Hedge direction is determined BOTH by live greeks AND by premium-change
       direction as a fallback (prevents wrong-direction hedge when API delta = 0).
    2. Weighted Average Entry Price is tracked precisely across multiple hedge
       fills so PnL display is always correct.
    3. Minimum hold time before unwind prevents flapping in volatile markets.
    4. Continuous rebalancing keeps hedge size at exact 1-to-1 delta neutrality.
    5. Hedge stop-loss closes position when hedge itself bleeds too much.
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
        self.hedge_placed_time = 0.0    # When the hedge was first placed (for min-hold)
        self.sl_tightened = False
        self.hedge_stopped_out = False

        # --- Precise PnL tracking ---
        self.hedge_avg_entry_price = 0.0   # Weighted average entry price (signed)
        self.hedge_total_cost_btc = 0.0    # Total absolute BTC transacted

        # --- Positions cache for premium-direction fallback ---
        self._entry_premiums = {}          # {symbol: entry_price_per_lot}

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
            "hedge_pnl_usd": round(self.get_live_hedge_pnl(), 2)
        }

    # ─────────────────────────────────────────────────────────────────
    # PNL CALCULATION (uses weighted average entry, never overwrites)
    # ─────────────────────────────────────────────────────────────────

    def get_live_hedge_pnl(self):
        """
        Calculates the live PnL of the current hedge position using
        the WEIGHTED AVERAGE ENTRY PRICE across all fills.

        FIX: Previously, hedge_entry_price was overwritten on each rebalance,
        causing wrong PnL. Now we track total cost / total size.
        """
        if not self.hedge_active or abs(self.execution.hedge_size_btc) < 0.0001:
            return 0.0
        if self.hedge_avg_entry_price <= 0:
            return 0.0

        # Get current BTC mark price
        mark_price = self._get_btc_mark_price()
        if mark_price <= 0:
            return 0.0

        size = self.execution.hedge_size_btc  # Signed
        avg_entry = self.hedge_avg_entry_price

        # Short hedge (size < 0): profit when price drops
        # Long hedge (size > 0): profit when price rises
        pnl = (avg_entry - mark_price) * abs(size) if size < 0 else (mark_price - avg_entry) * size
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
    # ENTRY PREMIUM CACHE (for direction detection fallback)
    # ─────────────────────────────────────────────────────────────────

    def set_entry_premiums(self, positions):
        """
        Call this immediately after a strangle is entered.
        Caches entry premiums per leg so we can detect which leg is losing
        even when API delta data is 0 or stale.
        """
        self._entry_premiums = {}
        for sym, data in positions.items():
            self._entry_premiums[sym] = data.get('entry_price', 0)
        app_logger.info(f"Hedge: Cached entry premiums: {self._entry_premiums}")

    # ─────────────────────────────────────────────────────────────────
    # DELTA CALCULATION
    # ─────────────────────────────────────────────────────────────────

    def _fetch_net_delta_and_gamma(self, positions):
        """
        Calculates NET portfolio delta in BTC for the short strangle.

        For SHORT positions:
          - Short call delta contribution = -call_delta_raw  (positive delta → short call is negative)
          - Short put delta contribution  = -put_delta_raw   (negative delta → short put is positive)

        Returns (net_delta_btc, total_gamma_btc, greeks_are_reliable)
        where greeks_are_reliable=True only if at least one real, non-zero delta was read.
        """
        net_delta_btc = 0.0
        total_gamma_btc = 0.0
        reliable_legs = 0
        zero_delta_legs = 0

        for sym, data in positions.items():
            ws_data = self.api_client.get_realtime_ticker(sym)
            d = None
            g = 0.0

            if ws_data:
                greeks = ws_data.get('greeks') or {}
                delta_raw = greeks.get('delta')
                gamma_raw = greeks.get('gamma')

                if delta_raw is not None:
                    d_candidate = float(delta_raw)
                    if abs(d_candidate) > 0.001:
                        d = d_candidate
                        g = float(gamma_raw or 0)
                        # Cache this good value
                        data['last_known_delta'] = d
                        data['last_known_gamma'] = g
                        reliable_legs += 1
                    else:
                        # API returned essentially zero → probably stale. Try cached.
                        zero_delta_legs += 1
                        cached_d = data.get('last_known_delta')
                        if cached_d is not None and abs(cached_d) > 0.001:
                            d = cached_d
                            g = data.get('last_known_gamma', 0)
                            app_logger.warning(
                                f"Hedge: Delta=0 from API for {sym}. Using cached delta={d:.4f}"
                            )
                        else:
                            app_logger.warning(
                                f"Hedge: Delta=0 from API for {sym} and no cache. Delta contribution ignored."
                            )
                else:
                    # No delta key at all → use cache
                    cached_d = data.get('last_known_delta')
                    if cached_d is not None and abs(cached_d) > 0.001:
                        d = cached_d
                        g = data.get('last_known_gamma', 0)
                        app_logger.warning(
                            f"Hedge: No greeks in WS tick for {sym}. Using cached delta={d:.4f}"
                        )
            else:
                # No WS data at all
                cached_d = data.get('last_known_delta')
                if cached_d is not None and abs(cached_d) > 0.001:
                    d = cached_d
                    g = data.get('last_known_gamma', 0)
                    app_logger.warning(
                        f"Hedge: No WS data for {sym}. Using cached delta={d:.4f}"
                    )

            if d is not None:
                # Invert because positions are SHORT
                net_delta_btc -= d * data['size'] * 0.001
                total_gamma_btc -= g * data['size'] * 0.001

        greeks_reliable = reliable_legs > 0 and zero_delta_legs < len(positions)

        app_logger.info(
            f"Hedge: Delta calc: net_delta={net_delta_btc:+.4f} BTC | "
            f"reliable_legs={reliable_legs} | zero_delta_legs={zero_delta_legs}"
        )
        return net_delta_btc, total_gamma_btc, greeks_reliable

    def _detect_direction_from_premium(self, positions):
        """
        FALLBACK: When API delta is unreliable (all zeros), determine hedge direction
        from which leg is losing money (i.e., which leg's current premium is above entry).

        - If PUT leg premium > PUT entry premium: BTC went DOWN → SELL BTC futures (go short)
        - If CALL leg premium > CALL entry premium: BTC went UP → BUY BTC futures (go long)

        Returns: ('sell', put_excess_usd) or ('buy', call_excess_usd) or (None, 0)
        """
        if not self._entry_premiums:
            return None, 0.0

        call_excess = 0.0
        put_excess = 0.0

        for sym, data in positions.items():
            entry = self._entry_premiums.get(sym, 0)
            if entry <= 0:
                continue

            ws_data = self.api_client.get_realtime_ticker(sym)
            if ws_data and 'mark_price' in ws_data:
                current = float(ws_data['mark_price'])
                excess = current - entry  # Positive = option price rose = losing leg
                is_call = sym.startswith('C-') or data.get('leg_type', '') == 'call'
                if is_call:
                    call_excess += excess
                else:
                    put_excess += excess

        app_logger.info(f"Hedge: Premium direction fallback: call_excess={call_excess:.2f}, put_excess={put_excess:.2f}")

        if put_excess > 0 and put_excess > call_excess:
            app_logger.info("Hedge: Put leg bleeding (BTC went DOWN) → direction: SELL BTC futures")
            return 'sell', put_excess
        elif call_excess > 0 and call_excess > put_excess:
            app_logger.info("Hedge: Call leg bleeding (BTC went UP) → direction: BUY BTC futures")
            return 'buy', call_excess
        else:
            app_logger.info("Hedge: Cannot determine direction from premium (balanced or no data)")
            return None, 0.0

    def _get_options_exposure_btc(self, positions):
        """Total option exposure in BTC (each lot = 0.001 BTC)."""
        total_size = sum(data.get('size', 0) for data in positions.values())
        return total_size * 0.001

    # ─────────────────────────────────────────────────────────────────
    # HEDGE EXECUTION (with weighted avg entry tracking)
    # ─────────────────────────────────────────────────────────────────

    def _place_hedge(self, size_btc, direction, label="HEDGE"):
        """
        Places a hedge order and updates the weighted average entry price.

        FIX: Previously, hedge_entry_price was overwritten on each order,
        making the PnL calculation wrong. Now we maintain a running weighted average.
        """
        result = self.execution.place_hedge_order(abs(size_btc), direction)

        if result and result.get('success'):
            fill_price = result.get('fill_price', 0)

            # Update weighted average entry price
            prev_abs_size = abs(self.hedge_size_btc)
            new_abs_size = abs(size_btc)
            total_abs = prev_abs_size + new_abs_size

            if total_abs > 0:
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
    # POST-ENTRY INITIAL HEDGE
    # ─────────────────────────────────────────────────────────────────

    def run_post_entry_hedge(self, positions):
        """
        Called in a background thread immediately after strangle entry.
        Waits HEDGE_WAIT_AFTER_ENTRY seconds, then checks if initial hedge is needed.
        """
        app_logger.info(f"Hedge: Scheduling post-entry check in {HEDGE_WAIT_AFTER_ENTRY}s...")
        time.sleep(HEDGE_WAIT_AFTER_ENTRY)

        if not positions:
            app_logger.info("Hedge: Post-entry check cancelled — no active positions.")
            return

        self.set_entry_premiums(positions)
        current_dvol = self.dvol.get_current_dvol()
        net_delta_btc, _, greeks_reliable = self._fetch_net_delta_and_gamma(positions)
        app_logger.info(
            f"Hedge: Post-entry check — DVOL: {current_dvol:.2f}% | "
            f"Net delta: {net_delta_btc:+.4f} BTC | Greeks reliable: {greeks_reliable}"
        )
        self._check_and_trigger_initial_hedge(net_delta_btc, greeks_reliable, current_dvol, positions)

    def _check_and_trigger_initial_hedge(self, net_delta_btc, greeks_reliable, dvol, positions):
        """Decide whether to place an initial hedge based on DVOL tier and net delta."""
        if dvol < 45.0:
            trigger = HEDGE_IV_THRESHOLDS['low']['delta_trigger']
            tier = "Low (<45%)"
        elif dvol <= 55.0:
            trigger = HEDGE_IV_THRESHOLDS['mid']['delta_trigger']
            tier = "Mid (45-55%)"
        else:
            trigger = HEDGE_IV_THRESHOLDS['high']['delta_trigger']
            tier = "High (>55%)"

        leg_size = list(positions.values())[0]['size'] if positions else 1
        raw_net_delta = abs(net_delta_btc) / (leg_size * 0.001) if leg_size > 0 else 0.0

        app_logger.info(
            f"Hedge: DVOL tier: {tier} | trigger: {trigger:.2f} | "
            f"raw_delta: {raw_net_delta:.4f} | greeks_reliable: {greeks_reliable}"
        )

        if raw_net_delta > trigger:
            self._execute_initial_hedge(net_delta_btc, greeks_reliable, positions)
        else:
            app_logger.info(
                f"Hedge: No initial hedge needed. raw_delta {raw_net_delta:.4f} <= trigger {trigger:.2f}"
            )

    def _execute_initial_hedge(self, net_delta_btc, greeks_reliable, positions):
        """Place the initial 1-to-1 delta hedge."""
        hedge_size = abs(net_delta_btc)
        direction = 'sell' if net_delta_btc > 0 else 'buy'

        # Safety: if greeks are unreliable, also check premium direction
        if not greeks_reliable or hedge_size < 0.001:
            fallback_dir, excess = self._detect_direction_from_premium(positions)
            if fallback_dir:
                direction = fallback_dir
                # Use exposure-based size if delta gives tiny/wrong size
                if hedge_size < 0.001:
                    exposure = self._get_options_exposure_btc(positions)
                    hedge_size = exposure * 0.5  # 50% of full exposure as conservative start
                    app_logger.warning(
                        f"Hedge: Using premium-direction fallback. size={hedge_size:.4f} BTC, dir={direction}"
                    )

        if hedge_size <= 0.001:
            app_logger.warning("Hedge: Hedge size too small, skipping initial hedge.")
            return

        result = self._place_hedge(hedge_size, direction, "INITIAL")
        if result and result.get('success'):
            self.hedge_active = True
            self.hedge_type = "oneshot_1to1"
            self.hedge_size_btc = hedge_size if direction == 'buy' else -hedge_size
            self.hedge_percentage = 100.0
            self.hedge_order_id = result.get('order_id', 'N/A')
            self.last_check_time = time.time()
            self.hedge_placed_time = time.time()

            notifier.notify_hedge_executed(
                timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
                iv=self.dvol.get_current_dvol(),
                net_delta=net_delta_btc,
                hedge_type="INITIAL 1-to-1",
                size_btc=hedge_size,
                order_id=result.get('order_id', 'N/A')
            )
        else:
            app_logger.error("Hedge: Initial hedge placement failed!")
            notifier.notify_hedge_failed()

    # ─────────────────────────────────────────────────────────────────
    # CONTINUOUS HEDGE MANAGEMENT (called every 15-30 seconds)
    # ─────────────────────────────────────────────────────────────────

    def manage_hedge(self, positions, unrealized_loss_pct, profit_usd=0.0):
        """
        Core hedge management loop. Called from bot_engine monitor loop.

        Steps performed every call:
        1. If no positions: close any open hedge
        2. If hedge stopped out: skip
        3. If hedge is active: check stop-loss
        4. Emergency hedge if losing > 30% with no hedge
        5. Tighten SL if losing > 25%
        6. Rebalance or unwind active hedge based on current delta
        7. Trigger new hedge if delta exceeds threshold
        """
        self.last_check_time = time.time()

        # Step 1: No positions → close hedge
        if not positions:
            if self.hedge_active:
                app_logger.info("Hedge: Positions cleared. Closing hedge...")
                self.close_hedge()
            return

        # Step 2: Hedge stopped out → do nothing
        if self.hedge_stopped_out:
            app_logger.info("Hedge: Stopped out — skipping management for this trade.")
            return

        # Step 3: Hedge stop-loss check
        if self.hedge_active:
            hedge_pnl = self.get_live_hedge_pnl()
            exposure_btc = self._get_options_exposure_btc(positions)
            total_lots = exposure_btc * 1000
            dynamic_max_loss = HEDGE_MAX_LOSS_PER_LOT * total_lots

            if hedge_pnl < -dynamic_max_loss:
                app_logger.warning(
                    f"Hedge: STOP LOSS HIT! PnL={hedge_pnl:.2f} < -{dynamic_max_loss:.2f}. "
                    f"Closing hedge and disabling for this trade."
                )
                self.close_hedge()
                self.hedge_stopped_out = True
                notifier.notify_error(
                    f"Hedge Stop-Loss Hit!\nLoss: ${hedge_pnl:.2f}\n"
                    f"Hedge disabled for remainder of this trade."
                )
                return

        # Step 4: Emergency hedge when losing > 30% with no hedge
        if not self.hedge_active and unrealized_loss_pct >= 0.30:
            self._emergency_hedge(positions, unrealized_loss_pct)
            return

        # Step 5: Tighten SL if losing > 25%
        if unrealized_loss_pct >= HEDGE_EMERGENCY_LOSS_PCT and not self.sl_tightened:
            app_logger.warning(
                f"Hedge: Critical loss ({unrealized_loss_pct:.1%}). Tightening SL."
            )
            self.risk_manager.tighten_stop_loss(HEDGE_EMERGENCY_SL_TIGHTEN)
            self.sl_tightened = True

        # Step 6 & 7: Fetch current delta and manage hedge
        net_delta_btc, _, greeks_reliable = self._fetch_net_delta_and_gamma(positions)
        abs_delta = abs(net_delta_btc)
        current_dvol = self.dvol.get_current_dvol()

        leg_size = list(positions.values())[0]['size'] if positions else 1
        raw_net_delta = abs_delta / (leg_size * 0.001) if leg_size > 0 else 0.0

        if self.hedge_active:
            self._manage_active_hedge(
                net_delta_btc, raw_net_delta, greeks_reliable,
                current_dvol, positions, profit_usd
            )
        else:
            self._check_standard_trigger(
                net_delta_btc, raw_net_delta, greeks_reliable,
                current_dvol, positions
            )

    def _emergency_hedge(self, positions, unrealized_loss_pct):
        """Trigger an emergency hedge when losing > 30% with no active hedge."""
        app_logger.warning(
            f"Hedge: EMERGENCY trigger -- loss={unrealized_loss_pct:.1%} >= 30%. No hedge active."
        )
        net_delta_btc, _, greeks_reliable = self._fetch_net_delta_and_gamma(positions)

        # CRITICAL FIX: When any leg shows delta=0 (API bug), greeks cannot be trusted
        # for direction. ALWAYS cross-check with premium direction.
        fallback_dir, excess = self._detect_direction_from_premium(positions)

        if not greeks_reliable or abs(net_delta_btc) < 0.001:
            # Delta data is unreliable — use premium direction exclusively
            if fallback_dir:
                direction = fallback_dir
                exposure = self._get_options_exposure_btc(positions)
                hedge_size = exposure * 0.5
                app_logger.warning(
                    f"Hedge [EMERGENCY]: Greeks unreliable. Using premium fallback: "
                    f"dir={direction}, size={hedge_size:.4f} BTC"
                )
            else:
                app_logger.error("Hedge [EMERGENCY]: Cannot determine direction -- no delta and no premium data!")
                notifier.notify_hedge_failed()
                return
        else:
            # Delta is available — but if premium direction contradicts delta, trust premium
            delta_direction = 'sell' if net_delta_btc >= 0 else 'buy'
            hedge_size = abs(net_delta_btc)

            if fallback_dir and fallback_dir != delta_direction:
                app_logger.warning(
                    f"Hedge [EMERGENCY]: Delta says {delta_direction} but premium says {fallback_dir}. "
                    f"Using PREMIUM direction (more reliable during volatile moves)."
                )
                direction = fallback_dir
            else:
                direction = delta_direction
                app_logger.info(
                    f"Hedge [EMERGENCY]: Delta and premium agree on direction: {direction} {hedge_size:.4f} BTC"
                )

        if hedge_size <= 0:
            app_logger.error("Hedge [EMERGENCY]: Computed hedge size is 0 -- aborting.")
            return

        result = self._place_hedge(hedge_size, direction, "EMERGENCY")
        if result and result.get('success'):
            self.hedge_active = True
            self.hedge_type = "emergency_1to1"
            self.hedge_size_btc = hedge_size if direction == 'buy' else -hedge_size
            self.hedge_percentage = 100.0
            self.hedge_order_id = result.get('order_id', 'N/A')
            self.hedge_placed_time = time.time()

            if not self.sl_tightened:
                self.risk_manager.tighten_stop_loss(HEDGE_EMERGENCY_SL_TIGHTEN)
                self.sl_tightened = True

            notifier.notify_hedge_escalated(
                timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
                from_pct=0.0,
                to_pct=100.0,
                loss_pct=unrealized_loss_pct * 100
            )
        else:
            app_logger.error("Hedge [EMERGENCY]: Placement failed!")
            notifier.notify_hedge_failed()

    def _manage_active_hedge(self, net_delta_btc, raw_net_delta, greeks_reliable,
                             dvol, positions, profit_usd):
        """
        Manage an existing active hedge:
        - Unwind if delta has neutralized AND minimum hold time passed
        - Rebalance if delta has drifted more than threshold
        - Reverse if market direction flipped
        """
        current_hedge = self.execution.hedge_size_btc  # Signed: neg=short, pos=long
        min_hold_elapsed = (time.time() - self.hedge_placed_time) >= 60.0  # Min 60s hold

        # ── UNWIND: Delta returned to neutral ─────────────────────────
        UNWIND_THRESHOLD = 0.08
        if raw_net_delta < UNWIND_THRESHOLD and min_hold_elapsed:
            app_logger.info(
                f"Hedge: Delta neutralized (raw={raw_net_delta:.4f} < {UNWIND_THRESHOLD}). "
                f"Unwinding hedge to restore naked strangle."
            )
            self.close_hedge()
            return

        # ── DIRECTION REVERSAL: Market flipped ─────────────────────────
        # current_hedge < 0 means we are SHORT BTC (needed when net_delta > 0)
        # If net_delta has flipped sign strongly, close and re-hedge
        expected_hedge_negative = (net_delta_btc > 0)  # need short hedge when delta is positive
        actual_hedge_negative = (current_hedge < 0)
        direction_mismatch = (expected_hedge_negative != actual_hedge_negative)

        if direction_mismatch and raw_net_delta > 0.15 and greeks_reliable:
            app_logger.info(
                f"Hedge: Market direction reversed (net_delta={net_delta_btc:+.4f}, "
                f"hedge={current_hedge:+.4f}). Closing and re-hedging."
            )
            self.close_hedge()
            self._execute_initial_hedge(net_delta_btc, greeks_reliable, positions)
            return

        # ── REBALANCE: Hedge size drifted from 1-to-1 ─────────────────
        target_hedge_signed = -net_delta_btc  # Opposite of delta to neutralize
        delta_diff = target_hedge_signed - current_hedge
        REBALANCE_THRESHOLD = 0.02  # Only rebalance if drift > 0.02 BTC

        if abs(delta_diff) >= REBALANCE_THRESHOLD:
            direction = 'buy' if delta_diff > 0 else 'sell'
            app_logger.info(
                f"Hedge [REBALANCE]: Drift={delta_diff:+.4f} BTC. "
                f"Adjusting by {abs(delta_diff):.4f} BTC ({direction})."
            )
            result = self._place_hedge(abs(delta_diff), direction, "REBALANCE")
            if result and result.get('success'):
                self.execution.hedge_size_btc = current_hedge + (abs(delta_diff) if direction == 'buy' else -abs(delta_diff))
                self.hedge_size_btc = self.execution.hedge_size_btc
                self.hedge_type = "dynamic_rebalance"
                notifier.notify_hedge_executed(
                    timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
                    iv=dvol,
                    net_delta=net_delta_btc,
                    hedge_type="REBALANCE",
                    size_btc=abs(delta_diff),
                    order_id=result.get('order_id', 'N/A')
                )
        else:
            app_logger.info(
                f"Hedge: Active and balanced. Drift={delta_diff:+.4f} < {REBALANCE_THRESHOLD}. No action."
            )

    def _check_standard_trigger(self, net_delta_btc, raw_net_delta, greeks_reliable, dvol, positions):
        """Check if a new hedge should be triggered based on delta thresholds."""
        if dvol < 45.0:
            trigger = HEDGE_IV_THRESHOLDS['low']['delta_trigger']
            tier = "Low (<45%)"
        elif dvol <= 55.0:
            trigger = HEDGE_IV_THRESHOLDS['mid']['delta_trigger']
            tier = "Mid (45-55%)"
        else:
            trigger = HEDGE_IV_THRESHOLDS['high']['delta_trigger']
            tier = "High (>55%)"

        app_logger.info(
            f"Hedge: Standard check — raw_delta={raw_net_delta:.4f} | "
            f"trigger={trigger:.2f} | dvol_tier={tier} | greeks_reliable={greeks_reliable}"
        )

        if raw_net_delta > trigger:
            app_logger.info(f"Hedge: Triggering initial hedge. raw_delta {raw_net_delta:.4f} > {trigger:.2f}")
            self._execute_initial_hedge(net_delta_btc, greeks_reliable, positions)
        else:
            app_logger.info(
                f"Hedge: No hedge needed. raw_delta {raw_net_delta:.4f} <= {trigger:.2f}"
            )

    # ─────────────────────────────────────────────────────────────────
    # CLOSE HEDGE
    # ─────────────────────────────────────────────────────────────────

    def close_hedge(self):
        """Closes all active hedge positions and resets all state."""
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
        app_logger.info("Hedge: Smart hedge state fully reset.")
