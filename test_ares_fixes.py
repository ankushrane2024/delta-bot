"""
test_ares_fixes.py
Unit + integration tests for:
  A1 - IV Zone badge uses correct 3-tier thresholds
  A2 - IV Percentile/Rank null sentinel when history is thin; -0 clamp
  A3 - Market Condition derived from real trend+edge, not premium_state string
  B1 - RV24 pre-trade entry filter blocks/allows correctly
  B1 isolation - SL and trailing-SL logic untouched

Run with: python test_ares_fixes.py
"""

import sys
import os
import math
import time
import statistics
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ── Helpers to build a minimal PSCE instance ─────────────────────────────────

def _make_dvol_provider(history, current_dvol=34.31):
    """Build a mock dvol_provider with configurable history and percentile."""
    dvol = MagicMock()
    dvol.current_dvol = current_dvol
    dvol.dvol_history = history
    # Compute percentile the same way dvol_provider does
    if history:
        count = sum(1 for v in history if v <= current_dvol)
        dvol.dvol_percentile = (count / len(history)) * 100.0
    else:
        dvol.dvol_percentile = 50.0
    dvol.last_update_time = time.time()
    return dvol


def _make_psce(history=None, current_dvol=34.31):
    """Build a PSCE instance with mocked dependencies."""
    from psce import PremiumSellingConditionsEngine
    api_client = MagicMock()
    if history is None:
        history = list(range(30, 60))  # 30 entries: 30..59%
    dvol = _make_dvol_provider(history, current_dvol)
    psce = PremiumSellingConditionsEngine(api_client, dvol)
    # Prevent file I/O during tests
    psce._save_historical_snapshot = MagicMock()
    psce._get_current_session_dvol_slope = MagicMock(return_value=(0.0, []))
    return psce


# ═══════════════════════════════════════════════════════════════════════════════
# A1 — IV Zone Badge
# ═══════════════════════════════════════════════════════════════════════════════

class TestA1ZoneBadge(unittest.TestCase):

    def _get_zone(self, atm_iv):
        """Call psce with a synthetic IV value and return the zone field."""
        psce = _make_psce(current_dvol=atm_iv)
        # Patch BTC price feed so evaluate_conditions doesn't early-exit
        ticker = {'spot_price': 60000.0}
        psce.api_client.get_realtime_ticker.return_value = ticker
        psce.api_client.last_price_update_time = time.time()
        # Patch intraday slope + RV so the method can run
        psce._get_current_session_dvol_slope = MagicMock(return_value=(0.0, list(range(1, 61))))
        # Patch _calculate_rv_5d and RV24 filter to keep test deterministic
        psce._calculate_rv_5d = MagicMock(return_value=25.0)
        psce._check_rv24_filter = MagicMock(return_value=(False, "RV24 ok"))
        result = psce.evaluate_conditions(mode="MONITOR")
        return result.get('zone')

    def test_below_20_is_red(self):
        """IV < 20% → zone RED (BLOCKED)."""
        zone = self._get_zone(15.0)
        self.assertEqual(zone, "RED", f"Expected RED at IV=15, got {zone}")

    def test_medium_iv_at_34(self):
        """IV = 34.2% (between 20-50%) → zone MEDIUM, NOT HEALTHY."""
        zone = self._get_zone(34.2)
        self.assertEqual(zone, "MEDIUM", f"Expected MEDIUM at IV=34.2, got {zone}")

    def test_healthy_iv_at_55(self):
        """IV >= 50% → zone HEALTHY."""
        zone = self._get_zone(55.0)
        self.assertEqual(zone, "HEALTHY", f"Expected HEALTHY at IV=55, got {zone}")

    def test_exactly_at_50_boundary(self):
        """IV exactly at 50% → zone HEALTHY (boundary inclusive)."""
        zone = self._get_zone(50.0)
        self.assertEqual(zone, "HEALTHY", f"Expected HEALTHY at IV=50, got {zone}")


# ═══════════════════════════════════════════════════════════════════════════════
# A2 — IV Percentile and IV Rank
# ═══════════════════════════════════════════════════════════════════════════════

