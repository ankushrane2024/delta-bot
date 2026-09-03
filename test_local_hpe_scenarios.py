import time
import json
import os
import unittest
from local_hpe_engine import HedgeProtectionEngine
from local_hpe_indicators import HPEIndicatorEngine

class TestLocalHPE(unittest.TestCase):
    def setUp(self):
        self.state_file = "test_hpe_state_scratch.json"
        self.audit_file = "test_hpe_audit_scratch.json"
        if os.path.exists(self.state_file):
            os.remove(self.state_file)
        if os.path.exists(self.audit_file):
            os.remove(self.audit_file)
        self.engine = HedgeProtectionEngine(state_file=self.state_file, audit_file=self.audit_file)

    def tearDown(self):
        if os.path.exists(self.state_file):
            os.remove(self.state_file)
        if os.path.exists(self.audit_file):
            os.remove(self.audit_file)

    def test_rule1_lazy_monitoring_dormant(self):
        """Rule 1 & Refinement 2: Engine MUST stay DORMANT when PnL > -10%."""
        data = {
            'options_pnl_pct': -5.0,
            'options_pnl_usd': -50.0,
            'positions': [{'symbol': 'C-BTC-100000', 'pnl_pct': -5.0, 'delta': 0.3, 'size': 0.1}],
            'btc_price': 90000.0,
            'trade_active': True,
            'timestamp': time.time()
        }
        res = self.engine.process_tick(data)
        self.assertEqual(res['state'], 'DORMANT')
        self.assertEqual(res['action_state'], 'DORMANT')
        self.assertEqual(res['trigger_status'], 'IDLE')
        self.assertFalse(res['monitoring_active'])

    def test_rule1_transition_to_monitoring(self):
        """Rule 1: Engine transitions DORMANT -> MONITORING at PnL <= -10%."""
        data = {
            'options_pnl_pct': -12.0,
            'options_pnl_usd': -120.0,
            'positions': [{'symbol': 'C-BTC-100000', 'pnl_pct': -25.0, 'delta': 0.3, 'size': 0.1}],
            'btc_price': 90000.0,
            'trade_active': True,
            'timestamp': time.time()
        }
        res = self.engine.process_tick(data)
        self.assertEqual(self.engine.state, 'MONITORING')
        self.assertTrue(res['monitoring_active'])

    def test_rule5_and_refinement4_sizing_math_and_clamping(self):
        """Rule 5 & Refinement 3 & 4: Formula calculation and hard max cap clamping."""
        # Test sizing: Bleeding loss = 40%, delta = 0.3, btc_price = 90,000, max option exposure = 0.05 BTC
        qty, rem_risk, exp_move = self.engine.calculate_hedge_size(
            bleeding_loss_pct=-40.0,
            bleeding_delta=0.3,
            btc_price=90000.0,
            total_option_exposure_btc=0.05,
            leg_entry_premium_usd=100.0
        )
        self.assertEqual(rem_risk, 60.0) # 100 - 40 = 60%
        self.assertLessEqual(qty, 0.05)   # Must be clamped to total_option_exposure_btc (0.05)

    def test_refinement11_stale_data_guard(self):
        """Refinement 11: Block action if data age > 30 seconds."""
        data = {
            'options_pnl_pct': -15.0,
            'options_pnl_usd': -150.0,
            'positions': [{'symbol': 'C-BTC-100000', 'pnl_pct': -30.0, 'delta': 0.3, 'size': 0.1}],
            'btc_price': 90000.0,
            'trade_active': True,
            'timestamp': time.time() - 45  # 45 seconds old!
        }
        res = self.engine.process_tick(data)
        self.assertEqual(res['action_state'], 'STALE_DATA_HOLD')

    def test_rule8_exit1_synchronous_option_close(self):
        """Rule 8 Exit 1 & Refinement 8: Option close forces immediate hedge exit."""
        # Manually open a shadow hedge
        self.engine._open_shadow_hedge("BUY", 0.01, 90000.0)
        self.engine.state = "HEDGING"
        
        data = {
            'options_pnl_pct': 0.0,
            'options_pnl_usd': 0.0,
            'positions': [],
            'btc_price': 90000.0,
            'trade_active': False,  # Option trade closed!
            'timestamp': time.time()
        }
        res = self.engine.process_tick(data)
        self.assertFalse(self.engine.hedge_active)
        self.assertEqual(res['action_state'], 'HEDGE_CLOSED')
        self.assertIn("Option trade closed", res['exit_reason'])

    def test_rule8_exit5_hedge_sl_protection(self):
        """Rule 8 Exit 5 & Refinement 9: Hedge loss <= -10% triggers exit."""
        self.engine._open_shadow_hedge("BUY", 0.01, 90000.0)
        self.engine.state = "HEDGING"
        
        # BTC drops to 75000 (-16.6% hedge loss)
        data = {
            'options_pnl_pct': -15.0,
            'options_pnl_usd': -150.0,
            'positions': [{'symbol': 'C-BTC-100000', 'pnl_pct': -35.0, 'delta': 0.3, 'size': 0.1}],
            'btc_price': 75000.0,
            'trade_active': True,
            'timestamp': time.time()
        }
        res = self.engine.process_tick(data)
        self.assertFalse(self.engine.hedge_active)
        self.assertEqual(self.engine.state, 'COOLDOWN')
        self.assertIn("Hedge SL hit", res['exit_reason'])

    def test_rule8_exit4_trade_recovered(self):
        """Rule 8 Exit 4: Combined Option PnL recovers above -10% -> close hedge."""
        self.engine._open_shadow_hedge("SELL", 0.01, 90000.0)
        self.engine.state = "HEDGING"
        
        data = {
            'options_pnl_pct': -8.0,  # Recovered above -10%!
            'options_pnl_usd': -80.0,
            'positions': [{'symbol': 'C-BTC-100000', 'pnl_pct': -15.0, 'delta': 0.3, 'size': 0.1}],
            'btc_price': 90000.0,
            'trade_active': True,
            'timestamp': time.time()
        }
        res = self.engine.process_tick(data)
        self.assertFalse(self.engine.hedge_active)
        self.assertEqual(self.engine.state, 'DORMANT')

if __name__ == "__main__":
    unittest.main()
