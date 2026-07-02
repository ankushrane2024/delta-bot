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
        context = PositionContext(total_lots=100, is_valid=True)
        result = self.engine.evaluate(self.dummy_regime, self.dummy_trend, context)
        
        self.assertIsInstance(result, PositionRiskResult)
        self.assertIsNotNone(result.evaluation_id)
        self.assertTrue(result.execution_time_ms >= 0)
        self.assertEqual(result.confidence, 100.0)
        self.assertEqual(result.debug_information["total_lots"], 100)
        
        health = self.engine.health()
        self.assertTrue(health.last_execution_time > 0)
        self.assertEqual(len(health.warnings), 0)

    def test_evaluate_invalid_context(self):
        context = PositionContext(total_lots=500, is_valid=False)
        result = self.engine.evaluate(self.dummy_regime, self.dummy_trend, context)
        
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.debug_information["total_lots"], 500)
        
        health = self.engine.health()
        self.assertEqual(len(health.warnings), 1)
        self.assertIn("invalid", health.warnings[0].lower())

    def test_reset(self):
        context = PositionContext(is_valid=False)
        self.engine.evaluate(self.dummy_regime, self.dummy_trend, context)
        
        self.assertEqual(len(self.engine._warnings), 1)
        self.engine.reset()
        self.assertEqual(len(self.engine._warnings), 0)

if __name__ == "__main__":
    unittest.main()
