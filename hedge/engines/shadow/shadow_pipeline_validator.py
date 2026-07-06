import logging
from hedge.ares_orchestrator import AresOrchestrator
from hedge.models.tick import TickResult

logger = logging.getLogger(__name__)

class ShadowPipelineValidator:
    """
    Pure wrapper/observer around the production AresOrchestrator.
    Guarantees exactly one production orchestrator exists.
    Calls tick() on the orchestrator, retrieves the immutable TickResult, 
    and feeds it into the ValidationEngine.
    """
    
    def __init__(self, orchestrator: AresOrchestrator, validation_engine):
        self.orchestrator = orchestrator
        self.validation_engine = validation_engine
        
    def start(self):
        logger.info("Starting ShadowPipelineValidator...")
        self.orchestrator.start()
        
    def tick(self) -> None:
        """
        Executes one production tick and extracts the result for validation.
        """
        # Execute the immutable production pipeline
        self.orchestrator.tick()
        
        # Extract the canonical immutable tick result
        tick_result: TickResult = self.orchestrator.latest_tick_result
        if not tick_result:
            return
            
        # Feed the pure observer
        self.validation_engine.observe_tick(tick_result)
