import unittest
import time
from hedge.models.core_interfaces import SystemClock
from hedge.models.execution import ExecutionOrder, ExecutionState
from hedge.models.hedge import HedgePlan
from hedge.engines.execution_provider import PaperExecutionProvider
from hedge.engines.state_machine import ExecutionStateMachine
from hedge.engines.health_monitor import HealthMonitor
from hedge.engines.decision_engine import DecisionEngine

class MockFailingProvider(PaperExecutionProvider):
    def submit_order(self, order: ExecutionOrder) -> ExecutionOrder:
        raise Exception("Simulated provider outage")



class TestOperationalHardening(unittest.TestCase):
    def test_circuit_breaker(self):
        clock = SystemClock()
        provider = MockFailingProvider(clock=clock)
        from hedge.models.events import EventBus
        event_bus = EventBus()
        machine = ExecutionStateMachine(provider, event_bus=event_bus, clock=clock, config={
            "CIRCUIT_BREAKER_THRESHOLD": 2,
            "MAX_RETRIES": 3
        })
        
        plan1 = HedgePlan(hedge_id="P1", action="HEDGE_NOW", side="SHORT", quantity=0.1, execution_priority=1, execution_style="MARKET", estimated_post_hedge_delta=0.0, hedge_reason="Test", urgency=1.0, timestamp=0.0, warnings=[])
        
        # Submit first plan - fails once, queues retry
        machine.submit_plan(plan1)
        self.assertEqual(machine._consecutive_failures, 1)
        self.assertFalse(machine._circuit_breaker_tripped)
        
        # Submit second plan - fails again, trips breaker
        plan2 = HedgePlan(hedge_id="P2", action="HEDGE_NOW", side="SHORT", quantity=0.1, execution_priority=1, execution_style="MARKET", estimated_post_hedge_delta=0.0, hedge_reason="Test", urgency=1.0, timestamp=0.0, warnings=[])
        machine.submit_plan(plan2)
        self.assertEqual(machine._consecutive_failures, 2)
        self.assertTrue(machine._circuit_breaker_tripped)
        
        # Third plan should be rejected instantly
        plan3 = HedgePlan(hedge_id="P3", action="HEDGE_NOW", side="SHORT", quantity=0.1, execution_priority=1, execution_style="MARKET", estimated_post_hedge_delta=0.0, hedge_reason="Test", urgency=1.0, timestamp=0.0, warnings=[])
        order = machine.submit_plan(plan3)
        self.assertEqual(order.state, ExecutionState.REJECTED)
        self.assertEqual(order.reason, "Circuit Breaker Tripped")

    def test_health_monitor(self):
        monitor = HealthMonitor()
        self.assertEqual(monitor.get_health(), "YELLOW") # Initialize
        
        monitor.mark_ws_msg()
        monitor.mark_sync()
        self.assertEqual(monitor.get_health(), "GREEN")
        
        monitor.record_error()
        self.assertEqual(monitor.get_health(), "YELLOW")
        
        for _ in range(5):
            monitor.record_error()
        self.assertEqual(monitor.get_health(), "RED")
        
    def test_time_weighted_ema(self):
        engine = DecisionEngine()
        
        from hedge.context.position_context import PositionContext
        from hedge.models.position import StressFusionBreakdown
        
        ctx = PositionContext()
        breakdown = StressFusionBreakdown(
            fused_score=1.0
        )
        
        engine.evaluate(1.0, breakdown, ctx, 0.0, current_time=0.0)
        self.assertEqual(engine._ema_stress, 1.0)
        
        # Feed 0.0 at t=1.0
        engine.evaluate(0.0, breakdown, ctx, 0.0, current_time=1.0)
        ema1 = engine._ema_stress
        
        engine2 = DecisionEngine()
        engine2.evaluate(1.0, breakdown, ctx, 0.0, current_time=0.0)
        # Feed 0.0 at t=60.0 (full decay tau=60)
        engine2.evaluate(0.0, breakdown, ctx, 0.0, current_time=60.0)
        ema2 = engine2._ema_stress
        
        # Time-weighted EMA means ema2 should be much smaller than ema1
        self.assertLess(ema2, ema1)

if __name__ == "__main__":
    unittest.main()
