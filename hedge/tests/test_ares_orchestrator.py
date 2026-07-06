import unittest
import time
from unittest.mock import Mock, MagicMock

from hedge.ares_orchestrator import AresOrchestrator
from hedge.models.core_interfaces import AbstractMarketDataProvider, ReplayClock
from hedge.engines.execution_provider import PaperExecutionProvider
from hedge.models.events import EventBus
from hedge.models.execution import ExecutionStatus

class MockMarketDataProvider(AbstractMarketDataProvider):
    def __init__(self):
        self.data = None
        
    def get_latest_data(self):
        return self.data

class TestAresOrchestrator(unittest.TestCase):
    def setUp(self):
        self.market_data_provider = MockMarketDataProvider()
        self.clock = ReplayClock(start_time=1000.0)
        self.event_bus = EventBus()
        self.execution_provider = PaperExecutionProvider(clock=self.clock)
        
        self.orchestrator = AresOrchestrator(
            market_data_provider=self.market_data_provider,
            execution_provider=self.execution_provider,
            clock=self.clock,
            event_bus=self.event_bus
        )
        self.orchestrator.start()
        
    def test_pipeline_execution_no_data(self):
        # Should gracefully skip if no market data
        self.orchestrator.tick()
        self.assertEqual(len(self.orchestrator.state_machine.store.get_active_orders()), 0)
        
    def test_pipeline_execution_full_cycle(self):
        # 1. Feed mock data that forces a hedge
        self.market_data_provider.data = {
            "timestamp": self.clock.now(),
            "spot_price": 50000.0,
            "funding": 0.0001,
            "open_interest": 1000000.0,
            "volume": 5000000.0,
            "iv": 1.5,
            "call_greeks": {
                "delta": 0.8,
                "gamma": 0.02,
                "vega": 10.0
            }
        }
        
        # 2. To ensure hedge triggers, we force the EMA stress high in DecisionEngine
        # since it's hard to spoof the entire Risk/Trend engines without extensive context setup
        self.orchestrator.decision_engine._ema_stress = 100.0
        self.orchestrator.decision_engine._last_ema_time = self.clock.now()
        
        # 3. We also need to give the portfolio some position so it is worth hedging
        # We manually inject a snapshot for testing purposes
        import dataclasses
        snapshot = self.orchestrator.portfolio_sync.current_snapshot
        new_snap = dataclasses.replace(
            snapshot,
            net_options_delta=2.0,
            futures_position_qty=0.0
        )
        self.orchestrator.portfolio_sync.current_snapshot = new_snap
        
        # Run tick
        self.orchestrator.tick()
        
        # We check if State Machine has received a Hedge Plan
        print("DECISION:", getattr(self.orchestrator, 'last_decision', None))
        print("PLAN:", getattr(self.orchestrator, 'last_plan', None))
        active_orders = self.orchestrator.state_machine.store.get_active_orders()
        print("ACTIVE ORDERS:", active_orders)
        # With high risk score and positive options delta, it should short hedge
        self.assertGreaterEqual(len(active_orders), 1)
        
        order = active_orders[0]
        self.assertEqual(order.side, "BUY")
        self.assertEqual(order.state.name, "ACKNOWLEDGED")
        
        # Simulate fill in paper provider
        self.orchestrator.execution_provider.simulate_fill(
            client_order_id=order.client_order_id,
            fill_qty=order.quantity,
            price=50000.0
        )
        
        # Simulate fill in paper provider
        self.orchestrator.execution_provider.simulate_fill(
            client_order_id=order.client_order_id,
            fill_qty=order.quantity,
            price=50000.0
        )
        
        # Pull latest state from provider into state machine
        self.orchestrator.state_machine.reconcile_order(order.client_order_id)
        
        # Fast forward time to process fill in state machine
        self.clock.tick(5.0)
        self.orchestrator.tick()
        
        # Order should be filled
        filled_order = self.orchestrator.state_machine.store.get_order(order.client_order_id)
        print("FILLED ORDER:", filled_order)
        print("EXCHANGE ORDER:", self.orchestrator.execution_provider._exchange_orders[order.client_order_id])
        self.assertEqual(filled_order.state.name, "FILLED")
        
        # Manually update mock position in paper provider to reflect fill
        self.orchestrator.execution_provider.mock_position['quantity'] = 1.0
        self.orchestrator.execution_provider.mock_position['direction'] = "LONG"
        
        # Portfolio should be synchronized to the new position
        self.orchestrator.portfolio_sync.reconcile_with_provider()
        snap = self.orchestrator.portfolio_sync.current_snapshot
        self.assertGreater(snap.futures_position_qty, 0.0) # Long position

if __name__ == '__main__':
    unittest.main()
