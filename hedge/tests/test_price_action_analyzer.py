import unittest
from hedge.analyzers.price_action_analyzer import PriceActionAnalyzer
from hedge.analyzers.evaluators.interfaces import CandleEvaluator, SwingEvaluator
from hedge.context.market_context import MarketContext
from hedge.models.price_action import PriceActionResult, PriceActionEvidence
from hedge.analyzers.evaluators.base_evaluator import AbstractPriceEvaluator

class FailingEvaluator(AbstractPriceEvaluator):
    def evaluate(self, context: MarketContext) -> PriceActionEvidence:
        raise ValueError("Simulated evaluator crash")

class TestPriceActionAnalyzer(unittest.TestCase):
    def setUp(self):
        self.context = MarketContext(current_price=60000.0)

    def test_initialization_and_metadata(self):
        evaluators = [CandleEvaluator(), SwingEvaluator()]
        analyzer = PriceActionAnalyzer(evaluators=evaluators)
        analyzer.initialize()
        
        meta = analyzer.metadata()
        self.assertEqual(meta["name"], "PriceActionAnalyzer")
        self.assertEqual(len(meta["evaluators"]), 2)
        
        health = analyzer.health()
        self.assertEqual(health.loaded_evaluators, 2)
        self.assertEqual(health.failed_evaluators, 0)
        self.assertFalse(health.replay_mode)

    def test_evaluate_success(self):
        evaluators = [CandleEvaluator()]
        analyzer = PriceActionAnalyzer(evaluators=evaluators)
        
        result = analyzer.evaluate(self.context)
        
        self.assertIsInstance(result, PriceActionResult)
        self.assertIsNotNone(result.evaluation_id)
        self.assertTrue(result.execution_time_ms >= 0)
        self.assertEqual(len(result.supporting_evidence), 1)
        self.assertEqual(result.supporting_evidence[0].source, "CandleEvaluator")
        
        health = analyzer.health()
        self.assertTrue(health.last_execution_time > 0)
        self.assertEqual(health.failed_evaluators, 0)

    def test_isolated_failures(self):
        evaluators = [CandleEvaluator(), FailingEvaluator(), SwingEvaluator()]
        analyzer = PriceActionAnalyzer(evaluators=evaluators)
        
        result = analyzer.evaluate(self.context)
        
        # Should not crash. Should aggregate the 2 successful evaluators.
        self.assertEqual(len(result.supporting_evidence), 2)
        
        health = analyzer.health()
        self.assertEqual(health.failed_evaluators, 1)
        self.assertEqual(len(health.warnings), 1)
        self.assertIn("Simulated evaluator crash", health.warnings[0])

if __name__ == "__main__":
    unittest.main()
