import config
from logger import app_logger

class RiskManager:
    def __init__(self, api_client):
        self.api_client = api_client
        self.paper_equity = float(config.STARTING_CAPITAL)
        self.live_equity = 0.0
        self.sl_multiplier = config.SL_PERCENT  # Default 1.30 (130% of premium)
        
        # --- ARES Dynamic Profit Lock State ---
        self.highest_profit_pct = 0.0       # One-way ratchet: only increases
        self.current_trailing_sl = None     # None = not activated yet
        self.trailing_confirmed = False     # True once 19% is reached
        self.confirm_started = False        # True once 15% is first touched

        # Engine-isolated trailing states
        self.paper_highest_profit_pct = 0.0
        self.paper_current_trailing_sl = None
        self.paper_trailing_confirmed = False
        self.paper_confirm_started = False

        self.live_highest_profit_pct = 0.0
        self.live_current_trailing_sl = None
        self.live_trailing_confirmed = False
        self.live_confirm_started = False

    @property
    def current_equity(self):
        """Returns the equity corresponding to the active trading mode."""
        if getattr(config, 'BOT_MODE', 'PAPER') == 'LIVE':
            return self.live_equity if self.live_equity > 0 else self.paper_equity
        return self.paper_equity

    @current_equity.setter
    def current_equity(self, val):
        val = float(val)
        if getattr(config, 'BOT_MODE', 'PAPER') == 'LIVE':
            self.live_equity = val
        else:
            self.paper_equity = val
        
    def update_equity(self):
        """Fetch current equity from exchange."""
        if getattr(config, 'BOT_MODE', 'PAPER') == 'PAPER':
            # Bypass API call in PAPER mode, keep live_equity separate
            app_logger.info(f"Risk [PAPER]: Simulated equity is ${self.paper_equity:.2f} (No live check)")
            return
        
        try:
            res = self.api_client.get_balances()
            if res.get('success'):
                meta = res.get('meta', {})
                net_eq = float(meta.get('net_equity', 0.0))
                if net_eq > 0:
                    self.live_equity = net_eq
                    app_logger.info(f"Risk [LIVE]: Real Delta equity updated from net_equity to ${self.live_equity:.2f}")
                    return
                for b in res.get('result', []):
                    if b.get('asset_symbol') in ('USD', 'USDT', 'INR'):
                        avail = float(b.get('available_balance', 0) or 0)
                        if avail > 0:
                            self.live_equity = avail
                            app_logger.info(f"Risk [LIVE]: Real Delta equity updated to ${self.live_equity:.2f}")
                            return
        except Exception as e:
            app_logger.error(f"Risk [LIVE]: Failed to update live equity: {e}")

    def tighten_stop_loss(self, level):
        """Tighten option SL during emergency hedging (e.g. 1.05 for 105%)."""
        self.sl_multiplier = level
        app_logger.warning(f"Risk: EMERGENCY SL tightened to {level*100:.1f}%")

    def get_dynamic_sl(self):
        """Returns the active SL multiplier."""
        return self.sl_multiplier

    def reset_sl_multiplier(self):
        """Reset SL to default level."""
        self.sl_multiplier = config.SL_PERCENT

    def calculate_max_risk_per_trade(self):
        """Returns the maximum absolute USDT risk allowed for a single trade based on 1.5% rule."""
        return self.current_equity * config.MAX_RISK_PER_TRADE_PCT

    # ── ARES Dynamic Profit Lock ─────────────────────────────────────────────

    def reset_trailing_state(self, mode=None):
        """Reset trailing state for a new trade."""
        if mode == 'LIVE' or mode is None:
            self.live_highest_profit_pct = 0.0
            self.live_current_trailing_sl = None
            self.live_trailing_confirmed = False
            self.live_confirm_started = False
        if mode == 'PAPER' or mode is None:
            self.paper_highest_profit_pct = 0.0
            self.paper_current_trailing_sl = None
            self.paper_trailing_confirmed = False
            self.paper_confirm_started = False

        active_mode = getattr(config, 'BOT_MODE', 'PAPER')
        if active_mode == 'LIVE':
            self.highest_profit_pct = self.live_highest_profit_pct
            self.current_trailing_sl = self.live_current_trailing_sl
            self.trailing_confirmed = self.live_trailing_confirmed
            self.confirm_started = self.live_confirm_started
        else:
            self.highest_profit_pct = self.paper_highest_profit_pct
            self.current_trailing_sl = self.paper_current_trailing_sl
            self.trailing_confirmed = self.paper_trailing_confirmed
            self.confirm_started = self.paper_confirm_started
        app_logger.info(f"Risk [DPL]: Trailing state reset (mode={mode or 'ALL'}).")

    def get_trailing_state(self, mode=None):
        """Return trailing state for persistence and dashboard display."""
        active_mode = mode or getattr(config, 'BOT_MODE', 'PAPER')
        if active_mode == 'LIVE':
            return self.get_live_trailing_state()
        return self.get_paper_trailing_state()

    def get_live_trailing_state(self):
        """Return dedicated LIVE engine trailing state."""
        return {
            "highest_profit_pct": round(self.live_highest_profit_pct * 100, 2),
            "current_trailing_sl": round(self.live_current_trailing_sl * 100, 2) if self.live_current_trailing_sl is not None else None,
            "trailing_confirmed": self.live_trailing_confirmed,
            "confirm_started": self.live_confirm_started,
        }

    def get_paper_trailing_state(self):
        """Return dedicated PAPER engine trailing state."""
        return {
            "highest_profit_pct": round(self.paper_highest_profit_pct * 100, 2),
            "current_trailing_sl": round(self.paper_current_trailing_sl * 100, 2) if self.paper_current_trailing_sl is not None else None,
            "trailing_confirmed": self.paper_trailing_confirmed,
            "confirm_started": self.paper_confirm_started,
        }

    def restore_trailing_state(self, state, mode=None):
        """Restore trailing state from persistence (e.g., after restart)."""
        if not state:
            return
        target_mode = mode or getattr(config, 'BOT_MODE', 'PAPER')
        peak = state.get("highest_profit_pct", 0.0) / 100.0
        sl_val = state.get("current_trailing_sl")
        sl = sl_val / 100.0 if sl_val is not None else None
        conf = state.get("trailing_confirmed", False)
        start = state.get("confirm_started", False)

        if target_mode == 'LIVE':
            self.live_highest_profit_pct = peak
            self.live_current_trailing_sl = sl
            self.live_trailing_confirmed = conf
            self.live_confirm_started = start
        else:
            self.paper_highest_profit_pct = peak
            self.paper_current_trailing_sl = sl
            self.paper_trailing_confirmed = conf
            self.paper_confirm_started = start

        # Update active pointer
        active_mode = getattr(config, 'BOT_MODE', 'PAPER')
        if active_mode == 'LIVE':
            self.highest_profit_pct = self.live_highest_profit_pct
            self.current_trailing_sl = self.live_current_trailing_sl
            self.trailing_confirmed = self.live_trailing_confirmed
            self.confirm_started = self.live_confirm_started
        else:
            self.highest_profit_pct = self.paper_highest_profit_pct
            self.current_trailing_sl = self.paper_current_trailing_sl
            self.trailing_confirmed = self.paper_trailing_confirmed
            self.confirm_started = self.paper_confirm_started

        app_logger.info(f"Risk [DPL]: Trailing state restored for {target_mode}. Peak={peak*100:.1f}% SL={sl*100 if sl is not None else 'None'} Confirmed={conf}")

    def _update_ratchet(self, pnl_pct, mode=None):
        """
        Core ratchet engine. Updates highest_profit and trailing SL.
        
        MANDATORY RULES:
        1. highest_profit_pct can ONLY increase
        2. current_trailing_sl can ONLY increase
        3. No hard Take Profit — trades run until SL hit or 5PM square-off
        """
        active_mode = mode or getattr(config, 'BOT_MODE', 'PAPER')
        
        # Select target state
        if active_mode == 'LIVE':
            peak = self.live_highest_profit_pct
            sl = self.live_current_trailing_sl
            conf = self.live_trailing_confirmed
            start = self.live_confirm_started
        else:
            peak = self.paper_highest_profit_pct
            sl = self.paper_current_trailing_sl
            conf = self.paper_trailing_confirmed
            start = self.paper_confirm_started

        # ── Rule 1: Update peak profit (one-way ratchet) ─────────────────
        if pnl_pct > peak:
            peak = pnl_pct
        
        # ── Below 15%: No trailing logic at all ──────────────────────────
        if peak < config.TRAILING_CONFIRM_THRESHOLD:
            self._save_ratchet_state(active_mode, peak, sl, conf, start)
            return
        
        # ── 15% touched: Mark confirmation started ───────────────────────
        if not start:
            start = True
            app_logger.info(f"Risk [DPL-{active_mode}]: Confirmation window opened at {pnl_pct*100:.1f}% profit.")
        
        # ── 19% reached: Confirm trailing and lock capital protection ────
        if not conf and peak >= config.TRAILING_CONFIRM_TARGET:
            conf = True
            new_sl = config.CAPITAL_PROTECTION_SL  # +5%
            if sl is None or new_sl > sl:
                sl = new_sl
                app_logger.warning(f"Risk [DPL-{active_mode}]: ✅ CAPITAL PROTECTION ACTIVATED! SL locked at +{new_sl*100:.0f}%. Trade can never lose.")
        
        # ── Not yet confirmed: do nothing further ────────────────────────
        if not conf:
            self._save_ratchet_state(active_mode, peak, sl, conf, start)
            return
        
        # ── Progressive Profit Lock Tiers ────────────────────────────────
        for threshold, sl_level in config.PROFIT_LOCK_TIERS:
            if peak >= threshold:
                if sl is None or sl_level > sl:
                    old_sl = sl
                    sl = sl_level
                    app_logger.warning(f"Risk [DPL-{active_mode}]: 🔒 Profit Lock Tier Hit! Peak={peak*100:.1f}% → SL Ratcheted from {old_sl*100 if old_sl else 0:.0f}% to +{sl_level*100:.0f}%")
        
        # ── Dynamic Trailing after 28%: SL = Peak - 5% ───────────────────
        if peak >= config.DYNAMIC_TRAIL_THRESHOLD:
            dynamic_sl = round(peak - config.DYNAMIC_TRAIL_GAP, 4)
            if sl is None or dynamic_sl > sl:
                old_sl = sl
                sl = dynamic_sl
                app_logger.info(f"Risk [DPL-{active_mode}]: 📈 Dynamic Trail Updated. Peak={peak*100:.1f}% → SL={dynamic_sl*100:.1f}%")

        self._save_ratchet_state(active_mode, peak, sl, conf, start)

    def _save_ratchet_state(self, mode, peak, sl, conf, start):
        if mode == 'LIVE':
            self.live_highest_profit_pct = peak
            self.live_current_trailing_sl = sl
            self.live_trailing_confirmed = conf
            self.live_confirm_started = start
        else:
            self.paper_highest_profit_pct = peak
            self.paper_current_trailing_sl = sl
            self.paper_trailing_confirmed = conf
            self.paper_confirm_started = start

        active_mode = getattr(config, 'BOT_MODE', 'PAPER')
        if active_mode == mode:
            self.highest_profit_pct = peak
            self.current_trailing_sl = sl
            self.trailing_confirmed = conf
            self.confirm_started = start

    def check_sl_tp(self, total_entry_premium, current_total_premium, pnl_pct):
        """
        ARES Dynamic Profit Lock decision engine.
        
        Returns:
            "STOP_LOSS_ALL"     - Hard downside SL hit (-130%)
            "TRAILING_SL_EXIT"  - Dynamic trailing SL hit (profit locked)
            None                - No action needed
        
        REMOVED actions (no longer exist):
            "TAKE_PROFIT_ALL"   - No hard TP ceiling
            "PARTIAL_PROFIT"    - No partial close
            "TRAILING_SL_TRIGGERED" - Replaced by progressive ratchet
        """
        
        # ── Step 1: Update the ratchet engine ────────────────────────────
        self._update_ratchet(pnl_pct)
        
        # ── Step 2: Check hard downside SL (-130%) ───────────────────────
        if pnl_pct <= -self.sl_multiplier:
            return "STOP_LOSS_ALL"
        
        # ── Step 3: Check trailing SL hit ────────────────────────────────
        if self.trailing_confirmed and self.current_trailing_sl is not None:
            if pnl_pct <= self.current_trailing_sl:
                app_logger.warning(f"Risk [DPL]: 🛑 TRAILING SL HIT! P&L={pnl_pct*100:.1f}% ≤ SL={self.current_trailing_sl*100:.1f}% | Peak was {self.highest_profit_pct*100:.1f}%")
                return "TRAILING_SL_EXIT"
        
        return None
