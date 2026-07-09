import unittest
from unittest.mock import MagicMock
import config
from risk_manager import RiskManager

class TestDynamicProfitLock(unittest.TestCase):
    def setUp(self):
        self.api_mock = MagicMock()
        self.rm = RiskManager(self.api_mock)
        config.TRAILING_CONFIRM_THRESHOLD = 0.15
        config.TRAILING_CONFIRM_TARGET = 0.19
        config.CAPITAL_PROTECTION_SL = 0.05
        config.PROFIT_LOCK_TIERS = [(0.20, 0.12), (0.25, 0.17), (0.28, 0.23)]
        config.DYNAMIC_TRAIL_THRESHOLD = 0.28
        config.DYNAMIC_TRAIL_GAP = 0.05
        config.SL_PERCENT = 1.30

    def test_ratchet_behavior(self):
        # Initial State
        self.assertEqual(self.rm.check_sl_tp(100, 100, 0.0), None)
        self.assertEqual(self.rm.highest_profit_pct, 0.0)
        self.assertFalse(self.rm.trailing_confirmed)

        # Go to 10% profit -> Nothing happens
        self.assertEqual(self.rm.check_sl_tp(100, 90, 0.10), None)
        self.assertFalse(self.rm.confirm_started)

        # Go to 16% profit -> Confirmation starts
        self.assertEqual(self.rm.check_sl_tp(100, 84, 0.16), None)
        self.assertTrue(self.rm.confirm_started)
        self.assertFalse(self.rm.trailing_confirmed)
        self.assertIsNone(self.rm.current_trailing_sl)

        # Drop back to 10% -> Should not trigger SL, we haven't locked yet
        self.assertEqual(self.rm.check_sl_tp(100, 90, 0.10), None)

        # Go to 19.5% profit -> Trailing Confirmed and SL locked at 5%
        self.assertEqual(self.rm.check_sl_tp(100, 80.5, 0.195), None)
        self.assertTrue(self.rm.trailing_confirmed)
        self.assertEqual(self.rm.current_trailing_sl, 0.05)

        # Drop to 4% profit -> Should hit Trailing SL!
        self.assertEqual(self.rm.check_sl_tp(100, 96, 0.04), "TRAILING_SL_EXIT")

        # Go to 21% profit -> Lock tier 1 (SL = 12%)
        self.assertEqual(self.rm.check_sl_tp(100, 79, 0.21), None)
        self.assertEqual(self.rm.current_trailing_sl, 0.12)

        # Drop to 15% -> No exit
        self.assertEqual(self.rm.check_sl_tp(100, 85, 0.15), None)

        # Drop to 11% -> Exit
        self.assertEqual(self.rm.check_sl_tp(100, 89, 0.11), "TRAILING_SL_EXIT")

        # Go to 26% profit -> Lock tier 2 (SL = 17%)
        self.assertEqual(self.rm.check_sl_tp(100, 74, 0.26), None)
        self.assertEqual(self.rm.current_trailing_sl, 0.17)

        # Go to 29% profit -> Lock tier 3 and Dynamic trailing! (SL = 29 - 5 = 24%)
        self.assertEqual(self.rm.check_sl_tp(100, 71, 0.29), None)
        self.assertEqual(self.rm.current_trailing_sl, 0.24)

        # Go to 40% profit -> SL = 35%
        self.assertEqual(self.rm.check_sl_tp(100, 60, 0.40), None)
        self.assertEqual(self.rm.current_trailing_sl, 0.35)
        
        # Go to 50% profit -> SL = 45% (Notice how it blows past the old 30% TP)
        self.assertEqual(self.rm.check_sl_tp(100, 50, 0.50), None)
        self.assertEqual(self.rm.current_trailing_sl, 0.45)

        # Drop to 48% -> Nothing
        self.assertEqual(self.rm.check_sl_tp(100, 52, 0.48), None)
        self.assertEqual(self.rm.current_trailing_sl, 0.45) # Ratchet does not go down

        # Drop to 44% -> Exit
        self.assertEqual(self.rm.check_sl_tp(100, 56, 0.44), "TRAILING_SL_EXIT")
        
        # Test hard downside SL (-130%)
        self.rm.reset_trailing_state()
        self.assertEqual(self.rm.check_sl_tp(100, 230, -1.30), "STOP_LOSS_ALL")

if __name__ == '__main__':
    unittest.main()
