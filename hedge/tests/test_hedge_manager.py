import unittest
from hedge.engines.hedge_manager import HedgeManager
from hedge.models.hedge import HedgePlan, HedgeSide
from hedge.models.decision import DecisionResult, AresDecision
from hedge.context.position_context import PositionContext
from hedge.models.enums import HedgeState

class TestHedgeManager(unittest.TestCase):
    def setUp(self):
        self.manager = HedgeManager()
        self.manager.initialize()
        
        self.dummy_context = PositionContext(is_valid=True)

    def test_initialization_and_metadata(self):
        meta = self.manager.metadata()
        self.assertEqual(meta["name"], "HedgeManager")
        self.assertEqual(meta["current_state"], "NOT_ACTIVE")
        self.assertIsNone(meta["active_hedge"])
        
        health = self.manager.health()
        self.assertFalse(health.replay_mode)
        self.assertEqual(health.failed_evaluators, 0)

    def test_hold_creates_no_hedge(self):
        decision = DecisionResult(
            evaluation_id="test",
            decision=AresDecision.HOLD,
            confidence=100.0,
            urgency=0.0,
            explanation="Holding",
            timestamp="",
            started_at=0.0,
            completed_at=0.0,
            execution_time_ms=0.0,
            supporting_evidence=[],
            debug_information={}
        )
        
        plan = self.manager.evaluate(decision, self.dummy_context)
        self.assertIsNone(plan)
        
        health = self.manager.health()
        self.assertEqual(len(health.warnings), 0)

    def test_open_hedge_creates_plan(self):
        decision = DecisionResult(
            evaluation_id="test",
            decision=AresDecision.OPEN_HEDGE,
            confidence=100.0,
            urgency=80.0,
            explanation="Opening hedge",
            timestamp="",
            started_at=0.0,
            completed_at=0.0,
            execution_time_ms=0.0,
            supporting_evidence=[],
            debug_information={}
        )
        
        plan = self.manager.evaluate(decision, self.dummy_context)
        
        self.assertIsNotNone(plan)
        self.assertIsInstance(plan, HedgePlan)
        self.assertEqual(plan.hedge_action, AresDecision.OPEN_HEDGE)
        self.assertEqual(plan.urgency, 80.0)
        self.assertEqual(plan.execution_priority, 1) # Because urgency > 50 in our placeholder logic
        self.assertIsNotNone(plan.hedge_id)

    def test_missing_inputs(self):
        plan = self.manager.evaluate(None, self.dummy_context)
        self.assertIsNone(plan)
        
        health = self.manager.health()
        self.assertEqual(len(health.warnings), 1)
        self.assertIn("Missing", health.warnings[0])

    def test_reset(self):
        self.manager.current_hedge_state = HedgeState.ACTIVE
        self.manager.active_hedge_id = "test_123"
        
        self.manager.reset()
        
        self.assertEqual(self.manager.current_hedge_state, HedgeState.NOT_ACTIVE)
        self.assertIsNone(self.manager.active_hedge_id)

if __name__ == "__main__":
    unittest.main()
