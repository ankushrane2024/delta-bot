from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from .enums import ExecutionStatus

@dataclass
class ExecutionOrder:
    order_id: str
    symbol: str
    side: str
    quantity: float
    order_type: str
    status: str
    price: Optional[float] = None
    filled_quantity: float = 0.0
    debug_information: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ExecutionResult:
    execution_id: str
    hedge_id: str
    execution_status: ExecutionStatus
    execution_plan: Dict[str, Any]
    created_orders: List[ExecutionOrder]
    validation_result: bool
    timestamp: str
    started_at: float
    completed_at: float
    execution_time_ms: float
    explanation: str
    debug_information: Dict[str, Any] = field(default_factory=dict)
