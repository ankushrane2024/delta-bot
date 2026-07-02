import unittest
from hedge.engines.trend_engine import TrendEngine
from hedge.engines.base_engine import AbstractBaseEngine
from hedge.context.market_context import MarketContext
from hedge.models.trend import TrendResult
from hedge.models.enums import TrendDirection
from hedge.models.shared import AnalyzerHealth

class DummyAnalyzer(AbstractBaseEngine):
    def initialize(self) -> None:
        pass
    def evaluate(self, context: MarketContext):
        return {"dummy_field": 100}
    def reset(self) -> None:
        pass
    def health(self) -> AnalyzerHealth:
        return AnalyzerHealth(1, 0, [], False, 1.0)
    def metadata(self):
        return {"name": "DummyAnalyzer"}

class FailingAnalyzer(AbstractBaseEngine):
    def initialize(self) -> None:
        pass
    def evaluate(self, context: MarketContext):
        raise ValueError("Simulated analyzer crash")
    def reset(self) -> None:
        pass
    def health(self) -> AnalyzerHealth:
        return AnalyzerHealth(1, 1, ["Crash"], False, 1.0)
    def metadata(self):
        return {"name": "FailingAnalyzer"}

class TestTrendEngine(unittest.TestCase):
    def setUp(self):
        self.context = MarketContext(current_price=60000.0)

    def test_initialization_and_metadata(self):
        analyzers = {"dummy": DummyAnalyzer()}
        engine = TrendEngine(analyzers=analyzers)
        engine.initialize()
        
        meta = engine.metadata()
        self.assertEqual(meta["name"], "TrendEngine")
        self.assertIn("dummy", meta["analyzers"])
        
        health = engine.health()
        self.assertEqual(health.loaded_evaluators, 1)

    def test_evaluate_success(self):
        analyzers = {"dummy1": DummyAnalyzer(), "dummy2": DummyAnalyzer()}
        engine = TrendEngine(analyzers=analyzers)
        
        result = engine.evaluate(self.context)
        
        self.assertIsInstance(result, TrendResult)
        self.assertIsNotNone(result.evaluation_id)
        self.assertTrue(result.execution_time_ms >= 0)
        self.assertEqual(len(result.supporting_signals), 2)
        self.assertEqual(result.signal_reliability, 100.0)
        self.assertEqual(result.trend_direction, TrendDirection.NONE)
        
        # Test analyzer health summary was populated
        self.assertIn("dummy1", result.analyzer_health_summary)
        self.assertEqual(result.analyzer_health_summary["dummy1"]["failed_evaluators"], 0)

    def test_isolated_failures(self):
        analyzers = {"dummy1": DummyAnalyzer(), "failing": FailingAnalyzer()}
        engine = TrendEngine(analyzers=analyzers)
        
        result = engine.evaluate(self.context)
        
        # Should not crash. Should aggregate the 1 successful analyzer.
        self.assertEqual(len(result.supporting_signals), 1)
        self.assertIn("dummy1", result.supporting_signals)
        self.assertNotIn("failing", result.supporting_signals)
        
        # Reliability should drop to 50%
        self.assertEqual(result.signal_reliability, 50.0)
        
        # Health summary should capture the error
        self.assertIn("error", result.analyzer_health_summary["failing"])
        
        health = engine.health()
        self.assertEqual(health.failed_evaluators, 1)
        self.assertEqual(len(health.warnings), 1)
        self.assertIn("Simulated analyzer crash", health.warnings[0])

    def test_missing_analyzers(self):
        engine = TrendEngine()
        result = engine.evaluate(self.context)
        
        # Should gracefully return defaults without crashing, with reliability 0
        self.assertEqual(len(result.supporting_signals), 0)
        self.assertEqual(result.signal_reliability, 0.0)
        
        health = engine.health()
        self.assertEqual(len(health.warnings), 1)
        self.assertIn("ZERO injected analyzers", health.warnings[0])

if __name__ == "__main__":
    unittest.main()
