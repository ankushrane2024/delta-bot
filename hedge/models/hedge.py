from dataclasses import dataclass
from typing import Dict, Any, Optional, List

@dataclass
class HedgePlan:
    action: str
    side: str
    quantity: float
    execution_priority: int
    execution_style: str
    estimated_post_hedge_delta: float
    hedge_reason: str
    urgency: float
    timestamp: float
    warnings: List[str]
    
    # Backward compatibility properties for ExecutionEngine
    @property
    def hedge_quantity(self) -> float:
        return self.quantity
        
    @property
    def hedge_side(self) -> Any:
        # Mock an enum so .name works
        class MockEnum:
            def __init__(self, name):
                self.name = name
        return MockEnum(self.side)
        
    @property
    def hedge_id(self) -> str:
        return "mock_id"
