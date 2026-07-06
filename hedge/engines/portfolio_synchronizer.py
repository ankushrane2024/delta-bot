import threading
import copy
from typing import List, Dict, Any, Optional

from hedge.models.portfolio import PortfolioSnapshot, InvalidPortfolioStateError
from hedge.models.events import (
    EventBus, ExecutionEvent, OrderSubmitted, OrderAcknowledged, 
    OrderPartiallyFilled, OrderFilled, OrderCancelled, OrderRejected,
    PortfolioReconciled, ManualPositionDetected, RecoveryCompleted
)
from hedge.models.core_interfaces import Clock, SystemClock
from hedge.engines.execution_provider import AbstractExecutionProvider
from hedge.models.execution import ExecutionState, ExecutionOrder
import logging

logger = logging.getLogger("ARES.PortfolioSynchronizer")

class PortfolioSynchronizer:
    def __init__(self, 
                 provider: AbstractExecutionProvider, 
                 event_bus: EventBus, 
                 clock: Clock = None,
                 replay_mode: bool = False):
        self.provider = provider
        self.event_bus = event_bus
        self.clock = clock or SystemClock()
        self.replay_mode = replay_mode
        
        self._lock = threading.RLock()
        self.event_log: List[ExecutionEvent] = []
        
        self.current_snapshot: PortfolioSnapshot = self._create_initial_snapshot()
        
        self._subscribe_to_events()

    def _create_initial_snapshot(self) -> PortfolioSnapshot:
        return PortfolioSnapshot(
            timestamp=self.clock.now_iso(),
            version=0,
            futures_position_qty=0.0,
            futures_average_price=0.0,
            net_options_delta=0.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            margin_used=0.0,
            available_balance=0.0,
            active_orders=[],
            open_orders=[],
            hedge_status="NOT_ACTIVE",
            metadata={"created_by_module": "PortfolioSynchronizer", "replay_mode": self.replay_mode}
        )

    def _subscribe_to_events(self):
        # Subscribe to execution events
        self.event_bus.subscribe(OrderSubmitted, self._handle_order_event)
        self.event_bus.subscribe(OrderAcknowledged, self._handle_order_event)
        self.event_bus.subscribe(OrderPartiallyFilled, self._handle_fill_event)
        self.event_bus.subscribe(OrderFilled, self._handle_order_event)
        self.event_bus.subscribe(OrderCancelled, self._handle_order_event)
        self.event_bus.subscribe(OrderRejected, self._handle_order_event)
        self.event_bus.subscribe(ManualPositionDetected, self._handle_manual_event)
        self.event_bus.subscribe(PortfolioReconciled, self._handle_generic_event)
        self.event_bus.subscribe(RecoveryCompleted, self._handle_generic_event)

    def _clone_snapshot_data(self) -> Dict[str, Any]:
        """Helper to prepare the next snapshot state."""
        return {
            "timestamp": self.clock.now_iso(),
            "version": self.current_snapshot.version + 1,
            "futures_position_qty": self.current_snapshot.futures_position_qty,
            "futures_average_price": self.current_snapshot.futures_average_price,
            "net_options_delta": self.current_snapshot.net_options_delta,
            "realized_pnl": self.current_snapshot.realized_pnl,
            "unrealized_pnl": self.current_snapshot.unrealized_pnl,
            "margin_used": self.current_snapshot.margin_used,
            "available_balance": self.current_snapshot.available_balance,
            "active_orders": list(self.current_snapshot.active_orders),
            "open_orders": list(self.current_snapshot.open_orders),
            "hedge_status": self.current_snapshot.hedge_status,
            "metadata": {"created_by_module": "PortfolioSynchronizer", "replay_mode": self.replay_mode}
        }

    def _apply_snapshot(self, next_state: Dict[str, Any]):
        try:
            new_snapshot = PortfolioSnapshot(**next_state)
            self.current_snapshot = new_snapshot
        except InvalidPortfolioStateError as e:
            logger.error(f"Failed to generate PortfolioSnapshot: {e}")
            raise

    def _log_event(self, event: ExecutionEvent):
        self.event_log.append(event)

    def _handle_generic_event(self, event: ExecutionEvent):
        with self._lock:
            self._log_event(event)
            next_state = self._clone_snapshot_data()
            next_state["metadata"]["created_from_event"] = event.__class__.__name__
            self._apply_snapshot(next_state)

    def _handle_manual_event(self, event: ManualPositionDetected):
        with self._lock:
            self._log_event(event)
            next_state = self._clone_snapshot_data()
            next_state["metadata"]["created_from_event"] = "ManualPositionDetected"
            
            # Simple addition to quantity
            next_state["futures_position_qty"] += event.position_diff
            
            # Recalculate average price safely (approximated for manual injection if we don't know the entry)
            # In a real system, we'd query the provider for the actual avg price of the new position.
            next_state["futures_average_price"] = event.price_diff # Assuming price_diff is the new average provided
            
            self._apply_snapshot(next_state)

    def _handle_order_event(self, event: ExecutionEvent):
        with self._lock:
            self._log_event(event)
            order = getattr(event, 'order', None)
            if not order:
                return
                
            next_state = self._clone_snapshot_data()
            next_state["metadata"]["created_from_event"] = event.__class__.__name__
            
            # Track open/active orders
            client_id = order.client_order_id
            
            if order.state in [ExecutionState.SUBMITTED, ExecutionState.QUEUED, ExecutionState.ACKNOWLEDGED, ExecutionState.PARTIALLY_FILLED]:
                if client_id not in next_state["active_orders"]:
                    next_state["active_orders"].append(client_id)
                if client_id not in next_state["open_orders"]:
                    next_state["open_orders"].append(client_id)
            elif order.state in [ExecutionState.FILLED, ExecutionState.CANCELLED, ExecutionState.REJECTED, ExecutionState.FAILED, ExecutionState.EXPIRED]:
                if client_id in next_state["active_orders"]:
                    next_state["active_orders"].remove(client_id)
                if client_id in next_state["open_orders"]:
                    next_state["open_orders"].remove(client_id)
                    
            self._apply_snapshot(next_state)

    def _handle_fill_event(self, event: OrderPartiallyFilled):
        with self._lock:
            self._log_event(event)
            order: ExecutionOrder = event.order
            
            next_state = self._clone_snapshot_data()
            next_state["metadata"]["created_from_event"] = "OrderPartiallyFilled"
            
            # Determine direction of fill
            fill_sign = 1.0 if order.side == "LONG" else -1.0
            fill_qty_signed = event.filled_amount * fill_sign
            
            current_qty = next_state["futures_position_qty"]
            current_avg_px = next_state["futures_average_price"]
            
            # Check if this fill increases or decreases the position size
            if (current_qty > 0 and fill_sign > 0) or (current_qty < 0 and fill_sign < 0) or current_qty == 0:
                # INCREASING position (or initiating)
                total_cost = (abs(current_qty) * current_avg_px) + (event.filled_amount * event.price)
                new_qty = current_qty + fill_qty_signed
                
                next_state["futures_position_qty"] = new_qty
                next_state["futures_average_price"] = total_cost / abs(new_qty)
            else:
                # DECREASING position (closing or reversing)
                # Calculate realized PnL
                if fill_sign > 0: # We are buying to close a short
                    pnl = (current_avg_px - event.price) * event.filled_amount
                else: # We are selling to close a long
                    pnl = (event.price - current_avg_px) * event.filled_amount
                    
                next_state["realized_pnl"] += pnl
                
                new_qty = current_qty + fill_qty_signed
                
                # Check for reversal
                if (current_qty > 0 and new_qty < 0) or (current_qty < 0 and new_qty > 0):
                    # Position flipped
                    next_state["futures_position_qty"] = new_qty
                    next_state["futures_average_price"] = event.price
                else:
                    # Still same direction or flat
                    next_state["futures_position_qty"] = new_qty
                    if new_qty == 0:
                        next_state["futures_average_price"] = 0.0
                    # If same direction, average price doesn't change on reduction
                    
            self._apply_snapshot(next_state)

    def update_options_delta(self, net_options_delta: float):
        """Called externally when portfolio options risk changes."""
        with self._lock:
            next_state = self._clone_snapshot_data()
            next_state["metadata"]["created_from_event"] = "OptionsDeltaUpdate"
            next_state["net_options_delta"] = net_options_delta
            self._apply_snapshot(next_state)
            
    def update_unrealized_pnl(self, unrealized_pnl: float):
        """Called externally when mark price changes."""
        with self._lock:
            next_state = self._clone_snapshot_data()
            next_state["metadata"]["created_from_event"] = "UnrealizedPnLUpdate"
            next_state["unrealized_pnl"] = unrealized_pnl
            self._apply_snapshot(next_state)

    def reconcile_with_provider(self):
        """
        Polls the execution provider for truth. 
        If differences are found, issues ManualPositionDetected and forces a resync.
        """
        with self._lock:
            open_orders = self.provider.get_open_orders()
            # Fetch actual position from provider
            actual_position = self.provider.fetch_position()
            
            provider_order_ids = set([o.client_order_id for o in open_orders])
            internal_order_ids = set(self.current_snapshot.open_orders)
            
            # Check for discrepancies
            discrepancy = []
            if provider_order_ids != internal_order_ids:
                discrepancy.append(f"Provider orders {provider_order_ids} != Internal {internal_order_ids}")
            if actual_position and actual_position.get('quantity', 0.0) != self.current_snapshot.futures_position_qty:
                discrepancy.append(f"Provider qty {actual_position.get('quantity')} != Internal {self.current_snapshot.futures_position_qty}")
            if actual_position and actual_position.get('average_entry', 0.0) != self.current_snapshot.futures_average_price:
                discrepancy.append(f"Provider avg {actual_position.get('average_entry')} != Internal {self.current_snapshot.futures_average_price}")
                
            if discrepancy:
                event = PortfolioReconciled(
                    order=ExecutionOrder(order_id="", client_order_id="reconcile", plan_id="", symbol="", side="", quantity=0, order_type="", state=ExecutionState.RECOVERED),
                    timestamp=self.clock.now_iso(),
                    diff_reason="; ".join(discrepancy)
                )
                self.event_bus.publish(event)
                
                old_qty = self.current_snapshot.futures_position_qty
                old_price = self.current_snapshot.futures_average_price
                
                import dataclasses
                new_snapshot = dataclasses.replace(
                    self.current_snapshot,
                    open_orders=list(provider_order_ids),
                    futures_position_qty=actual_position.get('quantity', 0.0) if actual_position else self.current_snapshot.futures_position_qty,
                    futures_average_price=actual_position.get('average_entry', 0.0) if actual_position else self.current_snapshot.futures_average_price
                )
                self.current_snapshot = new_snapshot
                
                # Emit events
                    
                logger.warning(f"Reconciliation triggered ManualPositionDetected due to: {discrepancy}")
                
                manual_event = ManualPositionDetected(
                    order=None,
                    timestamp=self.clock.now_iso(),
                    position_diff=self.current_snapshot.futures_position_qty - old_qty,
                    price_diff=self.current_snapshot.futures_average_price - old_price
                )
                self.event_bus.publish(manual_event)
                
            event2 = RecoveryCompleted(
                order=ExecutionOrder(order_id="", client_order_id="reconcile", plan_id="", symbol="", side="", quantity=0, order_type="", state=ExecutionState.RECOVERED),
                timestamp=self.clock.now_iso()
            )
            self.event_bus.publish(event2)
