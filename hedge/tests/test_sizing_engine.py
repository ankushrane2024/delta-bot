import unittest
from unittest.mock import patch

from hedge.engines.sizing_engine import HedgeSizingEngine
from hedge.models.decision import HedgeDecision, HedgeAction
from hedge.context.position_context import PositionContext
import config

class TestSizingEngine(unittest.TestCase):
    def setUp(self):
        self.engine = HedgeSizingEngine()
        self.context = PositionContext(
            total_lots=10, 
            is_valid=True, 
            futures_price=60000.0,
            call_delta=0.3,
            put_delta=-0.1
        )
        # lot_to_btc is 0.001
        # lots_per_leg = 5
        # call_delta = 0.3, put_delta = -0.1
        # Net Options Delta BTC = -1.0 * (0.3 - 0.1) * 5 * 0.001 = -1.0 * 0.2 * 0.005 = -0.001 BTC
        
        self.decision_full = HedgeDecision(
            action=HedgeAction.FULL_HEDGE,
            urgency=1.0,
            hedge_ratio=1.0,
            reason="Large Loss",
            dominant_cluster="Financial",
            dominant_factor="pnl_factor"
        )
        
        self.decision_partial = HedgeDecision(
            action=HedgeAction.PARTIAL_HEDGE,
            urgency=0.5,
            hedge_ratio=0.5,
            reason="Gamma",
            dominant_cluster="Directional",
            dominant_factor="gamma_factor"
        )
        
        self.decision_dehedge = HedgeDecision(
            action=HedgeAction.DEHEDGE,
            urgency=0.0,
            hedge_ratio=0.0,
            reason="Recovered",
            dominant_cluster="None",
            dominant_factor="None"
        )

    def test_full_hedge_zero_existing(self):
        # Target hedge = +0.001 BTC. Contract size = 0.001 BTC. 
        # So we need 1 contract.
        res = self.engine.evaluate(self.decision_full, self.context, current_hedge_qty=0.0)
        
        self.assertAlmostEqual(res.current_delta, -0.001)
        self.assertAlmostEqual(res.target_delta, 0.001)
        self.assertAlmostEqual(res.delta_to_hedge, 0.001)
        self.assertEqual(res.hedge_side, "BUY")
        self.assertAlmostEqual(res.additional_quantity, 1.0)
        self.assertAlmostEqual(res.hedge_quantity, 1.0)

    def test_partial_hedge_zero_existing(self):
        # Target hedge = +0.0005 BTC. Contract size = 0.001 BTC.
        # Required contracts = 0.5. With step size 1.0, 0.5 rounds to 0.0 (or 1.0 depending on round).
        # Python's round(0.5) is 0 (rounds to even).
        res = self.engine.evaluate(self.decision_partial, self.context, current_hedge_qty=0.0)
        
        self.assertAlmostEqual(res.target_delta, 0.0005)
        self.assertEqual(res.hedge_side, "NONE") # Because it rounded to 0
        self.assertAlmostEqual(res.additional_quantity, 0.0)

    def test_partial_hedge_rounded_up(self):
        # Let's make it 3 contracts needed for full -> 1.5 for partial -> round to 2
        self.context.call_delta = 0.7
        # Sum = 0.6. -1 * 0.6 * 5 * 0.001 = -0.003 BTC.
        # Target for partial (0.5 ratio) = +0.0015 BTC -> 1.5 contracts -> rounds to 2.
        res = self.engine.evaluate(self.decision_partial, self.context, current_hedge_qty=0.0)
        self.assertEqual(res.hedge_side, "BUY")
        self.assertAlmostEqual(res.additional_quantity, 2.0)

    def test_existing_hedge_adjustment(self):
        # Target hedge = +0.001 BTC (1 contract). We already have 3 contracts.
        # So we need to sell 2 contracts.
        res = self.engine.evaluate(self.decision_full, self.context, current_hedge_qty=3.0)
        
        self.assertAlmostEqual(res.current_delta, -0.001)
        self.assertAlmostEqual(res.target_delta, 0.001)
        # Current hedge delta = 0.003 BTC
        # delta to hedge = 0.001 - 0.003 = -0.002 BTC
        self.assertAlmostEqual(res.delta_to_hedge, -0.002)
        
        self.assertEqual(res.hedge_side, "SELL")
        self.assertAlmostEqual(res.additional_quantity, 2.0)
        self.assertAlmostEqual(res.hedge_quantity, 1.0) # 3 - 2 = 1

    def test_dehedge(self):
        # We want to dehedge entirely. We have 5 contracts.
        res = self.engine.evaluate(self.decision_dehedge, self.context, current_hedge_qty=5.0)
        
        self.assertEqual(res.target_delta, 0.0)
        self.assertAlmostEqual(res.delta_to_hedge, -0.005) # 5 contracts * 0.001 = 0.005
        self.assertEqual(res.hedge_side, "SELL")
        self.assertAlmostEqual(res.additional_quantity, 5.0)
        self.assertAlmostEqual(res.hedge_quantity, 0.0)

    def test_invalid_delta(self):
        self.context.call_delta = float('nan')
        res = self.engine.evaluate(self.decision_full, self.context, current_hedge_qty=0.0)
        # With call_delta NaN, it falls back to 0.0
        # Net delta = -1 * (0 + -0.1) * 5 * 0.001 = 0.0005 BTC.
        self.assertAlmostEqual(res.current_delta, 0.0005)

    def test_over_max_quantity(self):
        # Set a massive delta
        self.context.total_lots = 10000000
        # Required contracts will exceed MAX_ORDER_QTY
        res = self.engine.evaluate(self.decision_full, self.context, current_hedge_qty=0.0)
        self.assertEqual(res.additional_quantity, config.MAX_ORDER_QTY)
        self.assertIn("MAX_ORDER_QTY", res.warnings[0])

if __name__ == '__main__':
    unittest.main()
