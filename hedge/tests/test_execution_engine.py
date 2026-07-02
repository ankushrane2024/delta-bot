import unittest
from hedge.engines.execution_engine import ExecutionEngine
from hedge.models.execution import ExecutionResult, ExecutionStatus
from hedge.models.hedge import HedgePlan, HedgeSide
from hedge.models.decision import AresDecision

class TestExecutionEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ExecutionEngine()
        self.engine.initialize()
        
        self.valid_plan = HedgePlan(
            hedge_action=AresDecision.OPEN_HEDGE,
            hedge_side=HedgeSide.SHORT,
            hedge_ratio=1.0,
            hedge_quantity=0.1,
            hedge_reason="Test",
            urgency=100.0,
            confidence=100.0,
            execution_priority=1,
            hedge_id="test_hedge_1",
            linked_position_id=None,
            timestamp="",
            explanation="test",
            started_at=0.0,
            completed_at=0.0,
            execution_time_ms=0.0,
            debug_information={}
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
        
        hold_plan = HedgePlan(
            hedge_action=AresDecision.HOLD,
            hedge_side=HedgeSide.NONE,
            hedge_ratio=0.0,
            hedge_quantity=0.0,
            hedge_reason="",
            urgency=0.0,
            confidence=0.0,
            execution_priority=0,
            hedge_id="hold_1",
            linked_position_id=None,
            timestamp="",
            explanation="",
            started_at=0.0,
            completed_at=0.0,
            execution_time_ms=0.0,
            debug_information={}
        )
        
        result_hold = self.engine.evaluate(hold_plan)
        self.assertIsNone(result_hold)

    def test_invalid_plan(self):
        invalid_plan = HedgePlan(
            hedge_action=AresDecision.OPEN_HEDGE,
            hedge_side=HedgeSide.NONE, # Invalid
            hedge_ratio=1.0,
            hedge_quantity=0.0, # Invalid
            hedge_reason="",
            urgency=0.0,
            confidence=0.0,
            execution_priority=0,
            hedge_id="invalid_1",
            linked_position_id=None,
            timestamp="",
            explanation="",
            started_at=0.0,
            completed_at=0.0,
            execution_time_ms=0.0,
            debug_information={}
        )
        
        result = self.engine.evaluate(invalid_plan)
        
        self.assertIsNotNone(result)
        self.assertEqual(result.execution_status, ExecutionStatus.FAILED)
        self.assertFalse(result.validation_result)
        
        health = self.engine.health()
        self.assertEqual(len(health.warnings), 2)
        self.assertIn("Hedge quantity", health.warnings[0])
        self.assertIn("Hedge side", health.warnings[1])

    def test_valid_plan_execution(self):
        result = self.engine.evaluate(self.valid_plan)
        
        self.assertIsNotNone(result)
        self.assertEqual(result.execution_status, ExecutionStatus.FILLED)
        self.assertTrue(result.validation_result)
        self.assertEqual(len(result.created_orders), 1)
        
        order = result.created_orders[0]
        self.assertEqual(order.side, "SHORT")
        self.assertEqual(order.quantity, 0.1)
        self.assertEqual(order.status, "FILLED")
        
        health = self.engine.health()
        self.assertEqual(len(health.warnings), 0)

if __name__ == "__main__":
    unittest.main()
