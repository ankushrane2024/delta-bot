import logging
import time
from typing import Optional, Any, Dict
from datetime import datetime, timezone

from hedge.models.core_interfaces import Clock, AbstractMarketDataProvider
from hedge.models.events import EventBus
from hedge.engines.execution_provider import AbstractExecutionProvider
from hedge.models.core_interfaces import ExecutionStore, InMemoryExecutionStore

# Frozen Engines
from hedge.engines.regime_engine import MarketRegimeEngine
from hedge.engines.trend_engine import TrendEngine
from hedge.engines.position_risk_engine import PositionRiskEngine
from hedge.engines.decision_engine import DecisionEngine
from hedge.engines.sizing_engine import HedgeSizingEngine
from hedge.engines.hedge_manager import HedgeManager
from hedge.engines.state_machine import ExecutionStateMachine
from hedge.engines.portfolio_synchronizer import PortfolioSynchronizer
from hedge.engines.data_adapters import PositionContextAdapter

# Analyzers
from hedge.analyzers.price_action_analyzer import PriceActionAnalyzer
from hedge.analyzers.volatility_analyzer import VolatilityAnalyzer
from hedge.analyzers.volume_analyzer import VolumeAnalyzer

# Models
from hedge.models.position import StressFusionBreakdown
from hedge.context.market_context import MarketContext
from hedge.models.tick import TickResult

logger = logging.getLogger(__name__)

