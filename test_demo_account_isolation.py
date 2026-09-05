"""
Comprehensive Test Suite: Demo Mode Account Isolation & Live Protection
Verifies that:
1. Orders NEVER execute on Live account (api.india.delta.exchange) when Demo API is active.
2. Orders execute ONLY on Demo testnet when Demo API is active.
3. Live toggle cannot be activated while in Demo API slot.
4. Active positions between Live, Demo, and Paper are strictly isolated.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db_manager
import config
from api_client import DeltaIndiaClient
from execution import ExecutionHandler

class TestDemoAccountIsolation(unittest.TestCase):

    def setUp(self):
        # Record initial state
        self.initial_slot = db_manager.get_active_api_slot()

    def tearDown(self):
        # Restore initial state
        db_manager.set_active_api_slot(self.initial_slot)

    def test_demo_gateway_guard_passes_for_testnet(self):
        """Verify _verify_execution_gateway passes when in demo slot and testnet URL."""
        db_manager.set_active_api_slot('demo')
        client = DeltaIndiaClient(base_url="https://cdn-ind.testnet.deltaex.org")
        handler = ExecutionHandler(client, mode='DEMO')
        env = handler._verify_execution_gateway()
        self.assertEqual(env, 'DEMO')

    def test_demo_gateway_guard_blocks_live_url(self):
        """Verify _verify_execution_gateway raises RuntimeError if gateway is live while demo slot is active."""
        db_manager.set_active_api_slot('demo')
        live_client = DeltaIndiaClient(base_url="https://api.india.delta.exchange")
        handler = ExecutionHandler(live_client, mode='DEMO')
        with self.assertRaises(RuntimeError) as ctx:
            handler._verify_execution_gateway()
        self.assertIn("Account Isolation Guard", str(ctx.exception))
        print("  [PASS] Successfully blocked trade on LIVE gateway while in DEMO mode!")

    def test_network_level_interceptor_blocks_live_requests(self):
        """Verify DeltaIndiaClient.request blocks any HTTP call to Live gateway when in demo slot."""
        db_manager.set_active_api_slot('demo')
        client = DeltaIndiaClient(base_url="https://api.india.delta.exchange")
        client.api_key = "test_key"
        client.api_secret = "test_secret"
        res = client.request("POST", "/v2/orders", data={"product_id": 84, "size": 1, "side": "buy"})
        self.assertFalse(res.get('success'))
        self.assertEqual(res.get('error', {}).get('code'), 'account_isolation_guard_tripped')
        print("  [PASS] Network interceptor aborted live order before sending bytes!")

    def test_toggle_live_blocked_in_demo_slot(self):
        """Verify that web_server /api/toggle_live_mode rejects activation when active slot is demo."""
        db_manager.set_active_api_slot('demo')
        from web_server import app, init_web_server
        from unittest.mock import MagicMock
        mock_engine = MagicMock()
        mock_engine.execution = ExecutionHandler(None, mode='DEMO')
        init_web_server(mock_engine)
        
        with app.test_client() as c:
            resp = c.post('/api/toggle_live_mode', json={'activate': True})
            self.assertEqual(resp.status_code, 400)
            data = resp.get_json()
            self.assertFalse(data.get('success'))
            self.assertIn("Cannot activate LIVE mode while DEMO API slot is active", data.get('error'))
            print("  [PASS] Live mode toggle activation rejected with 400 while DEMO slot active!")

    def test_position_isolation(self):
        """Verify Demo, Live, and Paper positions stores are strictly separated."""
        client = DeltaIndiaClient(base_url="https://cdn-ind.testnet.deltaex.org")
        
        # Test Live
        h_live = ExecutionHandler(client, mode='LIVE')
        h_live.active_positions = {"C-BTC-LIVE": {"size": 1, "side": "SELL"}}
        
        # Test Demo
        h_demo = ExecutionHandler(client, mode='DEMO')
        h_demo.active_positions = {"C-BTC-DEMO": {"size": 1, "side": "SELL"}}
        
        # Test Paper
        h_paper = ExecutionHandler(client, mode='PAPER')
        h_paper.active_positions = {"C-BTC-PAPER": {"size": 1, "side": "SELL"}}

        # Verify no cross-contamination
        self.assertIn("C-BTC-LIVE", h_live.live_active_positions)
        self.assertNotIn("C-BTC-LIVE", h_demo.demo_active_positions)
        self.assertNotIn("C-BTC-LIVE", h_paper.paper_active_positions)

        self.assertIn("C-BTC-DEMO", h_demo.demo_active_positions)
        self.assertNotIn("C-BTC-DEMO", h_live.live_active_positions)
        self.assertNotIn("C-BTC-DEMO", h_paper.paper_active_positions)
        
        print("  [PASS] 100% position isolation confirmed between LIVE, DEMO, and PAPER!")

if __name__ == '__main__':
    print("=" * 60)
    print("RUNNING DEMO MODE ACCOUNT ISOLATION TEST SUITE")
    print("=" * 60)
    unittest.main()
