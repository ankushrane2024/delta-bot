import uuid
import hashlib
from typing import Dict, Any, List, Optional

from hedge.models.execution import ExecutionOrder, ExecutionState, StateTransitionRecord, FillEvent
from hedge.models.hedge import HedgePlan
from hedge.models.events import (
    EventBus, OrderSubmitted, OrderAcknowledged, 
    OrderPartiallyFilled, OrderFilled, OrderCancelled, OrderRejected
)
from hedge.models.core_interfaces import Clock, ExecutionStore, SystemClock, InMemoryExecutionStore
from hedge.engines.execution_provider import AbstractExecutionProvider
import logging

logger = logging.getLogger("ARES.ExecutionStateMachine")

class InvalidStateTransitionError(Exception):
    pass

class ExecutionStateMachine:
    def __init__(self, 
                 provider: AbstractExecutionProvider, 
                 event_bus: EventBus,
                 store: ExecutionStore = None,
                 clock: Clock = None,
                 replay_mode: bool = False,
                 config: Dict[str, Any] = None):
                 
        if event_bus is None:
            raise ValueError("EventBus is mandatory for ExecutionStateMachine.")
        self.event_bus = event_bus
                 
        self.provider = provider
        self.store = store or InMemoryExecutionStore()
        self.clock = clock or SystemClock()
        self.replay_mode = replay_mode
        self.config = config or {
            "MAX_RETRIES": 3,
            "SUBMISSION_TIMEOUT": 5.0,
            "ACK_TIMEOUT": 10.0,
            "FILL_TIMEOUT": 60.0,
            "CIRCUIT_BREAKER_THRESHOLD": 5
        }
        
        self._consecutive_failures = 0
        self._circuit_breaker_tripped = False
        self._scheduled_actions = [] # List of (execute_at: float, order: ExecutionOrder)
        
        # Valid state transitions
        self._allowed_transitions = {
            ExecutionState.CREATED: [ExecutionState.VALIDATED, ExecutionState.REJECTED],
            ExecutionState.VALIDATED: [ExecutionState.QUEUED, ExecutionState.REJECTED, ExecutionState.CANCELLED],
            ExecutionState.QUEUED: [ExecutionState.SUBMITTED, ExecutionState.CANCELLED, ExecutionState.FAILED],
            ExecutionState.SUBMITTED: [ExecutionState.ACKNOWLEDGED, ExecutionState.REJECTED, ExecutionState.FAILED],
            ExecutionState.ACKNOWLEDGED: [ExecutionState.PARTIALLY_FILLED, ExecutionState.FILLED, ExecutionState.CANCEL_PENDING, ExecutionState.CANCELLED, ExecutionState.REPLACED],
            ExecutionState.PARTIALLY_FILLED: [ExecutionState.PARTIALLY_FILLED, ExecutionState.FILLED, ExecutionState.CANCEL_PENDING, ExecutionState.CANCELLED],
            ExecutionState.CANCEL_PENDING: [ExecutionState.CANCELLED, ExecutionState.FAILED, ExecutionState.FILLED],
            # Terminal states below (no outgoing transitions except RECOVERED for fixing broken state, which is handled bypass)
            ExecutionState.FILLED: [],
            ExecutionState.CANCELLED: [],
            ExecutionState.REJECTED: [],
            ExecutionState.FAILED: [ExecutionState.QUEUED], # Allow retry
            ExecutionState.EXPIRED: []
        }

    def _generate_id(self, plan_id: str) -> str:
        if self.replay_mode:
            # Deterministic UUID for replay
            h = hashlib.md5(f"{plan_id}_{self.clock.now()}".encode()).hexdigest()
            return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"
        return str(uuid.uuid4())

    def _transition(self, order: ExecutionOrder, new_state: ExecutionState, reason: str = ""):
        if new_state not in self._allowed_transitions.get(order.state, []) and new_state != ExecutionState.RECOVERED:
            raise InvalidStateTransitionError(f"Cannot transition from {order.state.name} to {new_state.name}")
            
        old_state = order.state
        order.state = new_state
        now_str = self.clock.now_iso()
        order.updated_at = now_str
        
        order.state_history.append(StateTransitionRecord(
            timestamp=now_str,
            previous_state=old_state,
            new_state=new_state,
            reason=reason
        ))
        
        # Terminal states
        if new_state in [ExecutionState.FILLED, ExecutionState.CANCELLED, ExecutionState.REJECTED, ExecutionState.FAILED, ExecutionState.EXPIRED]:
            order.completed_at = now_str
            order.reason = reason

        self.store.save_order(order)
        self._publish_event(order)
        
    def _publish_event(self, order: ExecutionOrder):
        event = None
        now = self.clock.now_iso()
        if order.state == ExecutionState.SUBMITTED:
            event = OrderSubmitted(order, now)
        elif order.state == ExecutionState.ACKNOWLEDGED:
            event = OrderAcknowledged(order, now)
        elif order.state == ExecutionState.FILLED:
            event = OrderFilled(order, now)
        elif order.state == ExecutionState.CANCELLED:
            event = OrderCancelled(order, now, reason=order.reason)
        elif order.state == ExecutionState.REJECTED:
            event = OrderRejected(order, now, reason=order.reason)
            
        if event:
            self.event_bus.publish(event)

    def submit_plan(self, plan: HedgePlan) -> ExecutionOrder:
        # Idempotency Check
        existing = self.store.get_order_by_plan(plan.hedge_id)
        if existing:
            logger.info(f"Idempotency hit: Plan {plan.hedge_id} already exists as order {existing.client_order_id}")
            return existing

        if self._circuit_breaker_tripped:
            logger.error(f"Circuit Breaker Tripped: Rejecting plan {plan.hedge_id}")
            return ExecutionOrder(
                order_id="", client_order_id=self._generate_id(plan.hedge_id), plan_id=plan.hedge_id,
                symbol="BTCUSD", side=plan.hedge_side.name, quantity=plan.hedge_quantity, remaining_quantity=plan.hedge_quantity,
                order_type="MARKET", state=ExecutionState.REJECTED, created_at=self.clock.now_iso(), updated_at=self.clock.now_iso(),
                reason="Circuit Breaker Tripped"
            )

        now_str = self.clock.now_iso()
        client_order_id = self._generate_id(plan.hedge_id)
        
        order = ExecutionOrder(
            order_id="",
            client_order_id=client_order_id,
            plan_id=plan.hedge_id,
            symbol="BTCUSD",
            side=plan.hedge_side.name,
            quantity=plan.hedge_quantity,
            remaining_quantity=plan.hedge_quantity,
            order_type="MARKET",
            state=ExecutionState.CREATED,
            created_at=now_str,
            updated_at=now_str
        )
        self.store.save_order(order)
        
        # Validate
        if order.quantity <= 0 or order.side == "NONE":
            self._transition(order, ExecutionState.REJECTED, "Invalid quantity or side")
            return order
            
        self._transition(order, ExecutionState.VALIDATED, "Passed validation")
        self._transition(order, ExecutionState.QUEUED, "Queued for submission")
        
        return self._execute_submission(order)

    def _execute_submission(self, order: ExecutionOrder) -> ExecutionOrder:
        try:
            self._transition(order, ExecutionState.SUBMITTED, "Sent to provider")
            exch_order = self.provider.submit_order(order)
            
            # Sync exchange generated fields back to our order
            if exch_order.order_id:
                order.order_id = exch_order.order_id
            
            if exch_order.state == ExecutionState.ACKNOWLEDGED:
                self._consecutive_failures = 0
                self._circuit_breaker_tripped = False
                self._transition(order, ExecutionState.ACKNOWLEDGED, "Provider Ack")
            elif exch_order.state == ExecutionState.REJECTED:
                self._transition(order, ExecutionState.REJECTED, exch_order.reason or "Exchange rejected")
                
        except Exception as e:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.config.get("CIRCUIT_BREAKER_THRESHOLD", 5):
                self._circuit_breaker_tripped = True
                logger.critical("CIRCUIT BREAKER TRIPPED! Too many consecutive failures.")
            
            logger.error(f"Provider submission failed: {e}")
            self._transition(order, ExecutionState.FAILED, f"Provider Error: {e}")
            self._handle_retry(order)
            
        return order

    def _handle_retry(self, order: ExecutionOrder):
        if order.retry_count < self.config.get("MAX_RETRIES", 3):
            order.retry_count += 1
            order.reason = f"Retrying ({order.retry_count}/{self.config.get('MAX_RETRIES')})"
            self._transition(order, ExecutionState.QUEUED, "Queued for retry")
            
            # Exponential backoff with deterministic jitter
            base_delay = 1.0 # 1 second base
            # Deterministic jitter using simple string hash
            jitter = (hash(order.client_order_id + str(order.retry_count)) % 100) / 100.0
            delay = (base_delay * (2 ** order.retry_count)) + jitter
            
            execute_at = self.clock.now() + delay
            self._scheduled_actions.append((execute_at, order))
            # Sort queue by execute_at
            self._scheduled_actions.sort(key=lambda x: x[0])
            logger.info(f"Order {order.client_order_id} scheduled for retry at {execute_at:.3f} (delay: {delay:.3f}s)")
        else:
            logger.warning(f"Order {order.client_order_id} reached max retries.")

    def process_due_actions(self, current_time: float):
        """Processes scheduled retries if their time has arrived."""
        while self._scheduled_actions and self._scheduled_actions[0][0] <= current_time:
            execute_at, order = self._scheduled_actions.pop(0)
            logger.info(f"Executing scheduled retry for {order.client_order_id}")
            self._execute_submission(order)

    def cancel_order(self, client_order_id: str) -> bool:
        order = self.store.get_order(client_order_id)
        if not order:
            return False
            
        if order.state in [ExecutionState.FILLED, ExecutionState.CANCELLED, ExecutionState.REJECTED, ExecutionState.FAILED, ExecutionState.EXPIRED]:
            return False
            
        self._transition(order, ExecutionState.CANCEL_PENDING, "Cancel requested")
        success = self.provider.cancel_order(client_order_id)
        if success:
            self._transition(order, ExecutionState.CANCELLED, "Provider cancelled")
        else:
            # If provider fails to cancel, we rollback to previous state via reconcile
            self.reconcile_order(client_order_id)
        return success

    def reconcile_order(self, client_order_id: str) -> ExecutionOrder:
        """Pulls latest state from provider and reconciles internal state."""
        order = self.store.get_order(client_order_id)
        if not order:
            return None
            
        if order.state in [ExecutionState.FILLED, ExecutionState.CANCELLED, ExecutionState.REJECTED, ExecutionState.FAILED]:
            return order
            
        exch_order = self.provider.fetch_order_status(client_order_id)
        self._sync_state(order, exch_order)
        return order

    def _sync_state(self, local_order: ExecutionOrder, exch_order: ExecutionOrder):
        """Reconcile local order with truth from exchange."""
        # Sync fills safely
        if len(exch_order.fill_events) > len(local_order.fill_events):
            new_fills = exch_order.fill_events[len(local_order.fill_events):]
            for fill in new_fills:
                local_order.fill_events.append(fill)
                local_order.filled_quantity += fill.quantity
                local_order.remaining_quantity -= fill.quantity
                
                # Emit the partial fill event immediately for THIS incremental fill
                # This ensures PortfolioSynchronizer sees the exact increment regardless of state transition
                self.event_bus.publish(
                    OrderPartiallyFilled(
                        order=local_order,
                        timestamp=self.clock.now_iso(),
                        filled_amount=fill.quantity,
                        price=fill.price
                    )
                )
                
            local_order.average_fill_price = exch_order.average_fill_price
            
            if local_order.remaining_quantity <= 0:
                self._transition(local_order, ExecutionState.FILLED, "Fills complete")
            else:
                self._transition(local_order, ExecutionState.PARTIALLY_FILLED, f"Filled {local_order.filled_quantity}")
                
        # Sync terminal states
        if exch_order.state in [ExecutionState.CANCELLED, ExecutionState.REJECTED] and local_order.state != exch_order.state:
            # Check if this transition is legal normally. 
            # If not (e.g. from ACKNOWLEDGED to REJECTED directly), we bypass via RECOVERED or force it.
            try:
                self._transition(local_order, exch_order.state, exch_order.reason or "Exchange synced state")
            except InvalidStateTransitionError:
                # Force recovery transition
                local_order.state_history.append(StateTransitionRecord(
                    timestamp=self.clock.now_iso(),
                    previous_state=local_order.state,
                    new_state=ExecutionState.RECOVERED,
                    reason="Forced reconciliation jump"
                ))
                local_order.state = exch_order.state
                local_order.reason = "Reconciled from exchange"
                self.store.save_order(local_order)
                self._publish_event(local_order)

    def recover(self):
        """
        Full recovery sequence on boot:
        1. Fetch open orders from provider.
        2. Load active orders from store.
        3. Match and sync. Any order active locally but not on exchange needs marking FAILED/CANCELLED.
        """
        logger.info("Initiating Execution State Machine Recovery...")
        exchange_open_orders = {o.client_order_id: o for o in self.provider.get_open_orders()}
        local_active = self.store.get_active_orders()
        
        for local_order in local_active:
            if local_order.client_order_id in exchange_open_orders:
                exch_order = exchange_open_orders[local_order.client_order_id]
                self._sync_state(local_order, exch_order)
            else:
                # Not open on exchange. Could be filled, cancelled, or never reached exchange.
                exch_status = self.provider.fetch_order_status(local_order.client_order_id)
                self._sync_state(local_order, exch_status)
        logger.info("Execution State Machine Recovery Complete.")