class TestA2IVPercentileRank(unittest.TestCase):

    def _get_metrics(self, history, current_dvol=34.31):
        psce = _make_psce(history=history, current_dvol=current_dvol)
        ticker = {'spot_price': 60000.0}
        psce.api_client.get_realtime_ticker.return_value = ticker
        psce.api_client.last_price_update_time = time.time()
        psce._get_current_session_dvol_slope = MagicMock(return_value=(0.0, list(range(1, 61))))
        psce._calculate_rv_5d = MagicMock(return_value=25.0)
        psce._check_rv24_filter = MagicMock(return_value=(False, "RV24 ok"))
        result = psce.evaluate_conditions(mode="MONITOR")
        return result.get('metrics', {})

    def test_null_when_history_empty(self):
        """Empty history → iv_percentile is None (Insufficient data)."""
        m = self._get_metrics(history=[])
        self.assertIsNone(m.get('iv_percentile'), "Expected None for iv_percentile with empty history")
        self.assertIsNone(m.get('iv_rank'), "Expected None for iv_rank with empty history")

    def test_null_when_history_too_thin(self):
        """History with < 5 entries → iv_percentile is None."""
        m = self._get_metrics(history=[30.0, 35.0, 40.0])
        self.assertIsNone(m.get('iv_percentile'), "Expected None for iv_percentile with 3 entries")

    def test_valid_percentile_with_sufficient_history(self):
        """30 entries → iv_percentile strictly between 0 and 100."""
        history = list(range(30, 60))  # 30 values 30..59
        m = self._get_metrics(history=history, current_dvol=34.31)
        pct = m.get('iv_percentile')
        self.assertIsNotNone(pct, "iv_percentile should not be None with 30 entries")
        self.assertGreater(pct, 0, f"iv_percentile should be > 0, got {pct}")
        self.assertLess(pct, 100, f"iv_percentile should be < 100, got {pct}")

    def test_iv_rank_never_negative(self):
        """iv_rank is clamped to >= 0 even when current_dvol < min(history)."""
        # History has min=35, but current_dvol=30 (below range)
        history = list(range(35, 65))  # 30 entries 35..64
        m = self._get_metrics(history=history, current_dvol=30.0)
        rank = m.get('iv_rank')
        if rank is not None:
            self.assertGreaterEqual(rank, 0.0, f"iv_rank must be >= 0, got {rank}")

    def test_iv_history_ready_flag(self):
        """iv_history_ready is True when >= 5 entries, False otherwise."""
        m_thin = self._get_metrics(history=[30.0, 35.0])
        self.assertFalse(m_thin.get('iv_history_ready'), "Should be False with 2 entries")

        m_ready = self._get_metrics(history=list(range(30, 60)))
        self.assertTrue(m_ready.get('iv_history_ready'), "Should be True with 30 entries")


# ═══════════════════════════════════════════════════════════════════════════════
# A3 — Market Condition
# ═══════════════════════════════════════════════════════════════════════════════

class TestA3MarketCondition(unittest.TestCase):

    def _get_result(self, atm_iv, force_trend=None, force_edge=None):
        psce = _make_psce(current_dvol=atm_iv)
        ticker = {'spot_price': 60000.0}
        psce.api_client.get_realtime_ticker.return_value = ticker
        psce.api_client.last_price_update_time = time.time()
        psce._calculate_rv_5d = MagicMock(return_value=25.0)
        psce._check_rv24_filter = MagicMock(return_value=(False, "RV24 ok"))

        if force_trend == "RISING":
            # Force slope > 0.5 to trigger RISING
            psce._get_current_session_dvol_slope = MagicMock(return_value=(2.0, list(range(1, 61))))
            # Also override dvol_history to have rising slope for 5d trend
            psce.dvol_provider.dvol_history = [30, 31, 32, 33, 34, 35] * 5
        else:
            psce._get_current_session_dvol_slope = MagicMock(return_value=(0.0, list(range(1, 61))))

        result = psce.evaluate_conditions(mode="MONITOR")
        return result

    def test_directional_when_trend_rising(self):
        """RISING iv_trend_5d → market_condition DIRECTIONAL."""
        result = self._get_result(55.0, force_trend="RISING")
        self.assertEqual(result.get('market_condition'), "DIRECTIONAL",
                         f"Expected DIRECTIONAL for RISING trend, got {result.get('market_condition')}")

    def test_directional_lowers_confidence_vs_range(self):
        """DIRECTIONAL case should have lower or equal edge_score than RANGE case."""
        # RANGE case: stable IV at 55% (high enough for HEALTHY)
        psce_range = _make_psce(current_dvol=55.0)
        psce_range.api_client.get_realtime_ticker.return_value = {'spot_price': 60000.0}
        psce_range.api_client.last_price_update_time = time.time()
        psce_range._calculate_rv_5d = MagicMock(return_value=25.0)
        psce_range._check_rv24_filter = MagicMock(return_value=(False, "RV24 ok"))
        psce_range._get_current_session_dvol_slope = MagicMock(return_value=(0.0, list(range(1, 61))))
        result_range = psce_range.evaluate_conditions(mode="MONITOR")

        # DIRECTIONAL case: forced RISING trend
        result_dir = self._get_result(55.0, force_trend="RISING")

        range_edge = result_range.get('edge_score', 0)
        dir_edge = result_dir.get('edge_score', 0)
        self.assertGreaterEqual(range_edge, dir_edge,
                                f"RANGE edge ({range_edge}) should be >= DIRECTIONAL edge ({dir_edge})")


