import unittest
from hedge.engines.regime_engine import MarketRegimeEngine
from hedge.models.trend import TrendResult
from hedge.models.enums import MarketRegime, TrendDirection

class TestMarketRegimeEngine(unittest.TestCase):
    def setUp(self):
        self.engine = MarketRegimeEngine()
        self.engine.initialize()
        
        # Helper to generate a dummy trend result with forced regime
        def make_trend_result(forced_regime: MarketRegime) -> TrendResult:
            return TrendResult(
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
                timestamp="2026-07-02T00:00:00Z",
                started_at=0.0,
                completed_at=0.0,
                execution_time_ms=0.0,
                explanation="test",
                supporting_evidence=[],
                analyzer_health_summary={},
                debug_information={"force_regime": forced_regime}
            )
        self.make_trend_result = make_trend_result

    def test_initialization_and_metadata(self):
        meta = self.engine.metadata()
        self.assertEqual(meta["name"], "MarketRegimeEngine")
        self.assertEqual(meta["current_regime"], "SAFE_RANGE")
        self.assertEqual(meta["transitions_recorded"], 0)
        
        health = self.engine.health()
        self.assertFalse(health.replay_mode)
        self.assertEqual(health.failed_evaluators, 0)

    def test_valid_transitions(self):
        # Initial is SAFE_RANGE -> WEAK_RANGE (Allowed)
        result = self.engine.evaluate(self.make_trend_result(MarketRegime.WEAK_RANGE))
        self.assertTrue(result.transition_allowed)
        self.assertEqual(result.current_regime, MarketRegime.WEAK_RANGE)
        self.assertEqual(result.previous_regime, MarketRegime.SAFE_RANGE)
        
        # WEAK_RANGE -> TRANSITION (Allowed)
        result = self.engine.evaluate(self.make_trend_result(MarketRegime.TRANSITION))
        self.assertTrue(result.transition_allowed)
        self.assertEqual(result.current_regime, MarketRegime.TRANSITION)
        self.assertEqual(result.previous_regime, MarketRegime.WEAK_RANGE)
        
        # TRANSITION -> EARLY_TREND (Allowed)
        result = self.engine.evaluate(self.make_trend_result(MarketRegime.EARLY_TREND))
        self.assertTrue(result.transition_allowed)
        self.assertEqual(result.current_regime, MarketRegime.EARLY_TREND)
        
        # Verify history recorded all transitions
        self.assertEqual(len(self.engine.transition_history), 3)

    def test_invalid_transitions(self):
        # Initial is SAFE_RANGE -> ACCELERATION (NOT Allowed)
        result = self.engine.evaluate(self.make_trend_result(MarketRegime.ACCELERATION))
        self.assertFalse(result.transition_allowed)
        self.assertEqual(result.current_regime, MarketRegime.SAFE_RANGE)
        self.assertIsNone(result.previous_regime)
        
        # History recorded the rejected transition
        self.assertEqual(len(self.engine.transition_history), 1)
        record = self.engine.transition_history[0]
        self.assertFalse(record.accepted)
        self.assertEqual(record.requested_regime, MarketRegime.ACCELERATION)
        
        # Warnings populated
        health = self.engine.health()
        self.assertEqual(len(health.warnings), 1)
        self.assertIn("Invalid transition", health.warnings[0])

    def test_reset(self):
        self.engine.evaluate(self.make_trend_result(MarketRegime.WEAK_RANGE))
        self.assertEqual(self.engine.current_regime, MarketRegime.WEAK_RANGE)
        self.assertEqual(len(self.engine.transition_history), 1)
        
        self.engine.reset()
        self.assertEqual(self.engine.current_regime, MarketRegime.SAFE_RANGE)
        self.assertEqual(len(self.engine.transition_history), 0)

if __name__ == "__main__":
    unittest.main()
