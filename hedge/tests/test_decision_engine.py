import unittest
from unittest.mock import MagicMock

from hedge.engines.decision_engine import DecisionEngine
from hedge.models.decision import HedgeAction, HedgeDecision
from hedge.models.position import StressFusionBreakdown, ClusterOutput
from hedge.context.position_context import PositionContext
import config

class TestDecisionEngine(unittest.TestCase):
    def setUp(self):
        self.engine = DecisionEngine()
        self.context = PositionContext(total_lots=10, is_valid=True, futures_price=60000, short_call_strike=65000)
        
        self.breakdown = StressFusionBreakdown()
        self.breakdown.directional_cluster = ClusterOutput(score=80.0, dominant_factor="gamma_factor", primary_reason="Gamma")
        self.breakdown.volatility_cluster = ClusterOutput(score=40.0)
        self.breakdown.financial_cluster = ClusterOutput(score=20.0)
        self.breakdown.context_cluster = ClusterOutput(score=10.0)

    def test_ema_smoothing(self):
        # First eval sets EMA exactly to the incoming score
        decision1 = self.engine.evaluate(50.0, self.breakdown, self.context, 0.0)
        self.assertAlmostEqual(decision1.ema_stress, 50.0)
        
        # Second eval applies EMA alpha
        # config.DECISION_EMA_ALPHA is defaulted to 0.3
        decision2 = self.engine.evaluate(100.0, self.breakdown, self.context, 0.0)
        expected_ema = (config.DECISION_EMA_ALPHA * 100.0) + ((1.0 - config.DECISION_EMA_ALPHA) * 50.0)
        self.assertAlmostEqual(decision2.ema_stress, expected_ema)

    def test_scaling_up_transitions(self):
        # We force EMA by manipulating fused_score on the first tick (EMA initialization)
        
        # NO_ACTION
        d = self.engine.evaluate(30.0, self.breakdown, self.context, 0.0)
        self.assertEqual(d.action, HedgeAction.MONITOR)
        self.assertEqual(d.hedge_ratio, 0.0)
        
        self.engine.reset_state()
        
        # PREPARE_HEDGE
        d = self.engine.evaluate(config.HEDGE_THRESHOLD_PREPARE + 1, self.breakdown, self.context, 0.0)
        self.assertEqual(d.action, HedgeAction.PREPARE_HEDGE)
        self.assertEqual(d.hedge_ratio, 0.0)
        
        self.engine.reset_state()
        
        # PARTIAL_HEDGE
        d = self.engine.evaluate(config.HEDGE_THRESHOLD_PARTIAL + 1, self.breakdown, self.context, 0.0)
        self.assertEqual(d.action, HedgeAction.PARTIAL_HEDGE)
        self.assertEqual(d.hedge_ratio, config.PARTIAL_HEDGE_RATIO)
        
        self.engine.reset_state()
        
        # FULL_HEDGE
        d = self.engine.evaluate(config.HEDGE_THRESHOLD_FULL + 1, self.breakdown, self.context, 0.0)
        self.assertEqual(d.action, HedgeAction.FULL_HEDGE)
        self.assertEqual(d.hedge_ratio, config.FULL_HEDGE_RATIO)
        
        self.engine.reset_state()
        
        # EMERGENCY_HEDGE
        d = self.engine.evaluate(config.HEDGE_THRESHOLD_EMERGENCY + 1, self.breakdown, self.context, 0.0)
        self.assertEqual(d.action, HedgeAction.EMERGENCY_HEDGE)
        self.assertEqual(d.hedge_ratio, config.FULL_HEDGE_RATIO)

    def test_hysteresis_scaling_down(self):
        # Start fully hedged and EMA = FULL threshold + 5
        ema_start = config.HEDGE_THRESHOLD_FULL + 5.0
        self.engine.evaluate(ema_start, self.breakdown, self.context, config.FULL_HEDGE_RATIO)
        
        # Now drop EMA just slightly below FULL threshold
        # It should NOT dehedge to PARTIAL because of UNHEDGE_THRESHOLD_BUFFER
        ema_slight_drop = config.HEDGE_THRESHOLD_FULL - (config.UNHEDGE_THRESHOLD_BUFFER / 2.0)
        self.engine._ema_stress = ema_slight_drop # directly manipulate for test precision
        d = self.engine.evaluate(ema_slight_drop, self.breakdown, self.context, config.FULL_HEDGE_RATIO)
        self.assertEqual(d.action, HedgeAction.MONITOR)
        self.assertEqual(d.hedge_ratio, config.FULL_HEDGE_RATIO)
        
        # Now drop EMA below the buffer for FULL
        ema_full_drop = config.HEDGE_THRESHOLD_FULL - config.UNHEDGE_THRESHOLD_BUFFER - 1.0
        self.engine._ema_stress = ema_full_drop
        d2 = self.engine.evaluate(ema_full_drop, self.breakdown, self.context, config.FULL_HEDGE_RATIO)
        self.assertEqual(d2.action, HedgeAction.PARTIAL_HEDGE)
        self.assertEqual(d2.hedge_ratio, config.PARTIAL_HEDGE_RATIO)
        
        # Now drop EMA below PARTIAL buffer -> DEHEDGE
        ema_partial_drop = config.HEDGE_THRESHOLD_PARTIAL - config.UNHEDGE_THRESHOLD_BUFFER - 1.0
        self.engine._ema_stress = ema_partial_drop
        d3 = self.engine.evaluate(ema_partial_drop, self.breakdown, self.context, config.PARTIAL_HEDGE_RATIO)
        self.assertEqual(d3.action, HedgeAction.DEHEDGE)
        self.assertEqual(d3.hedge_ratio, 0.0)

    def test_dominant_cluster_extraction(self):
        self.breakdown.directional_cluster = ClusterOutput(score=10.0)
        self.breakdown.financial_cluster = ClusterOutput(score=99.0, dominant_factor="pnl_factor", primary_reason="Large Loss")
        
        d = self.engine.evaluate(100.0, self.breakdown, self.context, 0.0)
        self.assertEqual(d.dominant_cluster, "Financial")
        self.assertEqual(d.dominant_factor, "pnl_factor")
        self.assertEqual(d.reason, "Large Loss")

if __name__ == '__main__':
    unittest.main()