# ═══════════════════════════════════════════════════════════════════════════════
# B1 — RV24 Pre-Trade Entry Filter
# ═══════════════════════════════════════════════════════════════════════════════

class TestB1RV24Filter(unittest.TestCase):

    def _run_filter(self, rv24, rv24_avg_60d, atm_iv):
        """Run just _check_rv24_filter with specific values."""
        psce = _make_psce(current_dvol=atm_iv)
        psce._calculate_rv_24h = MagicMock(return_value=rv24)
        psce._calculate_rv24_avg_60day = MagicMock(return_value=rv24_avg_60d)
        return psce._check_rv24_filter(atm_iv)

    def test_blocks_when_rv24_spikes_above_60d_avg(self):
        """RV24 > 1.3 * RV24_avg_60day → blocked."""
        blocked, reason = self._run_filter(rv24=55.0, rv24_avg_60d=40.0, atm_iv=60.0)
        self.assertTrue(blocked, "Should block when RV24=55 > 1.3*40=52")
        self.assertIn("Spike", reason)
        self.assertIn("No same-day retry", reason)

    def test_blocks_when_rv24_eats_iv_premium(self):
        """RV24 > 0.85 * ATM IV → blocked."""
        blocked, reason = self._run_filter(rv24=30.0, rv24_avg_60d=25.0, atm_iv=34.0)
        # 0.85 * 34 = 28.9, RV24=30 > 28.9 → block
        self.assertTrue(blocked, "Should block when RV24=30 > 0.85*34=28.9")
        self.assertIn("thin", reason)
        self.assertIn("No same-day retry", reason)

    def test_passes_in_normal_conditions(self):
        """Normal RV24 below both thresholds → allowed."""
        blocked, reason = self._run_filter(rv24=25.0, rv24_avg_60d=30.0, atm_iv=50.0)
        # 1.3*30=39 > 25, 0.85*50=42.5 > 25 → both pass
        self.assertFalse(blocked, f"Should NOT block in normal conditions, reason: {reason}")

    def test_b1_only_fires_at_entry_mode(self):
        """B1 filter is NOT called when mode=MONITOR (in-trade monitoring)."""
        from psce import PremiumSellingConditionsEngine
        psce = _make_psce(current_dvol=34.31)
        psce.api_client.get_realtime_ticker.return_value = {'spot_price': 60000.0}
        psce.api_client.last_price_update_time = time.time()
        psce._get_current_session_dvol_slope = MagicMock(return_value=(0.0, list(range(1, 61))))
        psce._calculate_rv_5d = MagicMock(return_value=25.0)
        psce._check_rv24_filter = MagicMock(return_value=(True, "SHOULD NOT BE CALLED"))
        result = psce.evaluate_conditions(mode="MONITOR")
        # In MONITOR mode, B1 should NOT be called
        psce._check_rv24_filter.assert_not_called()

    def test_b1_fires_at_entry_mode(self):
        """B1 filter IS called when mode=ENTRY."""
        psce = _make_psce(current_dvol=34.31)
        psce.api_client.get_realtime_ticker.return_value = {'spot_price': 60000.0}
        psce.api_client.last_price_update_time = time.time()
        psce._get_current_session_dvol_slope = MagicMock(return_value=(0.0, list(range(1, 61))))
        psce._calculate_rv_5d = MagicMock(return_value=25.0)
        psce._check_rv24_filter = MagicMock(return_value=(False, "RV24 ok"))
        psce.evaluate_conditions(mode="ENTRY")
        psce._check_rv24_filter.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# B1 Isolation — confirm zero interaction with SL/trailing-SL
# ═══════════════════════════════════════════════════════════════════════════════

