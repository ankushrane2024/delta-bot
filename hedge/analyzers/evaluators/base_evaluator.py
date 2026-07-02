from abc import ABC, abstractmethod
from typing import Dict, Any
from hedge.models.price_action import PriceActionEvidence
from hedge.context.market_context import MarketContext

class AbstractPriceEvaluator(ABC):
    def __init__(self, weight: float = 1.0, config: Dict[str, Any] = None):
        self.weight = weight
        self.config = config or {}

    @abstractmethod
    def evaluate(self, context: MarketContext) -> PriceActionEvidence:
        pass
        
    @property
    def name(self) -> str:
        return self.__class__.__name__
