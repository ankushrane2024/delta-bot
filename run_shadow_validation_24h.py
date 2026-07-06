import logging
import time
import os
import uvicorn
import threading
from unittest.mock import Mock

from hedge.ares_orchestrator import AresOrchestrator
from hedge.engines.shadow.shadow_provider import ShadowExecutionProvider
from hedge.engines.shadow.shadow_execution_simulator import ShadowExecutionSimulator
from hedge.engines.shadow.shadow_pipeline_validator import ShadowPipelineValidator
from hedge.engines.shadow.shadow_store import ShadowStore
from hedge.validation.validation_engine import ValidationEngine
from hedge.validation.shadow_analytics import ShadowAnalytics
from hedge.engines.execution_provider import PaperExecutionProvider
from hedge.models.events import EventBus
from hedge.models.core_interfaces import SystemClock

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ShadowValidation")

def run_dashboard():
    from hedge.engines.shadow.dashboard_api import app, ShadowAnalytics
    # uvicorn runs the FastAPI app
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")

def main():
    logger.info("Initializing 24h Shadow Validation...")
    
    # 1. Base dependencies
    clock = SystemClock()
    event_bus = EventBus()
    
    # 2. Mock Market Data for running without real internet
    mock_market_data = Mock()
    mock_market_data.get_latest_data.return_value = {
        "spot_price": 50000.0,
        "funding": 0.01,
        "timestamp": clock.now(),
        "open_interest": 1000.0,
        "volume": 5000.0,
        "iv": 0.6,
        "call_greeks": {"delta": 0.5, "gamma": 0.05, "vega": 10.0}
    }
    
    # 3. Shadow Execution Layer
    live_provider = PaperExecutionProvider(clock=clock) # Using paper as fake "live" for this test
    simulator = ShadowExecutionSimulator(event_bus=event_bus, clock=clock)
    shadow_provider = ShadowExecutionProvider(live_provider=live_provider, simulator=simulator)
    
    # 4. Orchestrator
    orchestrator = AresOrchestrator(
        market_data_provider=mock_market_data,
        execution_provider=shadow_provider,
        clock=clock,
        event_bus=event_bus
    )
    
    # 5. Validation & Analytics Layer
    analytics = ShadowAnalytics()
    store = ShadowStore(db_path="shadow_validation_24h.db")
    validation_engine = ValidationEngine(event_bus=event_bus, store=store, analytics=analytics)
    
    # 6. Pipeline Validator Wrapper
    validator = ShadowPipelineValidator(orchestrator=orchestrator, validation_engine=validation_engine)
    
    # 7. Start Dashboard
    from hedge.engines.shadow.dashboard_api import app
    app.state.analytics = analytics
    app.state.db_path = "shadow_validation_24h.db"
    
    dashboard_thread = threading.Thread(target=run_dashboard, daemon=True)
    dashboard_thread.start()
    
    # 8. Start Validation
    validator.start()
    
    logger.info("Starting shadow loop (simulating 10 ticks for test). Dashboard running on port 8000.")
    try:
        for i in range(10): # Usually this would be a while True loop with time.sleep
            validator.tick()
            time.sleep(1) # Simulating 1 tick per second
            
    except KeyboardInterrupt:
        logger.info("Shadow Validation interrupted.")
    finally:
        logger.info("Shutting down...")
        store.close()
        
if __name__ == "__main__":
    main()
