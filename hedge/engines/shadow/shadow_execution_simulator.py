import logging
import copy
import uuid
import time
from typing import Dict

from hedge.models.execution import ExecutionOrder, ExecutionState, FillEvent
from hedge.models.events import EventBus, OrderSubmitted, OrderFilled, OrderCancelled, OrderPartiallyFilled
from hedge.models.core_interfaces import Clock, SystemClock

logger = logging.getLogger(__name__)

class ShadowExecutionSimulator:
    """
    Simulates Paper-like execution behavior (latency, partial fills) for the ShadowExecutionProvider.
    Emits events directly to the EventBus.
    """
    
    def __init__(self, event_bus: EventBus, clock: Clock = None):
        self.event_bus = event_bus
        self.clock = clock or SystemClock()
        
    def simulate_submission(self, order: ExecutionOrder, active_orders: Dict[str, ExecutionOrder]) -> ExecutionOrder:
        """Simulate an exchange accepting the order."""
        new_order = copy.deepcopy(order)
        new_order.order_id = f"shdw_exch_{uuid.uuid4()}"
        new_order.state = ExecutionState.ACKNOWLEDGED
        new_order.updated_at = str(self.clock.now())
        
        active_orders[new_order.client_order_id] = new_order
        
        # Publish submission
        self.event_bus.publish(OrderSubmitted(order=copy.deepcopy(new_order), timestamp=str(self.clock.now())))
        
        # Simulate immediate perfect fill for shadow mode
        self.simulate_fill(new_order.client_order_id, active_orders)
        
        return new_order
        
    def simulate_cancellation(self, client_order_id: str, active_orders: Dict[str, ExecutionOrder]) -> bool:
        if client_order_id not in active_orders:
            return False
            
        order = active_orders[client_order_id]
        order.state = ExecutionState.CANCELLED
        order.updated_at = str(self.clock.now())
        
        self.event_bus.publish(OrderCancelled(order=copy.deepcopy(order), timestamp=str(self.clock.now()), reason="Shadow User Cancel"))
        
        del active_orders[client_order_id]
        return True

    def simulate_fill(self, client_order_id: str, active_orders: Dict[str, ExecutionOrder]):
        """Simulates an execution fill."""
        if client_order_id not in active_orders:
            return
            
        order = active_orders[client_order_id]
        if order.state not in [ExecutionState.SUBMITTED, ExecutionState.ACKNOWLEDGED, ExecutionState.PARTIALLY_FILLED]:
            return
            
        # Simulate a price around requested, or mock 50k if missing
        fill_price = order.requested_price if order.requested_price else 50000.0
        fill_qty = order.remaining_quantity
        
        order.filled_quantity += fill_qty
        order.remaining_quantity -= fill_qty
        order.average_fill_price = fill_price
        
        fill = FillEvent(
            timestamp=str(self.clock.now()),
            quantity=fill_qty,
            price=fill_price,
            fee=0.0,
            execution_id=f"shdw_fill_{uuid.uuid4()}"
        )
        order.fill_events.append(fill)
        order.updated_at = str(self.clock.now())
        
        if order.remaining_quantity <= 0.000001:
            order.state = ExecutionState.FILLED
            order.completed_at = str(self.clock.now())
            self.event_bus.publish(OrderFilled(order=copy.deepcopy(order), timestamp=str(self.clock.now())))
            del active_orders[client_order_id]
        else:
            order.state = ExecutionState.PARTIALLY_FILLED
            self.event_bus.publish(OrderPartiallyFilled(order=copy.deepcopy(order), timestamp=str(self.clock.now()), filled_amount=fill_qty, price=fill_price))
