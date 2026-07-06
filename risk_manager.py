import config
from logger import app_logger

class RiskManager:
    def __init__(self, api_client):
        self.api_client = api_client
        self.current_equity = config.STARTING_CAPITAL
        self.sl_multiplier = config.SL_PERCENT  # Default 1.30 (130% of premium)
        
        # --- ARES Dynamic Profit Lock State ---
        self.highest_profit_pct = 0.0       # One-way ratchet: only increases
        self.current_trailing_sl = None     # None = not activated yet
        self.trailing_confirmed = False     # True once 19% is reached
        self.confirm_started = False        # True once 15% is first touched
        
    def update_equity(self):
        """Fetch current equity from exchange."""
        if config.BOT_MODE == 'PAPER':
            # Bypass API call in PAPER mode
            app_logger.info(f"Risk [PAPER]: Simulated equity is ${self.current_equity:.2f} (No live check)")
            return
        
        try:
            res = self.api_client.get_balances()
            if res.get('success'):
                for b in res.get('result', []):
                    if b.get('asset_symbol') == 'USDT':
                        self.current_equity = float(b.get('available_balance', 0))
                        app_logger.info(f"Risk: Equity updated to ${self.current_equity:.2f}")
                        return
        except Exception as e:
            app_logger.error(f"Risk: Failed to update equity. Using fallback ${self.current_equity:.2f}. {e}")

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

    def reset_trailing_state(self):
        """Reset all trailing state for a new trade."""
        self.highest_profit_pct = 0.0
        self.current_trailing_sl = None
        self.trailing_confirmed = False
        self.confirm_started = False
        app_logger.info("Risk [DPL]: Trailing state reset for new trade.")

    def get_trailing_state(self):
        """Return current trailing state for persistence and dashboard display."""
        return {
            "highest_profit_pct": round(self.highest_profit_pct * 100, 2),
            "current_trailing_sl": round(self.current_trailing_sl * 100, 2) if self.current_trailing_sl is not None else None,
            "trailing_confirmed": self.trailing_confirmed,
            "confirm_started": self.confirm_started,
        }

    def restore_trailing_state(self, state):
        """Restore trailing state from persistence (e.g., after restart)."""
        if state:
            self.highest_profit_pct = state.get("highest_profit_pct", 0.0) / 100.0
            sl_val = state.get("current_trailing_sl")
            self.current_trailing_sl = sl_val / 100.0 if sl_val is not None else None
            self.trailing_confirmed = state.get("trailing_confirmed", False)
            self.confirm_started = state.get("confirm_started", False)
            app_logger.info(f"Risk [DPL]: Trailing state restored. Peak={self.highest_profit_pct*100:.1f}% SL={self.current_trailing_sl*100:.1f}% Confirmed={self.trailing_confirmed}" if self.current_trailing_sl is not None else f"Risk [DPL]: Trailing state restored. Peak={self.highest_profit_pct*100:.1f}% SL=None Confirmed={self.trailing_confirmed}")

    def _update_ratchet(self, pnl_pct):
        """
        Core ratchet engine. Updates highest_profit and trailing SL.
        
        MANDATORY RULES:
        1. highest_profit_pct can ONLY increase
        2. current_trailing_sl can ONLY increase
        3. No hard Take Profit — trades run until SL hit or 5PM square-off
        """
        
        # ── Rule 1: Update peak profit (one-way ratchet) ─────────────────
        if pnl_pct > self.highest_profit_pct:
            self.highest_profit_pct = pnl_pct
        
        # ── Below 15%: No trailing logic at all ──────────────────────────
        if self.highest_profit_pct < config.TRAILING_CONFIRM_THRESHOLD:
            return
        
        # ── 15% touched: Mark confirmation started ───────────────────────
        if not self.confirm_started:
            self.confirm_started = True
            app_logger.info(f"Risk [DPL]: Confirmation window opened at {pnl_pct*100:.1f}% profit.")
        
        # ── 19% reached: Confirm trailing and lock capital protection ────
        if not self.trailing_confirmed and self.highest_profit_pct >= config.TRAILING_CONFIRM_TARGET:
            self.trailing_confirmed = True
            new_sl = config.CAPITAL_PROTECTION_SL  # +5%
            if self.current_trailing_sl is None or new_sl > self.current_trailing_sl:
                self.current_trailing_sl = new_sl
                app_logger.warning(f"Risk [DPL]: ✅ CAPITAL PROTECTION ACTIVATED! SL locked at +{new_sl*100:.0f}%. Trade can never lose.")
        
        # ── Not yet confirmed: do nothing further ────────────────────────
        if not self.trailing_confirmed:
            return
        
        # ── Progressive Profit Lock Tiers ────────────────────────────────
        for threshold, sl_level in config.PROFIT_LOCK_TIERS:
            if self.highest_profit_pct >= threshold:
                if self.current_trailing_sl is None or sl_level > self.current_trailing_sl:
                    old_sl = self.current_trailing_sl
                    self.current_trailing_sl = sl_level
                    app_logger.warning(f"Risk [DPL]: 🔒 Profit Lock Tier Hit! Peak={self.highest_profit_pct*100:.1f}% → SL moved from {old_sl*100:.1f}% to +{sl_level*100:.0f}%")
        
        # ── Dynamic Trailing After 28% ───────────────────────────────────
        if self.highest_profit_pct >= config.DYNAMIC_TRAIL_THRESHOLD:
            dynamic_sl = round(self.highest_profit_pct - config.DYNAMIC_TRAIL_GAP, 4)
            if self.current_trailing_sl is None or dynamic_sl > self.current_trailing_sl:
                old_sl = self.current_trailing_sl
                self.current_trailing_sl = dynamic_sl
                app_logger.info(f"Risk [DPL]: 📈 Dynamic Trail Updated. Peak={self.highest_profit_pct*100:.1f}% → SL = {dynamic_sl*100:.1f}% (was {old_sl*100:.1f}%)")

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
