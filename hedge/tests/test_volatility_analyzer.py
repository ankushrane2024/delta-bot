import unittest
from hedge.analyzers.volatility_analyzer import VolatilityAnalyzer
from hedge.analyzers.evaluators.volatility_interfaces import ExpansionEvaluator, CompressionEvaluator
from hedge.context.market_context import MarketContext
from hedge.models.volatility import VolatilityResult
from hedge.models.shared import SignalEvidence
from hedge.analyzers.evaluators.base_volatility_evaluator import AbstractVolatilityEvaluator

class FailingVolatilityEvaluator(AbstractVolatilityEvaluator):
    def evaluate(self, context: MarketContext) -> SignalEvidence:
        raise ValueError("Simulated Volatility evaluator crash")

class TestVolatilityAnalyzer(unittest.TestCase):
    def setUp(self):
        self.context = MarketContext(current_price=60000.0)

    def test_initialization_and_metadata(self):
        evaluators = [ExpansionEvaluator(), CompressionEvaluator()]
        analyzer = VolatilityAnalyzer(evaluators=evaluators)
        analyzer.initialize()
        
        meta = analyzer.metadata()
        self.assertEqual(meta["name"], "VolatilityAnalyzer")
        self.assertEqual(len(meta["evaluators"]), 2)
        
        health = analyzer.health()
        self.assertEqual(health.loaded_evaluators, 2)
        self.assertEqual(health.failed_evaluators, 0)
        self.assertFalse(health.replay_mode)

    def test_evaluate_success(self):
        evaluators = [ExpansionEvaluator()]
        analyzer = VolatilityAnalyzer(evaluators=evaluators)
        
        result = analyzer.evaluate(self.context)
        
        self.assertIsInstance(result, VolatilityResult)
        self.assertIsNotNone(result.evaluation_id)
        self.assertTrue(result.execution_time_ms >= 0)
        self.assertEqual(len(result.supporting_evidence), 1)
        self.assertEqual(result.supporting_evidence[0].source, "ExpansionEvaluator")
        
        health = analyzer.health()
        self.assertTrue(health.last_execution_time > 0)
        self.assertEqual(health.failed_evaluators, 0)

    def test_isolated_failures(self):
        evaluators = [ExpansionEvaluator(), FailingVolatilityEvaluator(), CompressionEvaluator()]
        analyzer = VolatilityAnalyzer(evaluators=evaluators)
        
        result = analyzer.evaluate(self.context)
        
        # Should not crash. Should aggregate the 2 successful evaluators.
        self.assertEqual(len(result.supporting_evidence), 2)
        
        health = analyzer.health()
        self.assertEqual(health.failed_evaluators, 1)
        self.assertEqual(len(health.warnings), 1)
        self.assertIn("Simulated Volatility evaluator crash", health.warnings[0])

if __name__ == "__main__":
    unittest.main()
