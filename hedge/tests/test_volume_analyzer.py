import unittest
from hedge.analyzers.volume_analyzer import VolumeAnalyzer
from hedge.analyzers.evaluators.volume_interfaces import VolumeExpansionEvaluator, ParticipationEvaluator
from hedge.context.market_context import MarketContext
from hedge.models.volume import VolumeResult
from hedge.models.shared import SignalEvidence
from hedge.analyzers.evaluators.base_volume_evaluator import AbstractVolumeEvaluator

class FailingVolumeEvaluator(AbstractVolumeEvaluator):
    def evaluate(self, context: MarketContext) -> SignalEvidence:
        raise ValueError("Simulated Volume evaluator crash")

class TestVolumeAnalyzer(unittest.TestCase):
    def setUp(self):
        self.context = MarketContext(current_price=60000.0)

    def test_initialization_and_metadata(self):
        evaluators = [VolumeExpansionEvaluator(), ParticipationEvaluator()]
        analyzer = VolumeAnalyzer(evaluators=evaluators)
        analyzer.initialize()
        
        meta = analyzer.metadata()
        self.assertEqual(meta["name"], "VolumeAnalyzer")
        self.assertEqual(len(meta["evaluators"]), 2)
        
        health = analyzer.health()
        self.assertEqual(health.loaded_evaluators, 2)
        self.assertEqual(health.failed_evaluators, 0)
        self.assertFalse(health.replay_mode)

    def test_evaluate_success(self):
        evaluators = [VolumeExpansionEvaluator()]
        analyzer = VolumeAnalyzer(evaluators=evaluators)
        
        result = analyzer.evaluate(self.context)
        
        self.assertIsInstance(result, VolumeResult)
        self.assertIsNotNone(result.evaluation_id)
        self.assertTrue(result.execution_time_ms >= 0)
        self.assertEqual(len(result.supporting_evidence), 1)
        self.assertEqual(result.supporting_evidence[0].source, "VolumeExpansionEvaluator")
        
        health = analyzer.health()
        self.assertTrue(health.last_execution_time > 0)
        self.assertEqual(health.failed_evaluators, 0)

    def test_isolated_failures(self):
        evaluators = [VolumeExpansionEvaluator(), FailingVolumeEvaluator(), ParticipationEvaluator()]
        analyzer = VolumeAnalyzer(evaluators=evaluators)
        
        result = analyzer.evaluate(self.context)
        
        # Should not crash. Should aggregate the 2 successful evaluators.
        self.assertEqual(len(result.supporting_evidence), 2)
        
        health = analyzer.health()
        self.assertEqual(health.failed_evaluators, 1)
        self.assertEqual(len(health.warnings), 1)
        self.assertIn("Simulated Volume evaluator crash", health.warnings[0])

if __name__ == "__main__":
    unittest.main()
