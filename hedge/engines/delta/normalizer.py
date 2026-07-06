from typing import Dict, Any, List
from hedge.models.execution import ExecutionOrder, ExecutionState
from hedge.models.events import (
    OrderSubmitted, OrderAcknowledged, OrderPartiallyFilled,
    OrderFilled, OrderCancelled, OrderRejected
)

class DeltaMessageNormalizer:
    """
    Pure data conversion class. No state, no business logic.
    Converts Delta Exchange JSON to ARES internal models.
    """
    
    @staticmethod
    def parse_state(delta_state: str) -> ExecutionState:
        state_map = {
            "open": ExecutionState.ACKNOWLEDGED,
            "pending": ExecutionState.SUBMITTED,
            "partially_filled": ExecutionState.PARTIALLY_FILLED,
            "closed": ExecutionState.FILLED,
            "cancelled": ExecutionState.CANCELLED,
            "rejected": ExecutionState.REJECTED
        }
        return state_map.get(delta_state.lower(), ExecutionState.FAILED)
        
    @staticmethod
    def parse_order(payload: Dict[str, Any], catalog=None) -> ExecutionOrder:
        """
        Parses a Delta order object (from REST or WS) into an ARES ExecutionOrder.
        `catalog` is an instance of ProductCatalog to reverse lookup product_id to generic symbol (BTCUSD).
        """
        client_order_id = payload.get("client_order_id", "")
        order_id = str(payload.get("id", ""))
        
        # Determine symbol
        product_id = payload.get("product_id")
        symbol = "BTCUSD"
        if catalog and product_id:
            mapped_sym = catalog.get_symbol(product_id)
            if mapped_sym:
                symbol = mapped_sym
                
        side = "BUY" if payload.get("side", "").lower() == "buy" else "SELL"
        qty = float(payload.get("size", 0.0))
        unfilled = float(payload.get("unfilled_size", qty))
        state = DeltaMessageNormalizer.parse_state(payload.get("state", "rejected"))
        reason = payload.get("reject_reason", "")
        
        return ExecutionOrder(
            order_id=order_id,
            client_order_id=client_order_id,
            plan_id=client_order_id, # Can't reconstruct plan_id from exchange unless encoded in client_order_id
            symbol=symbol,
            side=side,
            quantity=qty,
            remaining_quantity=unfilled,
            order_type=payload.get("order_type", "MARKET").upper(),
            state=state,
            created_at=str(payload.get("created_at", "")),
            updated_at=str(payload.get("updated_at", "")),
            reason=reason
        )

    @staticmethod
    def create_event(order: ExecutionOrder, timestamp: float, event_type: str = None) -> Any:
        if order.state == ExecutionState.SUBMITTED:
            return OrderSubmitted(order=order, timestamp=timestamp)
        elif order.state == ExecutionState.ACKNOWLEDGED:
            return OrderAcknowledged(order=order, timestamp=timestamp)
        elif order.state == ExecutionState.PARTIALLY_FILLED:
            # Note: For partial fills we typically need fill qty and price, but here we just pass the order
            # ARES assumes partial fills update remaining_quantity on the order.
            return OrderPartiallyFilled(order=order, timestamp=timestamp, fill_qty=0.0, fill_price=0.0)
        elif order.state == ExecutionState.FILLED:
            return OrderFilled(order=order, timestamp=timestamp, fill_qty=order.quantity, fill_price=0.0)
        elif order.state == ExecutionState.CANCELLED:
            return OrderCancelled(order=order, timestamp=timestamp)
        elif order.state == ExecutionState.REJECTED:
            return OrderRejected(order=order, timestamp=timestamp, reason=order.reason)
        return None
