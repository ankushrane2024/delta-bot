import unittest
from hedge.engines.execution_engine import ExecutionEngine
from hedge.models.execution import ExecutionResult, ExecutionStatus, ExecutionState
from hedge.models.hedge import HedgePlan
from hedge.models.decision import AresDecision

class TestExecutionEngine(unittest.TestCase):
    def setUp(self):
        from hedge.models.events import EventBus
        self.event_bus = EventBus()
        self.engine = ExecutionEngine(event_bus=self.event_bus)
        self.engine.initialize()
        
        self.valid_plan = HedgePlan(
            hedge_id="test_plan",
            action=AresDecision.OPEN_HEDGE,
            side="SHORT",
            quantity=0.1,
            execution_priority=1,
            execution_style="AGGRESSIVE",
            estimated_post_hedge_delta=0.0,
            hedge_reason="Test",
            urgency=100.0,
            timestamp=0.0,
            warnings=[]
        )

    def test_initialization_and_metadata(self):
        meta = self.engine.metadata()
        self.assertEqual(meta["name"], "ExecutionEngine")
        self.assertEqual(meta["provider"], "None")
        
        health = self.engine.health()
        self.assertFalse(health.replay_mode)
        # 0 loaded evaluators because no provider is injected
        self.assertEqual(health.loaded_evaluators, 0)

    def test_missing_or_hold_plan(self):
        result_none = self.engine.evaluate(None)
        self.assertIsNone(result_none)
        
        missing_action = HedgePlan(
            hedge_id="missing_action_id",
            action=AresDecision.HOLD,
            side="NONE",
            quantity=0.0,
            execution_priority=1,
            execution_style="AGGRESSIVE",
            estimated_post_hedge_delta=0.0,
            hedge_reason="",
            urgency=0.0,
            timestamp=0.0,
            warnings=[]
        )
        
        result_missing = self.engine.evaluate(missing_action)
        self.assertIsNone(result_missing)

    def test_invalid_plan(self):
        invalid_plan = HedgePlan(
            hedge_id="invalid_id",
            action=AresDecision.OPEN_HEDGE,
            side="NONE",
            quantity=0.0,
            execution_priority=1,
            execution_style="AGGRESSIVE",
            estimated_post_hedge_delta=0.0,
            hedge_reason="",
            urgency=0.0,
            timestamp=0.0,
            warnings=[]
        )
        
        result = self.engine.evaluate(invalid_plan)
        
        self.assertIsNotNone(result)
        self.assertEqual(result.execution_status, ExecutionStatus.CANCELLED)
        self.assertFalse(result.validation_result)
        
        health = self.engine.health()
        self.assertEqual(len(health.warnings), 0)

    def test_valid_plan_execution(self):
        result = self.engine.evaluate(self.valid_plan)
        
        self.assertIsNotNone(result)
        self.assertEqual(result.execution_status, ExecutionStatus.SUBMITTED)
        self.assertTrue(result.validation_result)
        self.assertEqual(len(result.created_orders), 1)
        
        order = result.created_orders[0]
        self.assertEqual(order.state, ExecutionState.QUEUED)
        self.assertEqual(order.quantity, 0.1)
        
        health = self.engine.health()
        self.assertEqual(len(health.warnings), 0)

if __name__ == "__main__":
    unittest.main()
