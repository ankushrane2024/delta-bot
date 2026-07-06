import unittest
import copy
from hedge.models.portfolio import PortfolioSnapshot, InvalidPortfolioStateError
from hedge.models.events import (
    EventBus, OrderSubmitted, OrderPartiallyFilled, OrderFilled, 
    ManualPositionDetected, PortfolioReconciled
)
from hedge.models.execution import ExecutionOrder, ExecutionState, FillEvent
from hedge.models.core_interfaces import ReplayClock
from hedge.engines.portfolio_synchronizer import PortfolioSynchronizer
from hedge.engines.execution_provider import PaperExecutionProvider

class TestPortfolioSynchronizer(unittest.TestCase):
    def setUp(self):
        self.clock = ReplayClock(start_time=1000.0)
        self.event_bus = EventBus()
        self.provider = PaperExecutionProvider(self.clock)
        self.sync = PortfolioSynchronizer(self.provider, self.event_bus, self.clock, replay_mode=True)
        
    def _dummy_order(self, client_id="test1", side="SHORT", qty=1.0, state=ExecutionState.SUBMITTED) -> ExecutionOrder:
        return ExecutionOrder(
            order_id="exc1",
            client_order_id=client_id,
            plan_id="plan1",
            symbol="BTCUSD",
            side=side,
            quantity=qty,
            order_type="MARKET",
            state=state,
            remaining_quantity=qty
        )

    def test_initial_empty_portfolio(self):
        snap = self.sync.current_snapshot
        self.assertEqual(snap.version, 0)
        self.assertEqual(snap.futures_position_qty, 0.0)
        self.assertEqual(snap.realized_pnl, 0.0)
        self.assertEqual(snap.gross_delta, 0.0)
        self.assertEqual(snap.position_direction, "FLAT")

    def test_version_increments_and_immutability(self):
        snap1 = self.sync.current_snapshot
        
        # Dispatch event
        order = self._dummy_order()
        self.event_bus.publish(OrderSubmitted(order, self.clock.now_iso()))
        
        snap2 = self.sync.current_snapshot
        self.assertEqual(snap2.version, 1)
        self.assertEqual(snap1.version, 0)
        self.assertNotEqual(id(snap1), id(snap2))
        
        # Try to mutate frozen dataclass
        with self.assertRaises(Exception):
            snap2.futures_position_qty = 100.0

    def test_single_hedge_and_partial_fill_average_price(self):
        order = self._dummy_order(side="SHORT", qty=10.0, state=ExecutionState.PARTIALLY_FILLED)
        
        # Fill 1: 2.0 @ 60000
        order.filled_quantity = 2.0
        self.event_bus.publish(OrderPartiallyFilled(order, self.clock.now_iso(), filled_amount=2.0, price=60000.0))
        snap = self.sync.current_snapshot
        self.assertEqual(snap.futures_position_qty, -2.0)
        self.assertEqual(snap.futures_average_price, 60000.0)
        
        # Fill 2: 3.0 @ 61000
        order.filled_quantity = 5.0
        self.event_bus.publish(OrderPartiallyFilled(order, self.clock.now_iso(), filled_amount=3.0, price=61000.0))
        snap = self.sync.current_snapshot
        self.assertEqual(snap.futures_position_qty, -5.0)
        # Avg = (2*60000 + 3*61000)/5 = 60600
        self.assertAlmostEqual(snap.futures_average_price, 60600.0)

    def test_realized_pnl_updates_on_reduction(self):
        # 1. Open SHORT 5.0 @ 60000
        order_open = self._dummy_order(side="SHORT", qty=5.0, state=ExecutionState.PARTIALLY_FILLED)
        self.event_bus.publish(OrderPartiallyFilled(order_open, self.clock.now_iso(), filled_amount=5.0, price=60000.0))
        
        # 2. Close LONG 2.0 @ 59000 (Profit of 1000 per BTC * 2 = +2000)
        order_close = self._dummy_order(side="LONG", qty=2.0, state=ExecutionState.PARTIALLY_FILLED)
        self.event_bus.publish(OrderPartiallyFilled(order_close, self.clock.now_iso(), filled_amount=2.0, price=59000.0))
        
        snap = self.sync.current_snapshot
        self.assertEqual(snap.futures_position_qty, -3.0)
        self.assertEqual(snap.futures_average_price, 60000.0) # Avg entry doesn't change on reduction
        self.assertAlmostEqual(snap.realized_pnl, 2000.0)
        
        # 3. Close remaining 3.0 @ 61000 (Loss of 1000 per BTC * 3 = -3000)
        self.event_bus.publish(OrderPartiallyFilled(order_close, self.clock.now_iso(), filled_amount=3.0, price=61000.0))
        snap = self.sync.current_snapshot
        self.assertEqual(snap.futures_position_qty, 0.0)
        self.assertAlmostEqual(snap.realized_pnl, -1000.0) # 2000 - 3000

    def test_manual_position_detection(self):
        self.event_bus.publish(ManualPositionDetected(
            order=self._dummy_order(),
            timestamp=self.clock.now_iso(),
            position_diff=2.5,
            price_diff=65000.0
        ))
        snap = self.sync.current_snapshot
        self.assertEqual(snap.futures_position_qty, 2.5)
        self.assertEqual(snap.futures_average_price, 65000.0)

    def test_reconciliation_detects_differences(self):
        # Reconcile empty provider with non-empty local snapshot
        # But we only reconcile orders right now, which emit PortfolioReconciled
        self.sync.current_snapshot = PortfolioSnapshot(
            timestamp=self.clock.now_iso(), version=1, futures_position_qty=0.0,
            futures_average_price=0.0, net_options_delta=0.0, realized_pnl=0.0,
            unrealized_pnl=0.0, margin_used=0.0, available_balance=0.0,
            active_orders=["fake_order_1"], open_orders=["fake_order_1"], hedge_status="", metadata={}
        )
        
        # Should publish PortfolioReconciled because provider has no fake_order_1
        events_fired = []
        self.event_bus.subscribe(PortfolioReconciled, lambda e: events_fired.append(e))
        
        self.sync.reconcile_with_provider()
        self.assertEqual(len(events_fired), 1)

    def test_validation_rejects_impossible_state(self):
        # We manually inject a bad event that pushes NaN to verify validation
        with self.assertRaises(InvalidPortfolioStateError):
            self.sync.update_unrealized_pnl(float('nan'))
            
    def test_1000_sequential_events(self):
        for i in range(1000):
            order = self._dummy_order(client_id=f"seq_{i}", side="LONG")
            self.event_bus.publish(OrderSubmitted(order, self.clock.now_iso()))
            
        self.assertEqual(self.sync.current_snapshot.version, 1000)
        self.assertEqual(len(self.sync.event_log), 1000)

if __name__ == '__main__':
    unittest.main()