class AresOrchestrator:
    """
    Module 37: End-to-End Pipeline Integration
    
    The AresOrchestrator wires together every mathematical and execution engine exactly once.
    It encapsulates the event loop to execute the pipeline:
    Market Data -> Trend -> Regime -> Risk -> Decision -> Sizing -> Hedge -> Execution -> Portfolio
    
    It keeps the orchestration extremely thin, coordinating data flow without introducing 
    new business logic.
    """
    def __init__(
        self,
        market_data_provider: AbstractMarketDataProvider,
        execution_provider: AbstractExecutionProvider,
        clock: Clock,
        event_bus: EventBus,
        execution_store: Optional[ExecutionStore] = None,
        **kwargs
    ):
        self.market_data_provider = market_data_provider
        self.execution_provider = execution_provider
        self.clock = clock
        self.event_bus = event_bus
        self.execution_store = execution_store or InMemoryExecutionStore()
        self.option_bridge = kwargs.get('option_bridge')
        self.bot_engine_ref = kwargs.get('bot_engine')  # Reference to read live ADX+BB+RSI filter
        
        # Determine if we are running in deterministic replay mode
        self.replay_mode = "ReplayClock" in clock.__class__.__name__

        # Initialize frozen mathematical engines
        self.regime_engine = MarketRegimeEngine()
        
        analyzers = {
            "price_action": PriceActionAnalyzer(),
            "volatility": VolatilityAnalyzer(),
            "volume": VolumeAnalyzer()
        }
        self.trend_engine = TrendEngine(analyzers=analyzers)
        self.risk_engine = PositionRiskEngine(replay_mode=self.replay_mode)
        self.decision_engine = DecisionEngine()
        self.sizing_engine = HedgeSizingEngine()
        self.hedge_manager = HedgeManager()
        
        # Initialize frozen execution engines
        self.state_machine = ExecutionStateMachine(
            provider=self.execution_provider,
            event_bus=self.event_bus,
            store=self.execution_store,
            clock=self.clock,
            replay_mode=self.replay_mode
        )
        
        self.portfolio_sync = PortfolioSynchronizer(
            provider=self.execution_provider,
            event_bus=self.event_bus,
            clock=self.clock,
            replay_mode=self.replay_mode
        )
        
        self.tick_number = 0
        self.latest_tick_result = None

    def start(self):
        """
        Initialization logic on startup.
        """
        logger.info("Starting Ares Orchestrator...")
        self.execution_provider.initialize()
        self.state_machine.recover()
        self.portfolio_sync.reconcile_with_provider()
        
    def tick(self) -> None:
        """
        Executes exactly one iteration of the ARES pipeline loop.
        """
        start_time = time.time()
        self.tick_number += 1
        try:
        
            # 0. State Machine scheduled tasks (Retries, polling)
            self.state_machine.process_due_actions(self.clock.now())
        
            # 1. Fetch live market data
            market_data = self.market_data_provider.get_latest_data()
            if not market_data:
                logger.debug("No market data available yet. Skipping tick.")
                return

            # 2. Portfolio Synchronization (Live from Bridge)
            if self.option_bridge:
                snapshot = self.option_bridge.get_portfolio_snapshot()
            else:
                self.portfolio_sync.reconcile_with_provider()
                snapshot = self.portfolio_sync.current_snapshot

            # Extract market attributes (Run Trend & Regime even if idle for UI telemetry)
            trend_context = MarketContext(
                current_price=market_data.get("spot_price", 0.0),
                funding_rate=market_data.get("funding", 0.0),
                metadata={
                    "timestamp": market_data.get("timestamp", self.clock.now()),
                    "open_interest": market_data.get("open_interest", 0.0),
                    "volume_24h": market_data.get("volume", 0.0),
                    "implied_volatility": market_data.get("iv", 0.0)
                }
            )

            # 3. Trend Engine
            trend_result = self.trend_engine.evaluate(trend_context)
            
            # 3.5 Inject Live ADX+BB+RSI Signal from filters.py into TrendResult
            # This bridges the 15m multi-indicator regime into the ARES pipeline
            try:
                if self.bot_engine_ref and hasattr(self.bot_engine_ref, 'filters'):
                    external_signal = getattr(self.bot_engine_ref.filters, 'last_detailed_signal', None)
                    if external_signal:
                        trend_result.debug_information["external_regime"] = external_signal
                        logger.debug(f"Injected external regime: {external_signal}")
            except Exception as e:
                logger.warning(f"Could not inject external regime: {e}")
        
            # 4. Market Regime Engine
            regime_result = self.regime_engine.evaluate(trend_result)

            # IDLE MODE: If no options are open and no hedge is active, skip Risk processing
            has_options = snapshot.metadata.get("total_entry_premium", 0.0) > 0.0
            if not has_options and snapshot.futures_position_qty == 0:
                # Return partial tick result so UI shows live market trend/regime
                self.latest_tick_result = TickResult(
                    tick_number=self.tick_number,
                    timestamp=self.clock.now(),
                    market_context=trend_context,
                    trend_result=trend_result,
                    regime_result=regime_result,
                    risk_result=None,
                    hedge_sizing=None,
                    hedge_decision=None,
                    portfolio_snapshot=snapshot,
                    pipeline_latency=time.time() - start_time,
                    provider_health="GREEN"
                )
                return

            # 5. Create Position Context (Adapter)
            if self.option_bridge:
                # Build context from LIVE legacy position
                pos_context = PositionContextAdapter.from_snapshot(snapshot)
                # CRITICAL: Also inject live BTC price from market data as a safety fallback
                spot = market_data.get("spot_price", 0.0)
                if spot > 0 and (pos_context.futures_price <= 0):
                    pos_context.futures_price = spot
            else:
                pos_context = PositionContextAdapter.from_snapshot(snapshot)
                # Inject live market data overrides for mock
                pos_context.futures_price = market_data.get("spot_price", pos_context.futures_price)
                pos_context.short_call_strike = market_data.get("spot_price", pos_context.futures_price) # Mock ATM
                pos_context.short_put_strike = market_data.get("spot_price", pos_context.futures_price)
                pos_context.call_iv = market_data.get("iv", pos_context.call_iv)
                pos_context.put_iv = market_data.get("iv", pos_context.put_iv)
                call_greeks = market_data.get("call_greeks", {})
                pos_context.options_delta = call_greeks.get("delta", pos_context.options_delta)
                pos_context.call_delta = call_greeks.get("delta", pos_context.call_delta)
                pos_context.call_gamma = call_greeks.get("gamma", pos_context.call_gamma)
                pos_context.call_vega = call_greeks.get("vega", pos_context.call_vega)

            # 6. Position Risk Engine
            risk_result = self.risk_engine.evaluate(regime_result, trend_result, pos_context)

            # Extract Fusion Breakdown
            breakdown = None
            if risk_result.debug_information and "call_stress_breakdown" in risk_result.debug_information:
                call_breakdown = risk_result.debug_information["call_stress_breakdown"]
                if hasattr(call_breakdown, "fusion_breakdown"):
                    breakdown = call_breakdown.fusion_breakdown

            if not breakdown:
                breakdown = StressFusionBreakdown() # Fallback empty breakdown

            # 7. Decision Engine
            decision = self.decision_engine.evaluate(
                fused_score=risk_result.overall_risk_score,
                breakdown=breakdown,
                context=pos_context,
                current_hedge_ratio=snapshot.hedge_ratio,
                current_time=self.clock.now(),
                regime_result=regime_result
            )
            
            if decision.action.name != "HOLD" and decision.action.name != "MONITOR" and risk_result.overall_risk_score > 10.0:
                logger.info(f"ARES Decision: {decision.action.name} | Risk: {risk_result.overall_risk_score:.2f} | Reason: {decision.reason}")

            self.last_decision = decision
            sizing_result = None
            hedge_plan = None

            if decision.action.name != "HOLD":
                # 8. Hedge Sizing Engine
                sizing_result = self.sizing_engine.evaluate(
                    decision=decision,
                    context=pos_context,
                    current_hedge_qty=snapshot.futures_position_qty
                )
            
                # 9. Hedge Manager
                hedge_plan = self.hedge_manager.evaluate(
                    decision=decision,
                    sizing=sizing_result,
                    context=pos_context,
                    existing_hedge_qty=snapshot.futures_position_qty,
                    pending_orders=self.execution_store.get_active_orders(),
                    tick_number=self.tick_number,
                    portfolio_hash=snapshot.snapshot_hash
                )

                self.last_plan = hedge_plan

                # 10. Execution State Machine
                if hedge_plan:
                    self.state_machine.submit_plan(hedge_plan)
                
            # Generate canonical TickResult
            try:
                provider_health = 'GREEN' if self.execution_provider.validate_connectivity() else 'RED'
            except Exception as e:
                logger.error(f'Provider connectivity validation failed: {e}')
                provider_health = 'RED'

            self.latest_tick_result = TickResult(
                timestamp=self.clock.now(),
                tick_number=self.tick_number,
                market_context=trend_context,
                trend_result=trend_result,
                regime_result=regime_result,
                risk_result=risk_result,
                hedge_decision=decision,
                hedge_sizing=sizing_result,
                hedge_plan=hedge_plan,
                execution_summary={"active_orders": len(self.execution_store.get_active_orders())},
                portfolio_snapshot=snapshot,
                provider_health=provider_health,
                pipeline_latency=time.time() - start_time
            )
        except Exception as e:
            logger.error(f'Fatal error in ARES Pipeline tick: {e}', exc_info=True)
            self.metrics = getattr(self, "metrics", {})
            self.metrics["execution_failures"] = self.metrics.get("execution_failures", 0) + 1
