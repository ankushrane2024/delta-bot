from abc import ABC, abstractmethod
from typing import Dict, Any

class AbstractBaseEngine(ABC):
    
    @abstractmethod
    def initialize(self) -> None:
        pass
        
    @abstractmethod
    def evaluate(self, *args, **kwargs) -> Any:
        pass
        
    @abstractmethod
    def reset(self) -> None:
        pass
        
    @abstractmethod
    def health(self) -> bool:
        pass
        
    @abstractmethod
    def metadata(self) -> Dict[str, Any]:
        pass
