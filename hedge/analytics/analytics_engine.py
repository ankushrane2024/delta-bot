from typing import Dict, Any
from ..engines.base_engine import AbstractBaseEngine

class AnalyticsEngine(AbstractBaseEngine):

    def initialize(self) -> None:
        pass
        
    def evaluate(self, *args, **kwargs) -> Any:
        pass
        
    def reset(self) -> None:
        pass
        
    def health(self) -> bool:
        return True
        
    def metadata(self) -> Dict[str, Any]:
        return {"name": "AnalyticsEngine"}
