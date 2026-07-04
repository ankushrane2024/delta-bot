import unittest
from hedge.engines.position_risk_engine import PositionRiskEngine
from hedge.context.position_context import PositionContext
from hedge.models.position import PositionRiskResult
from hedge.models.trend import TrendResult
from hedge.models.regime import MarketRegimeResult
from hedge.models.enums import MarketRegime, TrendDirection

class TestPositionRiskEngine(unittest.TestCase):
    def setUp(self):
        self.engine = PositionRiskEngine()
        self.engine.initialize()
        
        self.dummy_regime = MarketRegimeResult(
            evaluation_id="test",
            current_regime=MarketRegime.SAFE_RANGE,
            previous_regime=None,
            confidence=100.0,
            transition_reason="",
            transition_allowed=True,
            regime_duration=0.0,
            regime_strength=0.0,
            stability_score=0.0,
            timestamp="",
            debug_information={}
        )
        
        self.dummy_trend = TrendResult(
            evaluation_id="test",
            trend_direction=TrendDirection.NONE,
            trend_strength=0.0,
            trend_confidence=0.0,
            trend_persistence=0.0,
            trend_acceleration=0.0,
            continuation_probability=0.0,
            reversal_probability=0.0,
            whipsaw_probability=0.0,
            signal_reliability=100.0,
            timestamp="",
            started_at=0.0,
            completed_at=0.0,
            execution_time_ms=0.0,
            explanation="",
            supporting_evidence=[],
            analyzer_health_summary={},
            debug_information={}
        )

    def test_initialization_and_metadata(self):
        meta = self.engine.metadata()
        self.assertEqual(meta["name"], "PositionRiskEngine")
        
        health = self.engine.health()
        self.assertFalse(health.replay_mode)
        self.assertEqual(health.failed_evaluators, 0)

    def test_evaluate_success_valid_context(self):
        context = PositionContext(total_lots=100, is_valid=True, futures_price=65000.0, short_call_strike=70000.0)
        result = self.engine.evaluate(self.dummy_regime, self.dummy_trend, context)
        
        self.assertIsInstance(result, PositionRiskResult)
        self.assertIsNotNone(result.evaluation_id)
        self.assertTrue(result.execution_time_ms >= 0)
        self.assertEqual(result.confidence, 100.0)
        self.assertEqual(result.debug_information["total_lots"], 100)
        
        health = self.engine.health()
        self.assertTrue(health.last_execution_time > 0)
        self.assertEqual(len(health.warnings), 0)

    def test_call_stress_breakdown_structure(self):
        self.dummy_context = PositionContext(
            is_valid=True,
            total_lots=1,
            futures_price=65000.0,
            short_call_strike=70000.0
        )
        breakdown = self.engine._compute_call_stress_breakdown(self.dummy_trend, self.dummy_regime, self.dummy_context)
        from hedge.models.position import CallStressBreakdown
        
        # Verify typing and structure
        self.assertIsInstance(breakdown, CallStressBreakdown)
        self.assertIsInstance(breakdown.delta_factor, float)
        self.assertIsInstance(breakdown.gamma_factor, float)
        self.assertIsInstance(breakdown.premium_growth_factor, float)
        self.assertIsInstance(breakdown.explanation, str)
        
        # Verify strike distance factor is populated
        self.assertGreaterEqual(breakdown.strike_distance_factor, 0.0)
        
        # Verify it passes through _compute_call_stress correctly
        stress = self.engine._compute_call_stress(breakdown)
        self.assertEqual(stress, breakdown.final_call_stress)

    def test_strike_distance_factor(self):
        strike = 70000.0
        
        # 1. Far from strike (>10% away)
        # 63000 is 10% away.
        score_far = self.engine._compute_strike_distance_factor(63000.0, strike)
        self.assertTrue(0.0 <= score_far < 10.0)
        
        # 2. Near strike (~3% away)
        # 67900 is 3% away. Should be ~50.
        score_near = self.engine._compute_strike_distance_factor(67900.0, strike)
        self.assertTrue(40.0 < score_near < 60.0)
        
        # 3. At strike (0% away)
        score_at = self.engine._compute_strike_distance_factor(70000.0, strike)
        self.assertTrue(90.0 < score_at <= 100.0)
        
        # 4. Beyond strike
        score_beyond = self.engine._compute_strike_distance_factor(72000.0, strike)
        self.assertTrue(95.0 < score_beyond <= 100.0)
        
        # 5. Output always clamped
        score_extreme_beyond = self.engine._compute_strike_distance_factor(100000.0, strike)
        self.assertEqual(score_extreme_beyond, 100.0)
        
        score_extreme_far = self.engine._compute_strike_distance_factor(30000.0, strike)
        self.assertEqual(score_extreme_far, 0.0)
        
        # 6. Invalid inputs
        score_invalid1 = self.engine._compute_strike_distance_factor(0.0, strike)
        self.assertEqual(score_invalid1, 0.0)
        score_invalid2 = self.engine._compute_strike_distance_factor(60000.0, 0.0)
        self.assertEqual(score_invalid2, 0.0)
        score_invalid3 = self.engine._compute_strike_distance_factor(None, strike)
        self.assertEqual(score_invalid3, 0.0)

    def test_delta_factor(self):
        import math
        
        # 1. Standard delta values
        score_0 = self.engine._compute_delta_factor(0.00)
        self.assertAlmostEqual(score_0, 0.0)
        
        score_10 = self.engine._compute_delta_factor(0.10)
        self.assertAlmostEqual(score_10, 1.1448, places=2)
        
        score_25 = self.engine._compute_delta_factor(0.25)
        self.assertAlmostEqual(score_25, 7.0097, places=2)
        
        score_50 = self.engine._compute_delta_factor(0.50)
        self.assertAlmostEqual(score_50, 50.0)
        
        score_75 = self.engine._compute_delta_factor(0.75)
        self.assertAlmostEqual(score_75, 92.9903, places=2)
        
        score_100 = self.engine._compute_delta_factor(1.00)
        self.assertAlmostEqual(score_100, 100.0)
        
        # 2. Absolute value mapping (short options have negative delta)
        score_neg = self.engine._compute_delta_factor(-0.50)
        self.assertAlmostEqual(score_neg, 50.0)
        
        # 3. Output clamped
        score_extreme = self.engine._compute_delta_factor(1.50)
        self.assertAlmostEqual(score_extreme, 100.0)
        
        # 4. Invalid inputs
        score_invalid1 = self.engine._compute_delta_factor(None)
        self.assertAlmostEqual(score_invalid1, 0.0)
        
        score_invalid2 = self.engine._compute_delta_factor(float('nan'))
        self.assertAlmostEqual(score_invalid2, 0.0)
        
        score_invalid3 = self.engine._compute_delta_factor(float('inf'))
        self.assertAlmostEqual(score_invalid3, 0.0)

    def test_gamma_factor(self):
        import math
        from config import GAMMA_SENSITIVITY_K
        
        # 1. Dormant Gamma (Safely OTM)
        score_0 = self.engine._compute_gamma_factor(0.0)
        self.assertEqual(score_0, 0.0)
        
        score_very_low = self.engine._compute_gamma_factor(0.001)
        self.assertAlmostEqual(score_very_low, 0.0) # practically zero
        
        score_low = self.engine._compute_gamma_factor(GAMMA_SENSITIVITY_K / 5)
        self.assertTrue(0.0 < score_low < 1.0) # Very flat initially
        
        # 2. Gamma approaching ATM (Accelerating)
        score_mid = self.engine._compute_gamma_factor(GAMMA_SENSITIVITY_K)
        # Should be exactly 100 * exp(-1) ≈ 36.78
        self.assertAlmostEqual(score_mid, 36.7879, places=2)
        
        # 3. High Gamma (Pin Risk)
        score_high = self.engine._compute_gamma_factor(GAMMA_SENSITIVITY_K * 2)
        # 100 * exp(-0.5) ≈ 60.65
        self.assertAlmostEqual(score_high, 60.653, places=2)
        
        # 4. Extreme Gamma
        score_extreme = self.engine._compute_gamma_factor(1.0)
        self.assertTrue(90.0 < score_extreme <= 100.0)
        
        # 5. Absolute value handling
        score_neg = self.engine._compute_gamma_factor(-GAMMA_SENSITIVITY_K)
        self.assertAlmostEqual(score_neg, 36.7879, places=2)
        
        # 6. Invalid inputs
        score_invalid1 = self.engine._compute_gamma_factor(None)
        self.assertEqual(score_invalid1, 0.0)
        
        score_invalid2 = self.engine._compute_gamma_factor(float('nan'))
        self.assertEqual(score_invalid2, 0.0)
        
        score_invalid3 = self.engine._compute_gamma_factor(float('inf'))
        self.assertEqual(score_invalid3, 0.0)

    def test_vega_factor(self):
        import math
        from config import VEGA_REFERENCE
        
        v_ref = VEGA_REFERENCE
        
        # 1. Zero Vega
        score_0 = self.engine._compute_vega_factor(0.0)
        self.assertEqual(score_0, 0.0)
        
        # 2. Low Vega
        # e.g., 20% of reference. Ratio = 0.2. 100 * (1 - exp(-0.693 * 0.04)) = 2.73
        score_low = self.engine._compute_vega_factor(v_ref * 0.2)
        self.assertAlmostEqual(score_low, 2.734, places=2)
        
        # 3. Medium Vega
        # e.g., 50% of reference. Ratio = 0.5. 100 * (1 - exp(-0.693 * 0.25)) = 15.91
        score_med = self.engine._compute_vega_factor(v_ref * 0.5)
        self.assertAlmostEqual(score_med, 15.910, places=2)
        
        # 4. Reference Vega (Exactly 50)
        score_ref = self.engine._compute_vega_factor(v_ref)
        self.assertAlmostEqual(score_ref, 50.0, places=2)
        
        # 5. High Vega
        # e.g., 150% of reference. Ratio = 1.5. 100 * (1 - exp(-0.693 * 2.25)) = 78.977
        score_high = self.engine._compute_vega_factor(v_ref * 1.5)
        self.assertAlmostEqual(score_high, 78.977, places=2)
        
        # 6. Extreme Vega
        # e.g., 300% of reference. Ratio = 3.0. 100 * (1 - exp(-0.693 * 9)) = 99.805
        score_extreme = self.engine._compute_vega_factor(v_ref * 3.0)
        self.assertAlmostEqual(score_extreme, 99.805, places=2)
        
        # 7. Asymptotic Boundary (Extreme outlier)
        score_asymptote = self.engine._compute_vega_factor(v_ref * 20.0)
        self.assertAlmostEqual(score_asymptote, 100.0, places=2)
        
        # 8. Negative values (Vega should be treated absolute)
        score_neg = self.engine._compute_vega_factor(-v_ref)
        self.assertAlmostEqual(score_neg, 50.0, places=2)
        
        # 9. Invalid inputs
        score_invalid1 = self.engine._compute_vega_factor(None)
        self.assertEqual(score_invalid1, 0.0)
        
        score_invalid2 = self.engine._compute_vega_factor(float('nan'))
        self.assertEqual(score_invalid2, 0.0)
        
        score_invalid3 = self.engine._compute_vega_factor(float('inf'))
        self.assertEqual(score_invalid3, 0.0)

    def test_evaluate_invalid_context(self):
        context = PositionContext(total_lots=500, is_valid=False, futures_price=65000.0, short_call_strike=70000.0)
        result = self.engine.evaluate(self.dummy_regime, self.dummy_trend, context)
        
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.debug_information["total_lots"], 500)
        
        health = self.engine.health()
        self.assertEqual(len(health.warnings), 1)
        self.assertIn("invalid", health.warnings[0].lower())

    def test_reset(self):
        context = PositionContext(is_valid=False, futures_price=65000.0, short_call_strike=70000.0)
        self.engine.evaluate(self.dummy_regime, self.dummy_trend, context)
        
        self.assertEqual(len(self.engine._warnings), 1)
        self.engine.reset()
        self.assertEqual(len(self.engine._warnings), 0)

if __name__ == "__main__":
    unittest.main()
