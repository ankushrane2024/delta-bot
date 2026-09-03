import sys
import logging
from unittest.mock import MagicMock
from hedge.ares_orchestrator import AresOrchestrator
from hedge.engines.execution_provider import PaperExecutionProvider
from hedge.models.core_interfaces import Clock, AbstractMarketDataProvider
from datetime import datetime

class MockClock(Clock):
    def now(self):
        return datetime.utcnow()
    def now_iso(self):
        return datetime.utcnow().isoformat()

class MockMarketDataProvider(AbstractMarketDataProvider):
    def __init__(self, clock):
        self._clock = clock
        self._data = {}
    def get_latest_data(self):
        return self._data
    def inject_tick(self, data):
        self._data = data
from hedge.models.events import EventBus

# Configure logging for the test
logging.basicConfig(level=logging.INFO, format='%(asctime)s - ARES TEST - %(message)s')
logger = logging.getLogger("system")

def run_reversal_test():
    clock = MockClock()
    market_provider = MockMarketDataProvider(clock)
    event_bus = EventBus()
    execution = PaperExecutionProvider(clock)
    
    # Mock bot engine filters
    bot_engine = MagicMock()
    bot_engine.filters.last_detailed_signal = "CONFIRMED_TREND"
    
    # Initialize Orchestrator
    orchestrator = AresOrchestrator(
        market_data_provider=market_provider,
        execution_provider=execution,
        clock=clock,
        event_bus=event_bus,
        bot_engine=bot_engine
    )
    
    orchestrator.start()
    
    # Step 1: Normal Market (Options Open, BTC at 65000)
    market_provider.inject_tick({
        "spot_price": 65000.0,
        "iv": 0.50,
        "call_greeks": {"delta": -0.10, "gamma": 0.01, "vega": 10, "theta": -5}
    })
    
    # Mock Snapshot: Short Call 66000
    from hedge.models.portfolio import PortfolioSnapshot
    def get_mock_snapshot(futures_qty=0.0, futures_price=0.0):
        return PortfolioSnapshot(
            timestamp="2026-07-18",
            version=1,
            futures_position_qty=futures_qty,
            futures_average_price=futures_price,
            net_options_delta=-0.10,
            realized_pnl=0.0,
            unrealized_pnl=-50.0,
            margin_used=1000.0,
            available_balance=10000.0,
            active_orders=[],
            open_orders=[],
            hedge_status="UNHEDGED" if futures_qty == 0 else "HEDGED",
            metadata={
                "total_entry_premium": 200.0,
                "total_lots": 1.0,
                "call_leg": {"strike": 66000.0, "entry_price": 0.05, "current_price": 0.06},
                "put_leg": {},
                "call_pnl_usd": -50.0,
                "put_pnl_usd": 0.0,
                "hedge_pnl_usd": 0.0
            }
        )
    
    # Override portfolio sync to inject mock snapshot
    orchestrator.portfolio_sync.current_snapshot = get_mock_snapshot()
    
    print("\n--- TICK 1: NORMAL MARKET ---")
    orchestrator.tick()
    res1 = orchestrator.latest_tick_result
    print(f"Risk Score: {res1.risk_result.overall_risk_score:.2f}")
    print(f"Decision: {res1.hedge_decision.action.name if res1.hedge_decision else 'WAITING'}")
    
    # Step 2: Massive Pump (BTC goes to 67000, Call Delta spikes to -0.60)
    market_provider.inject_tick({
        "spot_price": 67000.0,
        "iv": 0.80,
        "call_greeks": {"delta": -0.60, "gamma": 0.05, "vega": 20, "theta": -15}
    })
    snap2 = get_mock_snapshot()
    snap2.unrealized_pnl = -600.0 # Massive loss
    snap2.metadata["call_pnl_usd"] = -600.0
    snap2.net_options_delta = -0.60
    orchestrator.portfolio_sync.current_snapshot = snap2
    
    print("\n--- TICK 2: MASSIVE PRICE PUMP ---")
    orchestrator.tick()
    res2 = orchestrator.latest_tick_result
    print(f"Risk Score: {res2.risk_result.overall_risk_score:.2f}")
    print(f"Decision: {res2.hedge_decision.action.name}")
    print(f"Reason: {res2.hedge_decision.reason}")
    print(f"Hedge Plan: {res2.hedge_plan.target_quantity if res2.hedge_plan else 'None'} BTC")
    
    # Mock executing the hedge
    execution.submit_order = MagicMock()
    
    # Step 3: Trend Reverses / Dumps back to 65000!
    market_provider.inject_tick({
        "spot_price": 65000.0,
        "iv": 0.50,
        "call_greeks": {"delta": -0.10, "gamma": 0.01, "vega": 10, "theta": -5}
    })
    snap3 = get_mock_snapshot(futures_qty=0.60, futures_price=67000.0)
    snap3.unrealized_pnl = 50.0 # Recovered options
    snap3.metadata["call_pnl_usd"] = 50.0
    snap3.metadata["hedge_pnl_usd"] = (67000.0 - 65000.0) * -0.60 # Short futures losing, or wait, hedge was a BUY (0.60 qty)
    snap3.metadata["hedge_pnl_usd"] = (65000.0 - 67000.0) * 0.60 # -1200
    orchestrator.portfolio_sync.current_snapshot = snap3
    
    # To trigger Gate 1 Profit Override or DPL, options are in profit!
    
    print("\n--- TICK 3: TREND REVERSAL (PRICE DUMPS BACK TO 65K) ---")
    orchestrator.tick()
    res3 = orchestrator.latest_tick_result
    print(f"Risk Score: {res3.risk_result.overall_risk_score:.2f}")
    print(f"Decision: {res3.hedge_decision.action.name}")
    print(f"Reason: {res3.hedge_decision.reason}")

if __name__ == "__main__":
    run_reversal_test()
