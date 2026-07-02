from typing import Dict, Any
from .base_engine import AbstractBaseEngine

class VolatilityEngine(AbstractBaseEngine):

    def initialize(self) -> None:
        pass
        
    def evaluate(self, *args, **kwargs) -> Any:
        pass
        
    def reset(self) -> None:
        pass
        
    def health(self) -> bool:
        return True
        
    def metadata(self) -> Dict[str, Any]:
        return {"name": "VolatilityEngine"}
