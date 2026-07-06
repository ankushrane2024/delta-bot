from abc import ABC, abstractmethod
from typing import Dict, Any, List
import copy
from hedge.models.execution import ExecutionOrder, ExecutionState, FillEvent
from hedge.models.core_interfaces import Clock, SystemClock

class AbstractExecutionProvider(ABC):
    """
    Abstract interface for exchange connectivity. 
    Ensures the ExecutionEngine remains strictly exchange-agnostic.
    """
    
    @abstractmethod
    def initialize(self) -> None:
        pass

    @abstractmethod
    def validate_connectivity(self) -> bool:
        pass

    @abstractmethod
    def submit_order(self, order: ExecutionOrder) -> ExecutionOrder:
        pass
        
    @abstractmethod
    def cancel_order(self, client_order_id: str) -> bool:
        pass
        
    @abstractmethod
    def fetch_order_status(self, client_order_id: str) -> ExecutionOrder:
        pass

    @abstractmethod
    def get_open_orders(self) -> List[ExecutionOrder]:
        """Used for state machine recovery/reconciliation."""
        pass

    @abstractmethod
    def fetch_position(self) -> dict:
        pass


class PaperExecutionProvider(AbstractExecutionProvider):
    """
    A simulated provider that mocks exchange latency and partial fills.
    Maintains its own 'exchange state' so the state machine can reconcile against it.
    """
    def __init__(self, clock: Clock = None):
        self.clock = clock or SystemClock()
        self._exchange_orders: Dict[str, ExecutionOrder] = {}
        self.is_connected = False
        self.mock_position = {
            'quantity': 0.0,
            'average_entry': 0.0,
            'direction': "NONE",
            'open_orders': 0,
            'hedge_ratio': 0.0,
            'margin': 0.0
        }
        
    def initialize(self) -> None:
        self.is_connected = True

    def validate_connectivity(self) -> bool:
        return self.is_connected

    def submit_order(self, order: ExecutionOrder) -> ExecutionOrder:
        exchange_order = copy.deepcopy(order)
        exchange_order.order_id = f"exch_{order.client_order_id}"
        exchange_order.state = ExecutionState.ACKNOWLEDGED
        exchange_order.updated_at = self.clock.now_iso()
        self._exchange_orders[order.client_order_id] = exchange_order
        return copy.deepcopy(exchange_order)

    def simulate_fill(self, client_order_id: str, fill_qty: float, price: float):
        """Helper method for testing partial fills and full fills."""
        if client_order_id not in self._exchange_orders:
            return
            
        order = self._exchange_orders[client_order_id]
        if order.state in [ExecutionState.FILLED, ExecutionState.CANCELLED, ExecutionState.FAILED, ExecutionState.REJECTED]:
            return
            
        now_str = self.clock.now_iso()
        
        # Calculate new filled quantity safely
        new_filled = min(order.quantity, order.filled_quantity + fill_qty)
        actual_fill_this_event = new_filled - order.filled_quantity
        
        if actual_fill_this_event <= 0:
            return
            
        # Update price (weighted average)
        total_cost = (order.average_fill_price * order.filled_quantity) + (price * actual_fill_this_event)
        order.filled_quantity = new_filled
        order.remaining_quantity = order.quantity - order.filled_quantity
        order.average_fill_price = total_cost / order.filled_quantity
        
        order.fill_events.append(FillEvent(
            timestamp=now_str,
            quantity=actual_fill_this_event,
            price=price,
            fee=0.0,
            execution_id=f"fill_{len(order.fill_events)}"
        ))
        
        if order.remaining_quantity <= 0:
            order.state = ExecutionState.FILLED
            order.completed_at = now_str
        else:
            order.state = ExecutionState.PARTIALLY_FILLED
            
        order.updated_at = now_str

    def cancel_order(self, client_order_id: str) -> bool:
        if client_order_id in self._exchange_orders:
            order = self._exchange_orders[client_order_id]
            if order.state not in [ExecutionState.FILLED, ExecutionState.CANCELLED, ExecutionState.FAILED, ExecutionState.REJECTED]:
                order.state = ExecutionState.CANCELLED
                order.updated_at = self.clock.now_iso()
                order.completed_at = order.updated_at
                order.reason = "User Cancelled"
                return True
        return False

    def fetch_order_status(self, client_order_id: str) -> ExecutionOrder:
        if client_order_id in self._exchange_orders:
            return copy.deepcopy(self._exchange_orders[client_order_id])
        
        # Return a REJECTED skeleton if not found
        fake = ExecutionOrder(
            order_id="unknown",
            client_order_id=client_order_id,
            plan_id="",
            symbol="",
            side="",
            quantity=0,
            order_type="",
            state=ExecutionState.REJECTED,
            reason="Order not found on exchange."
        )
        return fake

    def get_open_orders(self) -> List[ExecutionOrder]:
        return [copy.deepcopy(o) for o in self._exchange_orders.values() 
                if o.state not in [ExecutionState.FILLED, ExecutionState.CANCELLED, ExecutionState.FAILED, ExecutionState.REJECTED]]

    def fetch_position(self) -> dict:
        self.mock_position['open_orders'] = len(self.get_open_orders())
        return self.mock_position
