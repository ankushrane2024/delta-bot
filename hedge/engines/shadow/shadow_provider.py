import logging
from typing import List, Dict, Optional, Any
import copy

from hedge.engines.execution_provider import AbstractExecutionProvider
from hedge.models.execution import ExecutionOrder

logger = logging.getLogger(__name__)

class ShadowExecutionProvider(AbstractExecutionProvider):
    """
    Pure transport wrapper for Shadow Trading.
    Forwards all read requests (connectivity, position, open orders) to the live Delta provider.
    Intercepts all write requests (submit_order, cancel_order) to prevent live trading.
    Passes intercepted orders to the ShadowExecutionSimulator.
    """
    
    def __init__(self, live_provider: AbstractExecutionProvider, simulator, config: Dict[str, Any] = None):
        self.live_provider = live_provider
        self.simulator = simulator
        self.active_shadow_orders: Dict[str, ExecutionOrder] = {}
        self.config = config or {}

    def _check_kill_switch(self):
        import os
        mode = self.config.get("BOT_MODE", os.getenv("BOT_MODE", ""))
        if mode != "SHADOW":
            raise RuntimeError(f"CRITICAL SECURITY: Shadow Provider invoked in non-SHADOW mode ({mode})")

    def initialize(self) -> None:
        logger.info("Initializing ShadowExecutionProvider (Wrapping Live Provider)")
        self.live_provider.initialize()

    def validate_connectivity(self) -> bool:
        return self.live_provider.validate_connectivity()

    def submit_order(self, order: ExecutionOrder) -> ExecutionOrder:
        """
        Intercepts order submission. 
        Never forwards to live provider.
        """
        self._check_kill_switch()
        logger.info(f"[SHADOW] Intercepted submit_order for {order.client_order_id}")
        # Hand off to simulator for life-cycle management
        return self.simulator.simulate_submission(order, self.active_shadow_orders)
        
    def cancel_order(self, client_order_id: str) -> bool:
        """
        Intercepts order cancellation.
        """
        self._check_kill_switch()
        logger.info(f"[SHADOW] Intercepted cancel_order for {client_order_id}")
        return self.simulator.simulate_cancellation(client_order_id, self.active_shadow_orders)
        
    def fetch_order_status(self, client_order_id: str) -> ExecutionOrder:
        """
        Returns shadow order status instead of live.
        """
        if client_order_id in self.active_shadow_orders:
            return copy.deepcopy(self.active_shadow_orders[client_order_id])
        return self.live_provider.fetch_order_status(client_order_id)

    def get_open_orders(self) -> List[ExecutionOrder]:
        """
        Returns purely shadow orders.
        """
        return [copy.deepcopy(o) for o in self.active_shadow_orders.values()]

    def fetch_position(self) -> dict:
        """
        Forwards to live provider so risk/sizing uses live wallet balance/positions, 
        unless PortfolioSynchronizer entirely owns the internal state (which it does).
        """
        return self.live_provider.fetch_position()
