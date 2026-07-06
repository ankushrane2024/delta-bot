import threading
import logging
from typing import List, Dict

from hedge.models.core_interfaces import SystemClock, Clock
from hedge.models.execution import ExecutionOrder, ExecutionState
from hedge.models.events import EventBus

from hedge.engines.execution_provider import AbstractExecutionProvider
from hedge.engines.delta.auth import DeltaAuthenticator
from hedge.engines.delta.rate_limiter import TokenBucketRateLimiter
from hedge.engines.delta.product_catalog import ProductCatalog
from hedge.engines.delta.rest_client import DeltaRestClient, ProviderUnavailable
from hedge.engines.delta.ws_client import DeltaWebSocketClient
from hedge.engines.delta.normalizer import DeltaMessageNormalizer

logger = logging.getLogger("ARES.DeltaProvider")

class DeltaExecutionProvider(AbstractExecutionProvider):
    def __init__(self, api_key: str, api_secret: str, rest_url: str, ws_url: str, event_bus: EventBus, clock: Clock = None):
        self.clock = clock or SystemClock()
        self.event_bus = event_bus
        
        self.auth = DeltaAuthenticator(api_key, api_secret)
        self.rate_limiter = TokenBucketRateLimiter(self.clock, requests_per_second=5.0)
        self.catalog = ProductCatalog(rest_url)
        self.rest = DeltaRestClient(rest_url, self.auth, self.clock, self.rate_limiter)
        self.ws = DeltaWebSocketClient(ws_url, self.auth, self.clock)
        
        self.ws.set_callbacks(
            on_message=self._handle_ws_message,
            on_gap=self._handle_ws_gap,
            on_reconnect=self._handle_ws_reconnect
        )
        
        self._exchange_orders: Dict[str, ExecutionOrder] = {}
        self._exchange_position = {
            'quantity': 0.0,
            'average_entry': 0.0,
            'direction': "NONE",
            'open_orders': 0,
            'hedge_ratio': 0.0,
            'margin': 0.0
        }
        self.lock = threading.RLock()

    def initialize(self) -> None:
        logger.info("Initializing DeltaExecutionProvider...")
        self.catalog.load_or_refresh(force=True)
        self.ws.connect()
        self._sync_state_from_rest()

    def validate_connectivity(self) -> bool:
        try:
            self.catalog.load_or_refresh()
            return True
        except:
            return False

    def submit_order(self, order: ExecutionOrder) -> ExecutionOrder:
        pid = self.catalog.get_product_id(order.symbol)
        try:
            resp = self.rest.place_order(pid, order.quantity, order.side, order.order_type, order.client_order_id)
            with self.lock:
                normalized = DeltaMessageNormalizer.parse_order(resp, self.catalog)
                self._exchange_orders[normalized.client_order_id] = normalized
                return normalized
        except ProviderUnavailable as e:
            logger.error(f"Failed to submit order: {e}")
            order.state = ExecutionState.FAILED
            order.reason = str(e)
            return order

    def cancel_order(self, client_order_id: str) -> bool:
        try:
            self.rest.cancel_order(client_order_id=client_order_id)
            return True
        except ProviderUnavailable as e:
            logger.error(f"Failed to cancel order: {e}")
            return False

    def fetch_order_status(self, client_order_id: str) -> ExecutionOrder:
        with self.lock:
            if client_order_id in self._exchange_orders:
                return self._exchange_orders[client_order_id]
        
        # Fallback to REST
        resp = self.rest.get_order(client_order_id)
        normalized = DeltaMessageNormalizer.parse_order(resp, self.catalog)
        with self.lock:
            self._exchange_orders[client_order_id] = normalized
        return normalized

    def get_open_orders(self) -> List[ExecutionOrder]:
        with self.lock:
            return [o for o in self._exchange_orders.values() if o.state in [ExecutionState.ACKNOWLEDGED, ExecutionState.PARTIALLY_FILLED, ExecutionState.CANCEL_PENDING]]

    def fetch_position(self) -> dict:
        with self.lock:
            self._exchange_position['open_orders'] = len(self.get_open_orders())
            return self._exchange_position.copy()

    def _sync_state_from_rest(self):
        """Reconcile internal caches from REST source of truth."""
        with self.lock:
            try:
                # Sync orders
                open_orders = self.rest.get_open_orders()
                for o in open_orders:
                    norm = DeltaMessageNormalizer.parse_order(o, self.catalog)
                    self._exchange_orders[norm.client_order_id] = norm
                    
                # Sync positions
                positions = self.rest.get_positions()
                for p in positions:
                    pid = p.get("product_id")
                    if pid and self.catalog.get_symbol(pid) == "BTCUSD":
                        self._exchange_position['quantity'] = float(p.get("size", 0.0))
                        self._exchange_position['average_entry'] = float(p.get("entry_price", 0.0))
                        self._exchange_position['direction'] = "NONE" if self._exchange_position['quantity'] == 0 else ("LONG" if self._exchange_position['quantity'] > 0 else "SHORT")
                        
                # Sync margin
                wallet = self.rest.get_wallet_balances()
                for w in wallet:
                    if w.get("asset_id") == 2: # USDT usually
                        self._exchange_position['margin'] = float(w.get("balance", 0.0))
            except ProviderUnavailable as e:
                logger.error(f"REST Sync failed: {e}")

    def _handle_ws_message(self, data: dict):
        # We only care about order/position events
        # In a real payload, delta sends channel name
        channel = data.get("type", "")
        if channel == "order":
            norm = DeltaMessageNormalizer.parse_order(data, self.catalog)
            with self.lock:
                self._exchange_orders[norm.client_order_id] = norm
            event = DeltaMessageNormalizer.create_event(norm, self.clock.now())
            if event:
                self.event_bus.publish(event)
                
        elif channel == "position":
            pid = data.get("product_id")
            if pid and self.catalog.get_symbol(pid) == "BTCUSD":
                with self.lock:
                    self._exchange_position['quantity'] = float(data.get("size", 0.0))
                    self._exchange_position['average_entry'] = float(data.get("entry_price", 0.0))
                    self._exchange_position['direction'] = "NONE" if self._exchange_position['quantity'] == 0 else ("LONG" if self._exchange_position['quantity'] > 0 else "SHORT")

    def _handle_ws_gap(self):
        logger.warning("WS Gap. Forcing REST sync.")
        self._sync_state_from_rest()

    def _handle_ws_reconnect(self):
        logger.warning("WS Reconnected. Forcing REST sync.")
        self._sync_state_from_rest()
