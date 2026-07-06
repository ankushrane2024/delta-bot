import uuid
import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from hedge.engines.base_engine import AbstractBaseEngine
from hedge.engines.execution_provider import AbstractExecutionProvider
from hedge.engines.state_machine import ExecutionStateMachine
from hedge.models.hedge import HedgePlan
from hedge.models.enums import AresDecision, ExecutionStatus
from hedge.models.execution import ExecutionResult, ExecutionOrder, ExecutionState
from hedge.models.shared import AnalyzerHealth

logger = logging.getLogger("ARES.ExecutionEngine")

from hedge.models.events import EventBus

class ExecutionEngine(AbstractBaseEngine):
    def __init__(self, provider: AbstractExecutionProvider = None, event_bus: EventBus = None, replay_mode: bool = False):
        self.provider = provider
        if event_bus is None:
            raise ValueError("ExecutionEngine requires an event_bus.")
        self.event_bus = event_bus
        self.replay_mode = replay_mode
        self._warnings: List[str] = []
        self._last_execution_time = 0.0
        
        # Instantiate State Machine with the provider
        self.state_machine = ExecutionStateMachine(
            provider=self.provider,
            event_bus=self.event_bus,
            replay_mode=self.replay_mode
        )

    def initialize(self) -> None:
        logger.info("Initialized ExecutionEngine.")
        if self.provider:
            self.provider.initialize()
            # On boot, recover state via the State Machine
            self.state_machine.recover()
        self.reset()

    def evaluate(self, hedge_plan: Optional[HedgePlan]) -> Optional[ExecutionResult]:
        """
        Takes a HedgePlan and executes it through the ExecutionStateMachine.
        Returns None if no plan was provided or if action is HOLD.
        """
        started_at = time.time()
        execution_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        self._warnings.clear()
        
        # 1. Reject invalid or missing plans
        if hedge_plan is None:
            return None
            
        if hedge_plan.action == AresDecision.HOLD:
            return None
            
        # 2. State Machine handles Validation, Queuing, Submission, Retry, and Provider Hand-off.
        order: ExecutionOrder = self.state_machine.submit_plan(hedge_plan)
        
        # Determine internal backwards compatible status
        status = ExecutionStatus.FAILED
        if order.state in [ExecutionState.FILLED]:
            status = ExecutionStatus.FILLED
        elif order.state in [ExecutionState.PARTIALLY_FILLED]:
            status = ExecutionStatus.PARTIALLY_FILLED
        elif order.state in [ExecutionState.ACKNOWLEDGED, ExecutionState.SUBMITTED, ExecutionState.QUEUED]:
            status = ExecutionStatus.SUBMITTED
        elif order.state in [ExecutionState.REJECTED, ExecutionState.CANCELLED]:
            status = ExecutionStatus.CANCELLED
            
        # Compile Result
        result = self._finalize_result(
            execution_id=execution_id,
            hedge_plan=hedge_plan,
            status=status,
            exec_plan={"strategy": "MARKET_TAKER"},
            orders=[order],
            valid=(order.state != ExecutionState.REJECTED),
            timestamp=timestamp,
            started_at=started_at,
            explanation=f"State Machine managed order {order.client_order_id} -> {order.state.name}"
        )
        
        logger.debug(f"ExecutionEngine evaluated in {result.execution_time_ms:.2f}ms. ID: {execution_id}")
        return result

    def _finalize_result(self, execution_id: str, hedge_plan: HedgePlan, status: ExecutionStatus, 
                         exec_plan: Dict[str, Any], orders: List[ExecutionOrder], valid: bool, 
                         timestamp: str, started_at: float, explanation: str) -> ExecutionResult:
        
        completed_at = time.time()
        execution_time_ms = (completed_at - started_at) * 1000.0
        if hedge_plan.action == AresDecision.HOLD:
            return ExecutionResult(
                status=ExecutionStatus.SKIPPED,
                executed_quantity=0.0,
                message="Plan action is HOLD."
            )
        self._last_execution_time = execution_time_ms
        
        return ExecutionResult(
            execution_id=execution_id,
            hedge_id=hedge_plan.hedge_id,
            execution_status=status,
            execution_plan=exec_plan,
            created_orders=orders,
            validation_result=valid,
            timestamp=timestamp,
            started_at=started_at,
            completed_at=completed_at,
            execution_time_ms=execution_time_ms,
            explanation=explanation,
            debug_information={"warnings": list(self._warnings)}
        )

    def reset(self) -> None:
        self._warnings.clear()
        self._last_execution_time = 0.0

    def health(self) -> AnalyzerHealth:
        provider_healthy = False
        if self.provider:
            provider_healthy = self.provider.validate_connectivity()
            
        return AnalyzerHealth(
            loaded_evaluators=1 if self.provider else 0,
            failed_evaluators=0,
            warnings=list(self._warnings),
            replay_mode=self.replay_mode,
            last_execution_time=self._last_execution_time
        )
        
    def metadata(self) -> Dict[str, Any]:
        return {
            "name": "ExecutionEngine",
            "provider": self.provider.__class__.__name__ if self.provider else "None",
            "state_machine": "ExecutionStateMachine"
        }
