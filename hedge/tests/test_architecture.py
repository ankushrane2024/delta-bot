import unittest
from hedge.models.enums import MarketRegime
from hedge.models.decision import DecisionResult, AresDecision
from hedge.engines.market_state_engine import MarketStateEngine
from hedge.config.hedge_config import HedgeConfig

class TestArchitecture(unittest.TestCase):
    
    def test_enums_import(self):
        self.assertEqual(MarketRegime.SAFE_RANGE.name, "SAFE_RANGE")
        
    def test_decision_dataclass(self):
        d = DecisionResult(
            evaluation_id="test",
            decision=AresDecision.HOLD,
            confidence=0.9,
            urgency=0.0,
            explanation="Test",
            timestamp="",
            started_at=0.0,
            completed_at=0.0,
            execution_time_ms=0.0,
            supporting_evidence=[],
            debug_information={}
        )
        self.assertEqual(d.decision, AresDecision.HOLD)
        
    def test_engine_initialization(self):
        engine = MarketStateEngine()
        self.assertTrue(engine.health())
        self.assertEqual(engine.metadata()["name"], "MarketStateEngine")

if __name__ == "__main__":
    unittest.main()
