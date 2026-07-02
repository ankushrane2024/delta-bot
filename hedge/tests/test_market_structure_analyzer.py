import unittest
from hedge.analyzers.market_structure_analyzer import MarketStructureAnalyzer
from hedge.analyzers.evaluators.structure_interfaces import StructureBreakEvaluator, HigherHighEvaluator
from hedge.context.market_context import MarketContext
from hedge.models.market_structure import MarketStructureResult
from hedge.models.shared import SignalEvidence
from hedge.analyzers.evaluators.base_structure_evaluator import AbstractStructureEvaluator

class FailingStructureEvaluator(AbstractStructureEvaluator):
    def evaluate(self, context: MarketContext) -> SignalEvidence:
        raise ValueError("Simulated structure evaluator crash")

class TestMarketStructureAnalyzer(unittest.TestCase):
    def setUp(self):
        self.context = MarketContext(current_price=60000.0)

    def test_initialization_and_metadata(self):
        evaluators = [StructureBreakEvaluator(), HigherHighEvaluator()]
        analyzer = MarketStructureAnalyzer(evaluators=evaluators)
        analyzer.initialize()
        
        meta = analyzer.metadata()
        self.assertEqual(meta["name"], "MarketStructureAnalyzer")
        self.assertEqual(len(meta["evaluators"]), 2)
        
        health = analyzer.health()
        self.assertEqual(health.loaded_evaluators, 2)
        self.assertEqual(health.failed_evaluators, 0)
        self.assertFalse(health.replay_mode)

    def test_evaluate_success(self):
        evaluators = [StructureBreakEvaluator()]
        analyzer = MarketStructureAnalyzer(evaluators=evaluators)
        
        result = analyzer.evaluate(self.context)
        
        self.assertIsInstance(result, MarketStructureResult)
        self.assertIsNotNone(result.evaluation_id)
        self.assertTrue(result.execution_time_ms >= 0)
        self.assertEqual(len(result.supporting_evidence), 1)
        self.assertEqual(result.supporting_evidence[0].source, "StructureBreakEvaluator")
        
        health = analyzer.health()
        self.assertTrue(health.last_execution_time > 0)
        self.assertEqual(health.failed_evaluators, 0)

    def test_isolated_failures(self):
        evaluators = [StructureBreakEvaluator(), FailingStructureEvaluator(), HigherHighEvaluator()]
        analyzer = MarketStructureAnalyzer(evaluators=evaluators)
        
        result = analyzer.evaluate(self.context)
        
        # Should not crash. Should aggregate the 2 successful evaluators.
        self.assertEqual(len(result.supporting_evidence), 2)
        
        health = analyzer.health()
        self.assertEqual(health.failed_evaluators, 1)
        self.assertEqual(len(health.warnings), 1)
        self.assertIn("Simulated structure evaluator crash", health.warnings[0])

if __name__ == "__main__":
    unittest.main()
