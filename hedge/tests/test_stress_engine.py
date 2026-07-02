import unittest
from hedge.engines.stress_engine import OptionStressEngine
from hedge.models.stress import OptionStressResult
from hedge.models.trend import TrendResult
from hedge.models.regime import MarketRegimeResult
from hedge.models.position import PositionRiskResult
from hedge.context.position_context import PositionContext
from hedge.models.enums import MarketRegime, TrendDirection

class TestOptionStressEngine(unittest.TestCase):
    def setUp(self):
        self.engine = OptionStressEngine()
        self.engine.initialize()
        
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
        
        self.dummy_risk = PositionRiskResult(
            evaluation_id="test",
            overall_risk_score=0.0,
            call_side_risk=0.0,
            put_side_risk=0.0,
            delta_exposure=0.0,
            gamma_exposure=0.0,
            theta_exposure=0.0,
            vega_exposure=0.0,
            stop_loss_proximity=0.0,
            portfolio_heat=0.0,
            hedge_urgency=0.0,
            confidence=100.0,
            timestamp="",
            started_at=0.0,
            completed_at=0.0,
            execution_time_ms=0.0,
            explanation="",
            debug_information={}
        )
        
        self.dummy_context = PositionContext(is_valid=True)

    def test_initialization_and_metadata(self):
        meta = self.engine.metadata()
        self.assertEqual(meta["name"], "OptionStressEngine")
        
        health = self.engine.health()
        self.assertFalse(health.replay_mode)
        self.assertEqual(health.failed_evaluators, 0)

    def test_evaluate_success_valid_context(self):
        result = self.engine.evaluate(self.dummy_trend, self.dummy_regime, self.dummy_risk, self.dummy_context)
        
        self.assertIsInstance(result, OptionStressResult)
        self.assertIsNotNone(result.evaluation_id)
        self.assertTrue(result.execution_time_ms >= 0)
        self.assertEqual(result.confidence, 100.0)
        
        health = self.engine.health()
        self.assertTrue(health.last_execution_time > 0)
        self.assertEqual(len(health.warnings), 0)

    def test_evaluate_invalid_context(self):
        invalid_context = PositionContext(is_valid=False)
        result = self.engine.evaluate(self.dummy_trend, self.dummy_regime, self.dummy_risk, invalid_context)
        
        self.assertEqual(result.confidence, 0.0)
        
        health = self.engine.health()
        self.assertEqual(len(health.warnings), 1)
        self.assertIn("invalid", health.warnings[0].lower())

    def test_missing_inputs(self):
        result = self.engine.evaluate(None, self.dummy_regime, self.dummy_risk, self.dummy_context)
        
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("Emergency", result.explanation)
        
        health = self.engine.health()
        self.assertEqual(len(health.warnings), 1)
        self.assertIn("Missing", health.warnings[0])

    def test_reset(self):
        invalid_context = PositionContext(is_valid=False)
        self.engine.evaluate(self.dummy_trend, self.dummy_regime, self.dummy_risk, invalid_context)
        
        self.assertEqual(len(self.engine._warnings), 1)
        self.engine.reset()
        self.assertEqual(len(self.engine._warnings), 0)

if __name__ == "__main__":
    unittest.main()
