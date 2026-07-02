from abc import ABC, abstractmethod
from typing import Dict, Any, List
from hedge.models.execution import ExecutionOrder

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
    def submit_orders(self, orders: List[Dict[str, Any]]) -> List[ExecutionOrder]:
        pass
        
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        pass
        
    @abstractmethod
    def fetch_order_status(self, order_id: str) -> ExecutionOrder:
        pass
