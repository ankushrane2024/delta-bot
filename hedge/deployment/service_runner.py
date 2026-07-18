import logging
import signal
import sys
import time
import threading
from unittest.mock import Mock

from hedge.deployment.config import AresConfig
from hedge.deployment.logger import initialize_all_loggers
from hedge.deployment.startup_validator import StartupValidator
from hedge.deployment.recovery_manager import RecoveryManager
from hedge.deployment.health_monitor import HealthMonitor

from hedge.ares_orchestrator import AresOrchestrator
from hedge.engines.execution_provider import PaperExecutionProvider
from hedge.engines.shadow.shadow_provider import ShadowExecutionProvider
from hedge.engines.shadow.shadow_execution_simulator import ShadowExecutionSimulator
from hedge.engines.shadow.shadow_pipeline_validator import ShadowPipelineValidator
from hedge.engines.shadow.shadow_store import ShadowStore
from hedge.validation.validation_engine import ValidationEngine
from hedge.validation.shadow_analytics import ShadowAnalytics
from hedge.models.events import EventBus
from hedge.models.core_interfaces import SystemClock
from hedge.engines.adapters.legacy_market_feed import LegacyMarketFeedAdapter

logger = logging.getLogger("system")

class ServiceRunner:
    """
    Master entrypoint for ARES.
    Owns startup, DI, mode selection, shutdown, signal handling, and background services.
    The AresOrchestrator is completely unaware of this wrapper.
    """
    def __init__(self, mode_override: str = None, option_bridge=None, bot_engine=None):
        self.running = False
        self.config = AresConfig.load(mode_override=mode_override)
        initialize_all_loggers(self.config.log_dir, self.config)
        self.clock = SystemClock()
        self.event_bus = EventBus()
        self.store = None
        self.option_bridge = option_bridge
        self.bot_engine = bot_engine

    def _signal_handler(self, sig, frame):
        logger.info(f"Received termination signal ({sig}). Initiating graceful shutdown...")
        self.running = False

    def setup_orchestrator_and_validator(self):
        if self.option_bridge and hasattr(self.option_bridge, 'engine'):
            market_data = LegacyMarketFeedAdapter(self.option_bridge.engine, self.clock)
        else:
            raise RuntimeError("CRITICAL: OptionBridge or its engine is missing. Cannot boot ARES.")
        
        # Select provider based on mode
        if self.option_bridge:
            provider = self.option_bridge
            logger.info("ServiceRunner: Using OptionBridge as ExecutionProvider.")
        elif self.config.mode in ["SHADOW", "REPLAY"]:
            # Setup Shadow Mode
            live_provider = PaperExecutionProvider(clock=self.clock) # Primary Paper provider
            simulator = ShadowExecutionSimulator(event_bus=self.event_bus, clock=self.clock)
            provider = ShadowExecutionProvider(live_provider=live_provider, simulator=simulator)
        elif self.config.mode == "PAPER":
            provider = PaperExecutionProvider(clock=self.clock)
        elif self.config.mode == "LIVE":
            # Real DeltaExecutionProvider would go here
            raise NotImplementedError("CRITICAL: Live Delta provider not yet integrated. Aborting LIVE startup.")
        else: # DEV
            provider = PaperExecutionProvider(clock=self.clock)

        self.orchestrator = AresOrchestrator(
            market_data_provider=market_data,
            execution_provider=provider,
            clock=self.clock,
            event_bus=self.event_bus,
            option_bridge=self.option_bridge,
            bot_engine=self.bot_engine
        )
        
        # Setup validation components
        self.analytics = ShadowAnalytics()
        self.store = ShadowStore(db_path=self.config.sqlite_db_path)
        self.validation_engine = ValidationEngine(self.event_bus, self.store, self.analytics)
        self.health_monitor = HealthMonitor(self.analytics, time.time())
        
        # Wrap in ShadowPipelineValidator
        self.pipeline_validator = ShadowPipelineValidator(self.orchestrator, self.validation_engine)

    def start_dashboard(self):
        # We are using the main Flask app, so disable internal FastAPI Uvicorn
        logger.info("Internal dashboard API disabled. Using host Flask application.")
        pass

    def run(self):
        # HARD ENFORCE PAPER MODE
        if self.config.mode != "PAPER":
            logger.critical(f"CRITICAL: ARES must run in PAPER mode. Current mode: {self.config.mode}")
            raise RuntimeError(f"Live trading not approved. Only PAPER mode is permitted. Current mode: {self.config.mode}")

        logger.info(f"Booting ARES Service in {self.config.mode} mode...")
        
        # 1. Preflight Validation
        validator = StartupValidator(self.config)
        if not validator.run_all_checks():
            logger.critical("Preflight validation failed. Aborting startup.")
            return
            
        # 2. Setup DI
        self.setup_orchestrator_and_validator()
        
        # Verify provider is PaperExecutionProvider or OptionBridge for safety
        if not (isinstance(self.orchestrator.execution_provider, PaperExecutionProvider) or self.option_bridge) and self.config.mode == "PAPER":
            logger.critical("CRITICAL: Execution provider is NOT PaperExecutionProvider/OptionBridge in PAPER mode. Aborting.")
            raise RuntimeError("Live provider detected while in PAPER mode.")
        
        # 3. Idempotent Recovery
        recovery_manager = RecoveryManager(self.orchestrator)
        if not recovery_manager.execute_recovery():
            logger.critical("Recovery sequence failed. Aborting startup.")
            if self.store: self.store.close()
            return
            
        # 4. Start Background Services
        self.start_dashboard()
        self.pipeline_validator.start()
        
        # 5. Main Loop
        self.running = True
        logger.info("ARES Main Loop started.")
        try:
            while self.running:
                if self.config.mode in ["SHADOW", "REPLAY"]:
                    self.pipeline_validator.tick()
                else:
                    self.orchestrator.tick()
                    # In PAPER mode, orchestrator returns nothing directly, but we can capture latency 
                    # and increment ticks for the dashboard manually since ShadowPipelineValidator is bypassed.
                    if self.analytics:
                        with self.analytics._lock:
                            self.analytics.live_stats["total_ticks"] += 1
                time.sleep(1) # Simulated tick delay
        except Exception as e:
            logger.error(f"Fatal error in main loop: {e}", exc_info=True)
        finally:
            self.shutdown()

    def shutdown(self):
        logger.info("Executing graceful shutdown sequence...")
        
        # Suspend new work
        self.running = False
        
        # Flush SQLite
        if self.store:
            logger.info("Flushing SQLite queues...")
            self.store.close()
            
        # The EventBus and Provider would be cleanly closed here
        # E.g. self.orchestrator.execution_provider.disconnect()
        
        logger.info("Shutdown complete.")

if __name__ == "__main__":
    runner = ServiceRunner()
    runner.run()
