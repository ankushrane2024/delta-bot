import uuid
import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from hedge.engines.base_engine import AbstractBaseEngine
from hedge.engines.execution_provider import AbstractExecutionProvider
from hedge.models.hedge import HedgePlan, HedgeSide
from hedge.models.enums import AresDecision, ExecutionStatus
from hedge.models.execution import ExecutionResult, ExecutionOrder
from hedge.models.shared import AnalyzerHealth

logger = logging.getLogger("ARES.ExecutionEngine")

class ExecutionEngine(AbstractBaseEngine):
    def __init__(self, provider: AbstractExecutionProvider = None, replay_mode: bool = False):
        self.provider = provider
        self.replay_mode = replay_mode
        self._warnings: List[str] = []
        self._last_execution_time = 0.0

    def initialize(self) -> None:
        logger.info("Initialized ExecutionEngine.")
        if self.provider:
            self.provider.initialize()
        self.reset()

    def evaluate(self, hedge_plan: Optional[HedgePlan]) -> Optional[ExecutionResult]:
        """
        Takes a HedgePlan and executes it.
        Returns None if no plan was provided or if action is HOLD.
        """
        started_at = time.time()
        execution_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        self._warnings.clear()
        
        # 1. Reject invalid or missing plans
        if hedge_plan is None:
            return None
            
        if hedge_plan.hedge_action == AresDecision.HOLD:
            return None
            
        is_valid = self._validate_plan(hedge_plan)
        if not is_valid:
            logger.warning(f"Invalid HedgePlan {hedge_plan.hedge_id}. Rejecting execution.")
            return self._finalize_result(
                execution_id=execution_id,
                hedge_plan=hedge_plan,
                status=ExecutionStatus.FAILED,
                exec_plan={},
                orders=[],
                valid=False,
                timestamp=timestamp,
                started_at=started_at,
                explanation="HedgePlan validation failed."
            )
            
        # 2. Build Internal Execution Plan (e.g. order legs, timing)
        exec_plan = self._prepare_execution(hedge_plan)
        
        # 3. Build order primitives
        raw_orders = self._build_orders(exec_plan, hedge_plan)
        
        # 4. Execute orders (Placeholder routing)
        created_orders = self._execute(raw_orders)
        
        # 5. Determine overall status
        status = self._determine_status(created_orders)
        
        # 6. Finalize
        result = self._finalize_result(
            execution_id=execution_id,
            hedge_plan=hedge_plan,
            status=status,
            exec_plan=exec_plan,
            orders=created_orders,
            valid=True,
            timestamp=timestamp,
            started_at=started_at,
            explanation=f"Execution pipeline completed with status {status.name}."
        )
        
        logger.debug(f"ExecutionEngine evaluated in {result.execution_time_ms:.2f}ms. ID: {execution_id}")
        return result

    # --- Pipeline Stages ---
    
    def _validate_plan(self, plan: HedgePlan) -> bool:
        is_valid = True
        if plan.hedge_quantity <= 0:
            self._warnings.append("Hedge quantity is zero or negative.")
            is_valid = False
        if plan.hedge_side == HedgeSide.NONE:
            self._warnings.append("Hedge side is NONE.")
            is_valid = False
        return is_valid

    def _prepare_execution(self, plan: HedgePlan) -> Dict[str, Any]:
        return {
            "strategy": "MARKET_TAKER",
            "legs": 1,
            "timeout_ms": 5000
        }

    def _build_orders(self, exec_plan: Dict[str, Any], hedge_plan: HedgePlan) -> List[Dict[str, Any]]:
        return [{
            "symbol": "BTCUSD",
            "side": hedge_plan.hedge_side.name,
            "quantity": hedge_plan.hedge_quantity,
            "type": "MARKET"
        }]

    def _execute(self, raw_orders: List[Dict[str, Any]]) -> List[ExecutionOrder]:
        # If provider exists, we would call it here. For now it's a placeholder.
        orders = []
        for i, ro in enumerate(raw_orders):
            orders.append(ExecutionOrder(
                order_id=str(uuid.uuid4()),
                symbol=ro.get("symbol", ""),
                side=ro.get("side", ""),
                quantity=ro.get("quantity", 0.0),
                order_type=ro.get("type", "MARKET"),
                status="FILLED",
                filled_quantity=ro.get("quantity", 0.0)
            ))
        return orders
        
    def _determine_status(self, orders: List[ExecutionOrder]) -> ExecutionStatus:
        if not orders:
            return ExecutionStatus.PENDING
        all_filled = all(o.status == "FILLED" for o in orders)
        if all_filled:
            return ExecutionStatus.FILLED
        return ExecutionStatus.PARTIALLY_FILLED

    def _finalize_result(self, execution_id: str, hedge_plan: HedgePlan, status: ExecutionStatus, 
                         exec_plan: Dict[str, Any], orders: List[ExecutionOrder], valid: bool, 
                         timestamp: str, started_at: float, explanation: str) -> ExecutionResult:
        
        completed_at = time.time()
        execution_time_ms = (completed_at - started_at) * 1000.0
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

    # ---------------------------------

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
            "provider": self.provider.__class__.__name__ if self.provider else "None"
        }
