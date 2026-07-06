from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from .enums import ExecutionStatus, ExecutionState

@dataclass
class FillEvent:
    timestamp: str
    quantity: float
    price: float
    fee: float = 0.0
    execution_id: str = ""

@dataclass
class StateTransitionRecord:
    timestamp: str
    previous_state: ExecutionState
    new_state: ExecutionState
    reason: str

@dataclass
class ExecutionOrder:
    order_id: str
    client_order_id: str
    plan_id: str
    symbol: str
    side: str
    quantity: float
    order_type: str
    state: ExecutionState
    
    requested_price: Optional[float] = None
    average_fill_price: float = 0.0
    filled_quantity: float = 0.0
    remaining_quantity: float = 0.0
    
    execution_style: str = "MARKET"
    priority: int = 0
    retry_count: int = 0
    
    created_at: str = ""
    updated_at: str = ""
    completed_at: Optional[str] = None
    
    reason: str = ""
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    fill_events: List[FillEvent] = field(default_factory=list)
    state_history: List[StateTransitionRecord] = field(default_factory=list)

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
