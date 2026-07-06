import unittest
from hedge.models.enums import ExecutionState, AresDecision, HedgeSide
from hedge.models.hedge import HedgePlan
from hedge.models.core_interfaces import ReplayClock, InMemoryExecutionStore
from hedge.engines.execution_provider import PaperExecutionProvider
from hedge.engines.state_machine import ExecutionStateMachine, InvalidStateTransitionError
import time

class TestExecutionStateMachine(unittest.TestCase):
    def setUp(self):
        self.clock = ReplayClock(start_time=1000.0)
        self.provider = PaperExecutionProvider(clock=self.clock)
        self.provider.initialize()
        self.store = InMemoryExecutionStore()
        
        from hedge.models.events import EventBus
        self.event_bus = EventBus()
        self.machine = ExecutionStateMachine(
            provider=self.provider,
            event_bus=self.event_bus,
            store=self.store,
            clock=self.clock,
            replay_mode=True
        )
        
    def _make_plan(self, hedge_id="plan_1", qty=1.0) -> HedgePlan:
        plan = HedgePlan(
            hedge_id=hedge_id,
            action="OPEN_HEDGE",
            side="SHORT",
            quantity=qty,
            execution_priority=10,
            execution_style="MARKET",
            estimated_post_hedge_delta=0.0,
            hedge_reason="Test",
            urgency=100.0,
            timestamp=123456789.0,
            warnings=[]
        )
        return plan

    def test_successful_execution(self):
        plan = self._make_plan("plan_success", 2.5)
        order = self.machine.submit_plan(plan)
        
        self.assertEqual(order.state, ExecutionState.ACKNOWLEDGED)
        self.assertEqual(order.quantity, 2.5)
        self.assertEqual(order.remaining_quantity, 2.5)
        
        # Simulate full fill
        self.provider.simulate_fill(order.client_order_id, 2.5, 60000.0)
        
        # Pull update
        reconciled = self.machine.reconcile_order(order.client_order_id)
        self.assertEqual(reconciled.state, ExecutionState.FILLED)
        self.assertEqual(reconciled.filled_quantity, 2.5)
        self.assertEqual(reconciled.remaining_quantity, 0.0)
        self.assertEqual(len(reconciled.fill_events), 1)

    def test_partial_fill_replay(self):
        plan = self._make_plan("plan_partial", 5.0)
        order = self.machine.submit_plan(plan)
        
        # 1st fill: 2.0
        self.clock.tick(1.0)
        self.provider.simulate_fill(order.client_order_id, 2.0, 60000.0)
        reconciled = self.machine.reconcile_order(order.client_order_id)
        
        self.assertEqual(reconciled.state, ExecutionState.PARTIALLY_FILLED)
        self.assertEqual(reconciled.filled_quantity, 2.0)
        self.assertEqual(reconciled.remaining_quantity, 3.0)
        
        # 2nd fill: 3.0
        self.clock.tick(1.0)
        self.provider.simulate_fill(order.client_order_id, 3.0, 60100.0)
        reconciled = self.machine.reconcile_order(order.client_order_id)
        
        self.assertEqual(reconciled.state, ExecutionState.FILLED)
        self.assertEqual(reconciled.filled_quantity, 5.0)
        self.assertEqual(reconciled.remaining_quantity, 0.0)
        self.assertEqual(len(reconciled.fill_events), 2)
        # Average price = (2*60000 + 3*60100)/5 = 60060.0
        self.assertAlmostEqual(reconciled.average_fill_price, 60060.0)

    def test_duplicate_hedge_plans(self):
        plan = self._make_plan("plan_dup", 1.0)
        order1 = self.machine.submit_plan(plan)
        order2 = self.machine.submit_plan(plan)
        
        self.assertEqual(order1.client_order_id, order2.client_order_id)
        self.assertEqual(order1.order_id, order2.order_id)
        # Verify provider only has 1 order
        self.assertEqual(len(self.provider.get_open_orders()), 1)

    def test_illegal_state_transition(self):
        plan = self._make_plan("plan_illegal")
        order = self.machine.submit_plan(plan)
        
        # Order is currently ACKNOWLEDGED. Let's force jump to QUEUED which is backwards
        with self.assertRaises(InvalidStateTransitionError):
            self.machine._transition(order, ExecutionState.QUEUED)

    def test_recovery_after_restart(self):
        # 1. Start original machine
        plan = self._make_plan("plan_recover")
        order = self.machine.submit_plan(plan)
        
        # 2. Simulate fill on provider without telling machine yet
        self.provider.simulate_fill(order.client_order_id, 1.0, 50000.0)
        
        # 3. Simulate process crash by creating a new Machine with same provider but NEW empty store!
        new_store = InMemoryExecutionStore()
        
        # Re-inject the order into the new store to simulate it was loaded from disk
        # (It hasn't received the fill yet in its local state)
        order_from_disk = self.store.get_order(order.client_order_id)
        new_store.save_order(order_from_disk)
        
        new_machine = ExecutionStateMachine(
            provider=self.provider,
            event_bus=self.event_bus,
            store=new_store,
            clock=self.clock,
            replay_mode=True
        )
        
        # 4. Trigger recovery
        new_machine.recover()
        
        # 5. Verify local state synced the fill from provider
        reconciled = new_store.get_order(order.client_order_id)
        self.assertEqual(reconciled.state, ExecutionState.FILLED)
        self.assertEqual(reconciled.filled_quantity, 1.0)

    def test_100_sequential_orders(self):
        for i in range(100):
            plan = self._make_plan(f"plan_seq_{i}", 0.1)
            order = self.machine.submit_plan(plan)
            self.assertEqual(order.state, ExecutionState.ACKNOWLEDGED)
            
        self.assertEqual(len(self.store.get_active_orders()), 100)
        self.assertEqual(len(self.provider.get_open_orders()), 100)

    def test_rapid_cancel(self):
        plan = self._make_plan("plan_cancel")
        order = self.machine.submit_plan(plan)
        self.assertEqual(order.state, ExecutionState.ACKNOWLEDGED)
        
        success = self.machine.cancel_order(order.client_order_id)
        self.assertTrue(success)
        
        final_order = self.store.get_order(order.client_order_id)
        self.assertEqual(final_order.state, ExecutionState.CANCELLED)
        
        # Try cancel again
        success2 = self.machine.cancel_order(order.client_order_id)
        self.assertFalse(success2)

    def test_clock_determinism(self):
        clock1 = ReplayClock(start_time=100.0)
        machine1 = ExecutionStateMachine(PaperExecutionProvider(clock1), event_bus=self.event_bus, clock=clock1, replay_mode=True)
        order1 = machine1.submit_plan(self._make_plan("plan_det"))
        
        clock2 = ReplayClock(start_time=100.0)
        machine2 = ExecutionStateMachine(PaperExecutionProvider(clock2), event_bus=self.event_bus, clock=clock2, replay_mode=True)
        order2 = machine2.submit_plan(self._make_plan("plan_det"))
        
        # Same IDs, same timestamps
        self.assertEqual(order1.client_order_id, order2.client_order_id)
        self.assertEqual(order1.created_at, order2.created_at)

if __name__ == '__main__':
    unittest.main()