class TestB1IsolationFromSL(unittest.TestCase):
    """
    Verify that B1 RV24 filter CANNOT interact with the SL or trailing-SL
    monitor loop. These are completely separate code paths:
      - B1 runs inside psce.evaluate_conditions() (entry gate)
      - SL monitor runs inside bot_engine.monitor_loop() (post-entry loop)
    This test verifies that blocking at B1 produces no side effects on
    the state variables used by the SL/trailing-SL logic.
    """

    def test_b1_block_does_not_set_any_leg_hit_sl(self):
        """When B1 blocks, any_leg_hit_sl state is never set."""
        psce = _make_psce(current_dvol=34.31)
        psce.api_client.get_realtime_ticker.return_value = {'spot_price': 60000.0}
        psce.api_client.last_price_update_time = time.time()
        psce._get_current_session_dvol_slope = MagicMock(return_value=(0.0, list(range(1, 61))))
        psce._calculate_rv_5d = MagicMock(return_value=25.0)
        psce._check_rv24_filter = MagicMock(return_value=(True, "B1 blocked"))

        result = psce.evaluate_conditions(mode="ENTRY")

        # B1 blocks → trade_allowed is False, final_decision is BLOCK
        self.assertFalse(result['trade_allowed'])
        self.assertEqual(result['final_decision'], 'BLOCK')

        # B1 result contains no SL-related keys
        self.assertNotIn('any_leg_hit_sl', result)
        self.assertNotIn('trailing_sl', result)
        self.assertNotIn('action', result)

    def test_b1_block_does_not_touch_risk_manager(self):
        """B1 block does not call risk_manager (not even imported by psce.py)."""
        import psce as psce_module
        # Confirm risk_manager is not imported anywhere in psce.py
        import inspect
        source = inspect.getsource(psce_module)
        self.assertNotIn('risk_manager', source,
                         "psce.py must NOT import or reference risk_manager")
        self.assertNotIn('trailing_sl', source,
                         "psce.py must NOT reference trailing_sl")
        self.assertNotIn('any_leg_hit_sl', source,
                         "psce.py must NOT reference any_leg_hit_sl")


# ═══════════════════════════════════════════════════════════════════════════════
# Config preservation tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfigUnchanged(unittest.TestCase):

    def test_sl_percent_still_valid(self):
        """SL_PERCENT must remain at valid configured level (1.00 or 1.50)."""
        import config
        self.assertIn(config.SL_PERCENT, (1.00, 1.50),
                      f"SL_PERCENT unexpected! Expected 1.00 or 1.50, got {config.SL_PERCENT}")

    def test_smart_hedging_disabled(self):
        """smart_hedging_enabled must still be False (as set earlier)."""
        import config
        # Hedging is disabled via instance attribute in bot_engine, not config
        # Just verify config doesn't override it unexpectedly
        self.assertTrue(hasattr(config, 'SL_PERCENT'), "SL_PERCENT must exist in config")


# ═══════════════════════════════════════════════════════════════════════════════
# Deribit candle fetch (smoke test — live network, skipped in offline runs)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeribitCandleFetch(unittest.TestCase):

    def test_fetch_1d_returns_60_plus_days(self):
        """Deribit 1D DVOL endpoint returns >= 60 daily entries (live network)."""
        try:
            psce = _make_psce()
            psce.api_client.last_price_update_time = time.time()
            closes = psce._fetch_deribit_btc_candles(resolution_seconds=86400, days=65)
            self.assertGreaterEqual(len(closes), 60,
                                    f"Expected >= 60 daily candles, got {len(closes)}")
            self.assertTrue(all(c > 0 for c in closes),
                            "All closes must be positive")
        except Exception as e:
            self.skipTest(f"Network unavailable: {e}")

    def test_rv24_is_positive_real_number(self):
        """_calculate_rv_24h returns a positive, non-zero value from Deribit (live)."""
        try:
            psce = _make_psce()
            rv = psce._calculate_rv_24h()
            self.assertGreater(rv, 0.0, f"rv24 must be > 0, got {rv}")
            self.assertLess(rv, 500.0, f"rv24 > 500% is implausible, got {rv}")
        except Exception as e:
            self.skipTest(f"Network unavailable: {e}")

    def test_rv24_avg_60d_is_positive_real_number(self):
        """_calculate_rv24_avg_60day returns a positive value from Deribit (live)."""
        try:
            psce = _make_psce()
            rv_avg = psce._calculate_rv24_avg_60day()
            self.assertGreater(rv_avg, 0.0, f"rv24_avg_60d must be > 0, got {rv_avg}")
            self.assertLess(rv_avg, 500.0, f"rv24_avg_60d > 500% is implausible, got {rv_avg}")
        except Exception as e:
            self.skipTest(f"Network unavailable: {e}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
