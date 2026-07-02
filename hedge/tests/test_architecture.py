import unittest
from hedge.models.enums import MarketState
from hedge.models.decision import Decision, DecisionAction
from hedge.engines.market_state_engine import MarketStateEngine
from hedge.config.hedge_config import HedgeConfig

class TestArchitecture(unittest.TestCase):
    
    def test_enums_import(self):
        self.assertEqual(MarketState.SAFE_RANGE.name, "SAFE_RANGE")
        
    def test_decision_dataclass(self):
        d = Decision(
            action=DecisionAction.NO_ACTION,
            confidence=0.9,
            reason="Test",
            metadata={}
        )
        self.assertEqual(d.action, DecisionAction.NO_ACTION)
        
    def test_engine_initialization(self):
        engine = MarketStateEngine()
        self.assertTrue(engine.health())
        self.assertEqual(engine.metadata()["name"], "MarketStateEngine")

if __name__ == "__main__":
    unittest.main()
