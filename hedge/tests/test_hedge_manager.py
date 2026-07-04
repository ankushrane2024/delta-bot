import unittest

from hedge.engines.hedge_manager import HedgeManager
from hedge.models.decision import HedgeDecision, HedgeAction
from hedge.models.sizing import HedgeSizingResult
from hedge.context.position_context import PositionContext

class TestHedgeManager(unittest.TestCase):
    def setUp(self):
        self.manager = HedgeManager()
        self.context = PositionContext()

    def test_no_hedge(self):
        decision = HedgeDecision(
            action=HedgeAction.MONITOR,
            urgency=0.0,
            hedge_ratio=0.0,
            reason="Stable",
            dominant_cluster="None",
            dominant_factor="None"
        )
        sizing = HedgeSizingResult(
            target_delta=0.0, current_delta=0.0, delta_to_hedge=0.0,
            hedge_side="NONE", hedge_quantity=0.0, current_hedge_quantity=0.0,
            additional_quantity=0.0, estimated_post_hedge_delta=0.0,
            hedge_reason="Stable", confidence=100.0, warnings=[]
        )
        
        plan = self.manager.evaluate(decision, sizing, self.context, 0.0, [])
        self.assertIsNone(plan)

    def test_full_hedge(self):
        decision = HedgeDecision(
            action=HedgeAction.FULL_HEDGE,
            urgency=0.9,
            hedge_ratio=1.0,
            reason="Gamma",
            dominant_cluster="Directional",
            dominant_factor="gamma"
        )
        sizing = HedgeSizingResult(
            target_delta=0.5, current_delta=-0.5, delta_to_hedge=0.5,
            hedge_side="BUY", hedge_quantity=5.0, current_hedge_quantity=0.0,
            additional_quantity=5.0, estimated_post_hedge_delta=0.5,
            hedge_reason="Gamma", confidence=100.0, warnings=[]
        )
        
        plan = self.manager.evaluate(decision, sizing, self.context, 0.0, [])
        self.assertIsNotNone(plan)
        self.assertEqual(plan.action, "FULL_HEDGE")
        self.assertEqual(plan.side, "BUY")
        self.assertEqual(plan.quantity, 5.0)
        self.assertEqual(plan.execution_priority, 5)
        self.assertEqual(plan.execution_style, "MARKET")

    def test_duplicate_order_prevention(self):
        decision = HedgeDecision(
            action=HedgeAction.FULL_HEDGE,
            urgency=0.9, hedge_ratio=1.0, reason="Gamma",
            dominant_cluster="Directional", dominant_factor="gamma"
        )
        sizing = HedgeSizingResult(
            target_delta=0.5, current_delta=-0.5, delta_to_hedge=0.5,
            hedge_side="BUY", hedge_quantity=5.0, current_hedge_quantity=0.0,
            additional_quantity=5.0, estimated_post_hedge_delta=0.5,
            hedge_reason="Gamma", confidence=100.0, warnings=[]
        )
        
        # Pending orders exist
        plan = self.manager.evaluate(decision, sizing, self.context, 0.0, [{"order_id": "123"}])
        self.assertIsNone(plan)
        self.assertIn("prevent duplicates", self.manager._warnings[0])

    def test_emergency_hedge_override(self):
        decision = HedgeDecision(
            action=HedgeAction.EMERGENCY_HEDGE,
            urgency=1.0, hedge_ratio=1.0, reason="Crash",
            dominant_cluster="Directional", dominant_factor="gamma"
        )
        sizing = HedgeSizingResult(
            target_delta=0.5, current_delta=-0.5, delta_to_hedge=0.5,
            hedge_side="BUY", hedge_quantity=5.0, current_hedge_quantity=0.0,
            additional_quantity=5.0, estimated_post_hedge_delta=0.5,
            hedge_reason="Crash", confidence=100.0, warnings=[]
        )
        
        # Pending orders exist, but EMERGENCY_HEDGE overrides
        plan = self.manager.evaluate(decision, sizing, self.context, 0.0, [{"order_id": "123"}])
        self.assertIsNotNone(plan)
        self.assertEqual(plan.action, "EMERGENCY_HEDGE")
        self.assertEqual(plan.execution_priority, 10)
        self.assertIn("Bypassing pending order checks", plan.warnings[0])

    def test_already_hedged(self):
        decision = HedgeDecision(
            action=HedgeAction.FULL_HEDGE,
            urgency=0.9, hedge_ratio=1.0, reason="Gamma",
            dominant_cluster="Directional", dominant_factor="gamma"
        )
        sizing = HedgeSizingResult(
            target_delta=0.5, current_delta=-0.5, delta_to_hedge=0.0,
            hedge_side="NONE", hedge_quantity=5.0, current_hedge_quantity=5.0,
            additional_quantity=0.0, estimated_post_hedge_delta=0.5,
            hedge_reason="Gamma", confidence=100.0, warnings=[]
        )
        
        # Additional quantity is 0
        plan = self.manager.evaluate(decision, sizing, self.context, 5.0, [])
        self.assertIsNone(plan)

    def test_dehedge(self):
        decision = HedgeDecision(
            action=HedgeAction.DEHEDGE,
            urgency=0.1, hedge_ratio=0.0, reason="Recovered",
            dominant_cluster="None", dominant_factor="None"
        )
        sizing = HedgeSizingResult(
            target_delta=0.0, current_delta=-0.5, delta_to_hedge=-0.5,
            hedge_side="SELL", hedge_quantity=0.0, current_hedge_quantity=5.0,
            additional_quantity=5.0, estimated_post_hedge_delta=0.0,
            hedge_reason="Recovered", confidence=100.0, warnings=[]
        )
        
        plan = self.manager.evaluate(decision, sizing, self.context, 5.0, [])
        self.assertIsNotNone(plan)
        self.assertEqual(plan.action, "DEHEDGE")
        self.assertEqual(plan.side, "SELL")
        self.assertEqual(plan.quantity, 5.0) # Quantity to sell
        self.assertEqual(plan.execution_priority, 2)

if __name__ == '__main__':
    unittest.main()
