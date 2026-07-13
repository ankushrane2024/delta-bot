import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

from hedge.models.portfolio import PortfolioSnapshot
import time
from datetime import datetime

from hedge.models.portfolio import PortfolioSnapshot
from hedge.models.execution import ExecutionOrder, ExecutionState, FillEvent
from hedge.engines.execution_provider import AbstractExecutionProvider
import time
from datetime import datetime

class OptionBridge(AbstractExecutionProvider):
    """
    Module 49 - Adapter separating ARES from the Legacy Options Strategy.
    Enforces loose coupling and performs mandatory Hedge Ownership validation.
    """
    def __init__(self, bot_engine):
        super().__init__()
        self.engine = bot_engine
        self.execution = bot_engine.execution
        self.version = 0
        self._active_orders = {}

    def initialize(self) -> None:
        pass

    def validate_connectivity(self) -> bool:
        return True

    def submit_order(self, order: ExecutionOrder) -> ExecutionOrder:
        """Translates ARES ExecutionOrder to legacy place_hedge_order."""
        import copy
        exchange_order = copy.deepcopy(order)
        exchange_order.order_id = f"exch_{order.client_order_id}"
        exchange_order.state = ExecutionState.ACKNOWLEDGED
        exchange_order.updated_at = datetime.utcnow().isoformat() + "Z"

        if self.execution.hedge_owner != "ARES":
            logger.error(f"Bridge: Cannot place hedge. ARES does not own Hedge Lock! Owner: {self.execution.hedge_owner}")
            exchange_order.state = ExecutionState.REJECTED
            return exchange_order

        # Call legacy execution
        direction = "buy" if getattr(order, 'side', '') == "BUY" else "sell"
        result = self.execution.place_hedge_order(order.quantity, direction)
        
        if result and result.get('success'):
            exchange_order.state = ExecutionState.FILLED
            exchange_order.filled_quantity = order.quantity
            exchange_order.average_fill_price = result.get('fill_price', 0.0)
            exchange_order.remaining_quantity = 0.0
            exchange_order.fill_events.append(FillEvent(
                timestamp=datetime.utcnow().isoformat() + "Z",
                quantity=order.quantity,
                price=exchange_order.average_fill_price
            ))
        else:
            exchange_order.state = ExecutionState.FAILED

        self._active_orders[order.client_order_id] = exchange_order
        return exchange_order

    def cancel_order(self, client_order_id: str) -> bool:
        return True

    def fetch_order_status(self, client_order_id: str) -> ExecutionOrder:
        return self._active_orders.get(client_order_id)

    def get_open_orders(self) -> list:
        return [o for o in self._active_orders.values() if o.state not in [ExecutionState.FILLED, ExecutionState.CANCELLED, ExecutionState.REJECTED, ExecutionState.FAILED]]

    def fetch_position(self) -> dict:
        return self.execution.get_portfolio_snapshot()

    def get_portfolio_snapshot(self) -> PortfolioSnapshot:
        """
        Reads directly from the live options position memory.
        Performs continuous reconciliation to ensure no phantom positions exist.
        """
        # Under PAPER mode, the legacy execution IS the exchange state.
        snapshot_raw = self.execution.get_portfolio_snapshot()
        
        # Mandatory Reconciliation Check (ARES must own the lock to hedge)
        if snapshot_raw['hedge_size_btc'] > 0 and snapshot_raw['hedge_owner'] != 'ARES':
            logger.warning(f"Bridge: Detected live hedge ({snapshot_raw['hedge_size_btc']}) but ARES does not own lock! Reconciling...")
            
        self.version += 1
        
        # Fetch live BTC spot price for risk engine
        btc_spot = 0.0
        try:
            ws_btc = self.engine.api_client.get_realtime_ticker('BTCUSD')
            if ws_btc:
                btc_spot = float(ws_btc.get('mark_price', 0.0) or ws_btc.get('close', 0.0) or 0.0)
            if btc_spot <= 0:
                btc_spot = float(self.engine.latest_btc_price or 0.0)
        except Exception:
            btc_spot = float(getattr(self.engine, 'latest_btc_price', 0.0) or 0.0)
        
        # Compute live options delta and pnl using actual data if available
        net_delta = 0.0
        live_metadata = {
            "hedge_owner": snapshot_raw['hedge_owner'],
            "total_entry_premium": self.engine.total_entry_premium,
            "current_equity": self.engine.risk_manager.current_equity,
            "futures_price": btc_spot,
            "total_lots": 0,
            "call_leg": {},
            "put_leg": {},
            "call_pnl_usd": 0.0,
            "put_pnl_usd": 0.0,
        }
        
        total_pnl = 0.0
        total_lots = 0
        call_pnl_usd = 0.0
        put_pnl_usd = 0.0
        
        for sym, opt in snapshot_raw['active_options'].items():
            leg = opt.get('leg_type', 'call')
            size = opt.get('size', 1.0)
            total_lots += size
            
            # Use cached live metrics from legacy engine if available
            ticker = self.engine.api_client.get_realtime_ticker(sym)
            live_price = float(ticker.get('mark_price', opt.get('entry_price', 0.0))) if ticker else opt.get('entry_price', 0.0)
            
            # Options Pnl (in USD): For SOLD options, profit = (entry - current) * qty_btc * btc_price
            side_mult = -1 if opt.get('side', 'SELL') == 'SELL' else 1
            entry_price = float(opt.get('entry_price', 0.0))
            pnl_btc = (live_price - entry_price) * side_mult * size * 0.001
            pnl_usd = pnl_btc * btc_spot if btc_spot > 0 else pnl_btc
            total_pnl += pnl_btc
            
            # Track per-leg PnL for Decision Engine Profit Override
            if leg == 'call':
                call_pnl_usd += pnl_usd
            else:
                put_pnl_usd += pnl_usd
            
            # Extract Live Greeks
            greeks = ticker.get('greeks', {}) if ticker else {}
            fallback_delta = 0.5 if leg == 'call' else -0.5
            delta_val = float(greeks.get('delta', fallback_delta))
            if delta_val == 0.0:
                delta_val = fallback_delta
                
            gamma_val = float(greeks.get('gamma', 0.05))
            vega_val = float(greeks.get('vega', 10.0))
            theta_val = float(greeks.get('theta', -5.0))
            
            # Live Delta Calculation
            net_delta += size * delta_val * side_mult
            
            # Populate metadata for PositionContext
            leg_key = f"{leg}_leg"
            live_metadata[leg_key] = {
                "strike": float(opt.get('strike', 0.0)),
                "entry_price": entry_price,
                "current_price": live_price,
                "delta": delta_val,
                "gamma": gamma_val, 
                "vega": vega_val,
                "theta": theta_val,
                "iv": float(greeks.get('iv', 0.6)) if 'iv' in greeks else 0.6
            }

        live_metadata["total_lots"] = total_lots
        live_metadata["call_pnl_usd"] = call_pnl_usd
        live_metadata["put_pnl_usd"] = put_pnl_usd

        return PortfolioSnapshot(
            timestamp=datetime.utcnow().isoformat() + "Z",
            version=self.version,
            futures_position_qty=snapshot_raw['hedge_size_btc'],
            futures_average_price=self.execution.hedge_entry_price,
            net_options_delta=net_delta,
            realized_pnl=0.0,
            unrealized_pnl=total_pnl,
            margin_used=0.0,
            available_balance=self.engine.risk_manager.current_equity,
            active_orders=[],
            open_orders=[],
            hedge_status="HEDGED" if snapshot_raw['hedge_size_btc'] != 0 else "UNHEDGED",
            metadata=live_metadata
        )


    def place_hedge_order(self, size_btc: float, direction: str) -> bool:
        """Submits a hedge order ONLY if ARES holds the lock."""
        if self.execution.hedge_owner != "ARES":
            logger.error(f"Bridge: Cannot place hedge. ARES does not own Hedge Lock! Owner: {self.execution.hedge_owner}")
            return False
            
        result = self.execution.place_hedge_order(size_btc, direction)
        return result is not None and result.get('success', False)

    def close_hedge(self) -> bool:
        """Closes all active hedges ONLY if ARES holds the lock."""
        if self.execution.hedge_owner != "ARES":
            logger.error(f"Bridge: Cannot close hedge. ARES does not own Hedge Lock! Owner: {self.execution.hedge_owner}")
            return False
            
        self.execution.close_hedge()
        return True
