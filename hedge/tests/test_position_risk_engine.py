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

    def test_premium_growth_factor(self):
        # Hill Equation: Score = 100 * (growth^3) / (1.0^3 + growth^3)
        # 1. No premium increase
        score_0 = self.engine._compute_premium_growth_factor(100.0, 100.0) # growth = 0
        self.assertEqual(score_0, 0.0)
        
        score_decay = self.engine._compute_premium_growth_factor(80.0, 100.0) # decay, growth = 0
        self.assertEqual(score_decay, 0.0)
        
        # 2. 10% increase (growth = 0.1) -> 100 * 0.001 / 1.001 = 0.0999
        score_10 = self.engine._compute_premium_growth_factor(110.0, 100.0)
        self.assertAlmostEqual(score_10, 0.100, places=2)
        
        # 3. 25% increase (growth = 0.25) -> 100 * 0.015625 / 1.015625 = 1.538
        score_25 = self.engine._compute_premium_growth_factor(125.0, 100.0)
        self.assertAlmostEqual(score_25, 1.538, places=2)
        
        # 4. 50% increase (growth = 0.5) -> 100 * 0.125 / 1.125 = 11.111
        score_50 = self.engine._compute_premium_growth_factor(150.0, 100.0)
        self.assertAlmostEqual(score_50, 11.111, places=2)
        
        # 5. 100% increase (growth = 1.0) -> 100 * 1 / 2 = 50.0
        score_100 = self.engine._compute_premium_growth_factor(200.0, 100.0)
        self.assertAlmostEqual(score_100, 50.0, places=2)
        
        # 6. 200% increase (growth = 2.0) -> 100 * 8 / 9 = 88.888
        score_200 = self.engine._compute_premium_growth_factor(300.0, 100.0)
        self.assertAlmostEqual(score_200, 88.889, places=2)
        
        # 7. Extreme premium explosion (growth = 10.0) -> 100 * 1000 / 1001 = 99.9
        score_extreme = self.engine._compute_premium_growth_factor(1100.0, 100.0)
        self.assertAlmostEqual(score_extreme, 99.900, places=2)
        
        # 8. Invalid inputs
        self.assertEqual(self.engine._compute_premium_growth_factor(None, 100.0), 0.0)
        self.assertEqual(self.engine._compute_premium_growth_factor(100.0, None), 0.0)
        self.assertEqual(self.engine._compute_premium_growth_factor(float('nan'), 100.0), 0.0)
        self.assertEqual(self.engine._compute_premium_growth_factor(100.0, 0.0), 0.0)
        self.assertEqual(self.engine._compute_premium_growth_factor(100.0, -50.0), 0.0)
        self.assertEqual(self.engine._compute_premium_growth_factor(float('inf'), 100.0), 0.0)

    def test_iv_expansion_factor(self):
        # Weibull CDF: Score = 100 * (1 - exp(-0.693 * (expansion/1.0)^3))
        # 1. No IV increase
        self.assertEqual(self.engine._compute_iv_expansion_factor(40.0, 40.0), 0.0)
        self.assertEqual(self.engine._compute_iv_expansion_factor(30.0, 40.0), 0.0) # IV drop
        
        # 2. 5% IV increase (expansion = 0.05)
        # exp(-0.693 * 0.05^3) = exp(-0.000086) ~ 1.0 -> score ~ 0.008
        self.assertAlmostEqual(self.engine._compute_iv_expansion_factor(42.0, 40.0), 0.009, places=2)
        
        # 3. 10% IV increase (expansion = 0.10)
        # exp(-0.693 * 0.1^3) = exp(-0.000693) ~ 1.0 -> score ~ 0.069
        self.assertAlmostEqual(self.engine._compute_iv_expansion_factor(44.0, 40.0), 0.069, places=2)
        
        # 4. 25% IV increase (expansion = 0.25)
        # 0.25^3 = 0.0156. exp(-0.693 * 0.0156) = exp(-0.0108) ~ 0.989. Score ~ 1.07
        self.assertAlmostEqual(self.engine._compute_iv_expansion_factor(50.0, 40.0), 1.077, places=2)
        
        # 5. 50% IV increase (expansion = 0.50)
        # 0.5^3 = 0.125. exp(-0.693 * 0.125) = exp(-0.0866). Score ~ 8.3
        self.assertAlmostEqual(self.engine._compute_iv_expansion_factor(60.0, 40.0), 8.300, places=2)
        
        # 6. 100% IV increase (expansion = 1.00)
        self.assertAlmostEqual(self.engine._compute_iv_expansion_factor(80.0, 40.0), 50.0, places=2)
        
        # 7. 150% IV increase (expansion = 1.50)
        # 1.5^3 = 3.375. exp(-0.693 * 3.375) = exp(-2.339). Score ~ 90.36
        self.assertAlmostEqual(self.engine._compute_iv_expansion_factor(100.0, 40.0), 90.363, places=2)
        
        # 8. Extreme volatility shock (expansion = 3.00, i.e. 40 -> 160)
        self.assertAlmostEqual(self.engine._compute_iv_expansion_factor(160.0, 40.0), 100.0, places=2)
        
        # 9. Invalid inputs
        self.assertEqual(self.engine._compute_iv_expansion_factor(None, 40.0), 0.0)
        self.assertEqual(self.engine._compute_iv_expansion_factor(40.0, None), 0.0)
        self.assertEqual(self.engine._compute_iv_expansion_factor(float('nan'), 40.0), 0.0)
        self.assertEqual(self.engine._compute_iv_expansion_factor(40.0, 0.0), 0.0)
        self.assertEqual(self.engine._compute_iv_expansion_factor(40.0, -10.0), 0.0)
        self.assertEqual(self.engine._compute_iv_expansion_factor(float('inf'), 40.0), 0.0)

    def test_trend_factor(self):
        from hedge.models.enums import TrendDirection
        from hedge.models.trend import TrendResult
        import uuid
        
        def create_trend(direction, strength, confidence, continuation):
            return TrendResult(
                evaluation_id=str(uuid.uuid4()),
                trend_direction=direction,
                trend_strength=strength,
                trend_confidence=confidence,
                trend_persistence=50.0,
                trend_acceleration=0.0,
                continuation_probability=continuation,
                reversal_probability=0.0,
                whipsaw_probability=0.0,
                signal_reliability=100.0,
                timestamp="test",
                started_at=0.0,
                completed_at=0.0,
                execution_time_ms=0.0,
                explanation="test"
            )
            
        # 1. No trend / Safe direction
        trend_none = create_trend(TrendDirection.NONE, 80.0, 100.0, 100.0)
        self.assertEqual(self.engine._compute_trend_factor(trend_none, is_call=True), 0.0)
        
        trend_safe = create_trend(TrendDirection.SHORT, 100.0, 100.0, 100.0)
        self.assertEqual(self.engine._compute_trend_factor(trend_safe, is_call=True), 0.0)
        
        # 2. Weak trend (Bullish, Strength 30, max conf/cont)
        # sigmoid(30) with center=60, steepness=0.1 -> raw = 0.0474, normalized ~ 4.589
        trend_weak = create_trend(TrendDirection.LONG, 30.0, 100.0, 100.0)
        score_weak = self.engine._compute_trend_factor(trend_weak, is_call=True)
        self.assertAlmostEqual(score_weak, 4.589, places=2)
        
        # 3. Medium trend (Bullish, Strength 60, max conf/cont) -> exactly 50.8 on raw sigmoid curve
        trend_med = create_trend(TrendDirection.LONG, 60.0, 100.0, 100.0)
        score_med = self.engine._compute_trend_factor(trend_med, is_call=True)
        self.assertAlmostEqual(score_med, 50.79, places=1)
        
        # 4. Strong trend (Bullish, Strength 80, max conf/cont) -> normalized ~ 89.67
        trend_strong = create_trend(TrendDirection.LONG, 80.0, 100.0, 100.0)
        score_strong = self.engine._compute_trend_factor(trend_strong, is_call=True)
        self.assertAlmostEqual(score_strong, 89.67, places=1)
        
        # 5. Extreme trend (Bullish, Strength 100, max conf/cont) -> normalized = 100.0
        trend_extreme = create_trend(TrendDirection.LONG, 100.0, 100.0, 100.0)
        score_extreme = self.engine._compute_trend_factor(trend_extreme, is_call=True)
        self.assertAlmostEqual(score_extreme, 100.0, places=2)
        
        # 6. Low confidence & Low continuation dampens score
        trend_dampened = create_trend(TrendDirection.LONG, 100.0, 50.0, 50.0)
        # max score 100 * dampener ((50+50)/200 = 0.5) = 50.0
        score_dampened = self.engine._compute_trend_factor(trend_dampened, is_call=True)
        self.assertAlmostEqual(score_dampened, 50.0, places=2)
        
        # 7. Invalid TrendResult
        self.assertEqual(self.engine._compute_trend_factor(None, is_call=True), 0.0)
        
        trend_invalid = create_trend(TrendDirection.LONG, float('nan'), 100.0, 100.0)
        self.assertEqual(self.engine._compute_trend_factor(trend_invalid, is_call=True), 0.0)

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
