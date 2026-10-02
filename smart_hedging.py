"""
smart_hedging.py — STUB (Bandwidth/Memory Optimization)
========================================================
The full SmartHedgingManager implementation has been replaced with this
lightweight stub. The hedge engine is currently DISABLED in bot_engine.py
(smart_hedging_enabled = False) so this stub is safe and functionally
equivalent for the live trading pipeline.

All public methods return safe no-op values so that web_server.py status
reporting, emergency close, and health checks continue to work without change.

DO NOT remove this file — it is imported at startup by bot_engine.py.
"""

from logger import app_logger


class SmartHedgingManager:
    """Lightweight stub — hedge engine is disabled. No trading logic runs here."""

    def __init__(self, execution_handler=None, dvol_provider=None,
                 risk_manager=None, api_client=None):
        self.execution = execution_handler
        self.is_running = False
        self._hedge_active = False
        app_logger.info("[SmartHedging] Stub loaded — hedge engine is disabled.")

    # ── Status & Reporting ─────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Return a safe empty status dict. Used by web_server /api/status."""
        return {
            'enabled': False,
            'hedge_active': False,
            'hedge_pnl_usd': 0.0,
            'hedge_size_btc': 0.0,
            'hedge_type': 'DISABLED',
            'hedge_entry_price': 0.0,
            'reason': 'Hedge engine is disabled.',
        }

    def get_live_hedge_pnl(self) -> float:
        """Return 0.0 — hedge is disabled."""
        return 0.0

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def set_entry_premiums(self, active_positions: dict):
        """No-op stub."""
        pass

    def run_post_entry_hedge(self):
        """No-op stub — called in a thread when smart_hedging_enabled=True."""
        pass

    def close_hedge(self, reason: str = "Manual"):
        """No-op stub — called by web_server emergency_close and toggle."""
        app_logger.info(f"[SmartHedging] close_hedge() called (stub) — reason: {reason}")

    def stop(self):
        """No-op stub."""
        self.is_running = False

    # ── Compatibility shims ────────────────────────────────────────────────────

    def __bool__(self):
        return True  # So `if bot_engine.smart_hedging:` checks pass
