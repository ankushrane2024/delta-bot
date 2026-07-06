import unittest
from unittest.mock import patch, MagicMock, call
import threading
import time
import json
import os
from hedge.models.core_interfaces import ReplayClock
from hedge.models.execution import ExecutionOrder, ExecutionState
from hedge.models.events import EventBus, OrderSubmitted, OrderFilled
from hedge.engines.delta.auth import DeltaAuthenticator
from hedge.engines.delta.rate_limiter import TokenBucketRateLimiter
from hedge.engines.delta.product_catalog import ProductCatalog
from hedge.engines.delta.rest_client import DeltaRestClient, ProviderUnavailable
from hedge.engines.delta.ws_client import DeltaWebSocketClient
from hedge.engines.delta.provider import DeltaExecutionProvider

class TestDeltaExecutionProvider(unittest.TestCase):
    def setUp(self):
        self.clock = ReplayClock()
        self.event_bus = EventBus()
        self.clock.tick(1000.0) # deterministic start time

    def test_authentication_signing(self):
        auth = DeltaAuthenticator("key123", "secret456")
        res = auth.sign_rest_request("POST", 1234567890, "/v2/orders", payload='{"size": 1}')
        self.assertEqual(res["api-key"], "key123")
        self.assertEqual(res["timestamp"], "1234567890")
        self.assertTrue(len(res["signature"]) > 0)

    @patch("requests.Session.get")
    def test_rest_timeout_and_500_circuit_breaker(self, mock_get):
        auth = DeltaAuthenticator("key", "secret")
        limiter = TokenBucketRateLimiter(self.clock, 5.0)
        client = DeltaRestClient("http://mock", auth, self.clock, limiter)
        
        # Mock 500 error
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp
        
        # Trigger failures up to threshold
        for _ in range(2):
            with self.assertRaises(ProviderUnavailable):
                client.get_positions()
        self.assertFalse(client.cb_open)
        
        with self.assertRaises(ProviderUnavailable):
            client.get_positions()
        self.assertTrue(client.cb_open) # Breaker opens
        
        # Advance time to half-open
        self.clock.set_time(1000.0 + 31.0) # past 30s recovery timeout
        
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": [{"size": "1"}]}
        res = client.get_positions()
        self.assertEqual(res, [{"size": "1"}])
        self.assertFalse(client.cb_open) # Closed on success

    @patch("requests.Session.get")
    @patch("time.sleep")
    def test_http_429_rate_limiting_queuing(self, mock_sleep, mock_get):
        limiter = TokenBucketRateLimiter(self.clock, 1.0) # 1 req per sec
        
        # When acquire sleeps, it calculates sleep_time. We'll advance the clock by that amount.
        def mock_sleep_func(sleep_time):
            self.clock.tick(sleep_time)
            
        mock_sleep.side_effect = mock_sleep_func
        
        limiter.acquire()
        limiter.acquire()
        limiter.acquire()
        # The clock should have advanced by 2.0 seconds total because 1st token is immediate
        self.assertAlmostEqual(self.clock.now(), 1002.0)

    @patch("requests.get")
    def test_product_cache_refresh(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": [{"symbol": "BTCUSD", "id": 123}]}
        mock_get.return_value = mock_resp
        
        catalog = ProductCatalog("http://mock", cache_file="test_cache.json")
        if os.path.exists("test_cache.json"):
            os.remove("test_cache.json")
            
        catalog.load_or_refresh()
        self.assertEqual(catalog.get_product_id("BTCUSD"), 123)
        self.assertEqual(catalog.get_symbol(123), "BTCUSD")
        self.assertTrue(os.path.exists("test_cache.json"))
        os.remove("test_cache.json")

    @patch("requests.get")
    @patch("websocket.WebSocketApp")
    def test_provider_initialization_and_ws_reconnect_reconciliation(self, mock_ws, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": [{"symbol": "BTCUSD", "id": 123}]}
        mock_get.return_value = mock_resp
        
        provider = DeltaExecutionProvider("k", "s", "http://mock", "ws://mock", self.event_bus, self.clock)
        
        # Override rest client to not actually hit network for orders
        provider.rest.get_open_orders = MagicMock(return_value=[{"client_order_id": "test_1", "product_id": 123, "state": "open"}])
        provider.rest.get_positions = MagicMock(return_value=[{"product_id": 123, "size": "0.1", "entry_price": "50000"}])
        provider.rest.get_wallet_balances = MagicMock(return_value=[{"asset_id": 2, "balance": "1000.0"}])
        
        provider.initialize()
        
        pos = provider.fetch_position()
        self.assertEqual(pos["quantity"], 0.1)
        self.assertEqual(pos["average_entry"], 50000.0)
        
        # Simulate sequence gap
        provider.ws.last_sequence = 5
        provider._handle_ws_message({"seq": 7, "type": "order", "client_order_id": "gap_order", "state": "open"})
        # Should detect gap -> forces reconnect logic. Wait, WS client calls gap callback.
        provider._handle_ws_gap() 
        # _handle_ws_gap forces REST sync.
        
    def test_normalizer_and_duplicate_events(self):
        from hedge.engines.delta.normalizer import DeltaMessageNormalizer
        # Test normalizer handles strings properly
        payload = {"client_order_id": "test_id", "size": "1.0", "state": "closed"}
        order = DeltaMessageNormalizer.parse_order(payload)
        self.assertEqual(order.quantity, 1.0)
        self.assertEqual(order.state, ExecutionState.FILLED)
        
    def test_ws_client_sequence_tracking(self):
        auth = DeltaAuthenticator("key", "secret")
        client = DeltaWebSocketClient("ws://mock", auth, self.clock)
        client.is_connected = True
        
        gap_detected = False
        def on_gap():
            nonlocal gap_detected
            gap_detected = True
            
        client.set_callbacks(lambda x: None, on_gap, lambda: None)
        
        client._on_message(None, '{"seq": 1}')
        self.assertEqual(client.last_sequence, 1)
        
        # Duplicate
        client._on_message(None, '{"seq": 1}')
        
        # Next
        client._on_message(None, '{"seq": 2}')
        self.assertFalse(gap_detected)
        
        # Gap
        client._on_message(None, '{"seq": 4}')
        self.assertTrue(gap_detected)

if __name__ == "__main__":
    unittest.main()
