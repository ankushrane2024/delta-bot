import uuid
import time
import math
import logging
from typing import Dict, Any, List
from datetime import datetime, timezone

from hedge.engines.base_engine import AbstractBaseEngine
from hedge.models.regime import MarketRegimeResult
from hedge.models.trend import TrendResult
from hedge.context.position_context import PositionContext
from hedge.models.position import PositionRiskResult, CallStressBreakdown
from hedge.models.shared import AnalyzerHealth

logger = logging.getLogger("ARES.PositionRiskEngine")

class PositionRiskEngine(AbstractBaseEngine):
    def __init__(self, replay_mode: bool = False):
        self.replay_mode = replay_mode
        self._warnings: List[str] = []
        self._last_execution_time = 0.0

    def initialize(self) -> None:
        logger.info("Initialized PositionRiskEngine.")
        self.reset()

    def evaluate(self, regime_result: MarketRegimeResult, trend_result: TrendResult, position_context: PositionContext) -> PositionRiskResult:
        started_at = time.time()
        evaluation_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        self._warnings.clear()
        
        # 1. Validate Context
        if not position_context.is_valid:
            msg = "PositionContext flagged as invalid. Risk metrics may be compromised."
            self._warnings.append(msg)
            logger.warning(msg)
            
        # 2. Risk Computation Pipeline
        delta_exposure = self._compute_delta_risk(position_context)
        gamma_exposure = self._compute_gamma_risk(position_context)
        theta_exposure = self._compute_theta_risk(position_context)
        vega_exposure = self._compute_vega_risk(position_context)
        
        call_side_risk = self._compute_call_risk(position_context, regime_result, trend_result)
        put_side_risk = self._compute_put_risk(position_context, regime_result, trend_result)
        
        stop_proximity = self._compute_stop_proximity(position_context)
        portfolio_heat = self._compute_portfolio_heat(position_context)
        hedge_urgency = self._compute_hedge_urgency(position_context, regime_result, trend_result)
        
        # 3. Stress Computation Framework
        call_stress_breakdown = self._compute_call_stress_breakdown(trend_result, regime_result, position_context)
        call_stress = self._compute_call_stress(call_stress_breakdown)
        
        overall_risk_score = self._compute_overall_risk(call_side_risk, put_side_risk, portfolio_heat, hedge_urgency)
        confidence = self._compute_confidence(position_context)
        
        completed_at = time.time()
        execution_time_ms = (completed_at - started_at) * 1000.0
        self._last_execution_time = execution_time_ms
        
        result = PositionRiskResult(
            evaluation_id=evaluation_id,
            overall_risk_score=overall_risk_score,
            call_side_risk=call_side_risk,
            put_side_risk=put_side_risk,
            delta_exposure=delta_exposure,
            gamma_exposure=gamma_exposure,
            theta_exposure=theta_exposure,
            vega_exposure=vega_exposure,
            stop_loss_proximity=stop_proximity,
            portfolio_heat=portfolio_heat,
            hedge_urgency=hedge_urgency,
            call_stress=call_stress,
            put_stress=0.0,
            portfolio_stress=0.0,
            stress_velocity=0.0,
            recovery_probability=0.0,
            hedge_efficiency_estimate=0.0,
            confidence=confidence,
            timestamp=timestamp,
            started_at=started_at,
            completed_at=completed_at,
            execution_time_ms=execution_time_ms,
            explanation="Position risk assessed successfully.",
            debug_information={"warnings": list(self._warnings), "total_lots": position_context.total_lots}
        )
        
        logger.debug(f"PositionRiskEngine evaluated in {execution_time_ms:.2f}ms. ID: {evaluation_id}")
        return result

    # --- Placeholder Computation Methods ---
    
    def _compute_delta_risk(self, ctx: PositionContext) -> float:
        return 0.0

    def _compute_gamma_risk(self, ctx: PositionContext) -> float:
        return 0.0
        
    def _compute_theta_risk(self, ctx: PositionContext) -> float:
        return 0.0
        
    def _compute_vega_risk(self, ctx: PositionContext) -> float:
        return 0.0

    def _compute_call_risk(self, ctx: PositionContext, regime: MarketRegimeResult, trend: TrendResult) -> float:
        return 0.0

    def _compute_put_risk(self, ctx: PositionContext, regime: MarketRegimeResult, trend: TrendResult) -> float:
        return 0.0

    def _compute_stop_proximity(self, ctx: PositionContext) -> float:
        return 0.0

    def _compute_portfolio_heat(self, ctx: PositionContext) -> float:
        return 0.0

    def _compute_hedge_urgency(self, ctx: PositionContext, regime: MarketRegimeResult, trend: TrendResult) -> float:
        return 0.0

    def _compute_strike_distance_factor(self, futures_price: float, short_call_strike: float) -> float:
        if not futures_price or futures_price <= 0.0 or not short_call_strike or short_call_strike <= 0.0:
            msg = f"Invalid inputs for strike_distance_factor: futures_price={futures_price}, strike={short_call_strike}"
            self._warnings.append(msg)
            logger.warning(msg)
            return 0.0
            
        # x is the percentage distance. Positive means breached, negative means safe.
        x = (futures_price - short_call_strike) / short_call_strike
        
        # Sigmoid function centered such that 3% OTM gives 50% stress
        center_offset = 0.03
        steepness = 100.0
        
        try:
            # Prevent math overflow for extreme values
            exponent = -steepness * (x + center_offset)
            if exponent > 50:
                return 0.0
            if exponent < -50:
                return 100.0
                
            score = 100.0 / (1.0 + math.exp(exponent))
            return max(0.0, min(100.0, score))
        except OverflowError:
            if x < -center_offset:
                return 0.0
            return 100.0
            
    def _compute_delta_factor(self, call_delta: float) -> float:
        try:
            if call_delta is None or math.isnan(call_delta) or math.isinf(call_delta):
                msg = f"Invalid inputs for delta_factor: call_delta={call_delta}"
                self._warnings.append(msg)
                logger.warning(msg)
                return 0.0
                
            abs_delta = abs(float(call_delta))
            
            # Clamp delta between 0.0 and 1.0
            abs_delta = max(0.0, min(1.0, abs_delta))
            
            # Normalized Sigmoid to model short-option directional risk:
            # - Very small delta stays near 0
            # - Accelerates aggressively around 0.4 - 0.6
            # - Rapidly approaches 100 as delta gets high
            from config import DELTA_SIGMOID_STEEPNESS, DELTA_SIGMOID_CENTER
            steepness = DELTA_SIGMOID_STEEPNESS
            midpoint = DELTA_SIGMOID_CENTER
            
            def sigmoid(x: float) -> float:
                return 1.0 / (1.0 + math.exp(-steepness * (x - midpoint)))
                
            min_val = sigmoid(0.0)
            max_val = sigmoid(1.0)
            
            raw_score = sigmoid(abs_delta)
            
            # Normalize to strictly 0-100 range
            score = 100.0 * (raw_score - min_val) / (max_val - min_val)
            
            return max(0.0, min(100.0, score))
        except Exception as e:
            msg = f"Exception in _compute_delta_factor: {str(e)}"
            self._warnings.append(msg)
            logger.warning(msg)
            return 0.0

    def _compute_gamma_factor(self, call_gamma: float) -> float:
        try:
            if call_gamma is None or math.isnan(call_gamma) or math.isinf(call_gamma):
                msg = f"Invalid inputs for gamma_factor: call_gamma={call_gamma}"
                self._warnings.append(msg)
                logger.warning(msg)
                return 0.0
                
            abs_gamma = abs(float(call_gamma))
            
            # Gamma is dormant when far OTM, and spikes aggressively towards infinity near expiration (Pin Risk).
            # The Inverse Exponential Decay (Arrhenius curve) naturally maps [0, infinity) -> [0, 100].
            if abs_gamma < 1e-9:
                return 0.0
                
            from config import GAMMA_SENSITIVITY_K
            k = GAMMA_SENSITIVITY_K
            
            # Score = 100 * e^(-k / gamma)
            exponent = -k / abs_gamma
            
            # Prevent underflow/overflow
            if exponent < -50:
                return 0.0
            
            score = 100.0 * math.exp(exponent)
            return max(0.0, min(100.0, score))
            
        except Exception as e:
            msg = f"Exception in _compute_gamma_factor: {str(e)}"
            self._warnings.append(msg)
            logger.warning(msg)
            return 0.0

    def _compute_vega_factor(self, call_vega: float) -> float:
        try:
            if call_vega is None or math.isnan(call_vega) or math.isinf(call_vega):
                msg = f"Invalid inputs for vega_factor: call_vega={call_vega}"
                self._warnings.append(msg)
                logger.warning(msg)
                return 0.0
                
            abs_vega = abs(float(call_vega))
            
            # Vega represents pure exposure to IV expansion.
            # We use a Squared Exponential Asymptote (Rayleigh CDF form): 100 * (1 - exp(-k * (vega/ref)^2))
            # This ensures zero stress at zero vega, flat initial growth, rapid acceleration midway, 
            # and a natural asymptotic ceiling at 100 without arbitrary clipping.
            from config import VEGA_REFERENCE
            v_ref = VEGA_REFERENCE
            
            if v_ref <= 0:
                v_ref = 10.0 # safe fallback
                
            # k = ln(2) ≈ 0.693147, so that when vega == v_ref, score is exactly 50.0
            k = 0.69314718056
            ratio = abs_vega / v_ref
            
            exponent = -k * (ratio ** 2)
            
            # Prevent extreme underflow
            if exponent < -50:
                return 100.0
                
            score = 100.0 * (1.0 - math.exp(exponent))
            return max(0.0, min(100.0, score))
            
        except Exception as e:
            msg = f"Exception in _compute_vega_factor: {str(e)}"
            self._warnings.append(msg)
            logger.warning(msg)
            return 0.0

    def _compute_premium_growth_factor(self, current_premium: float, entry_premium: float) -> float:
        try:
            if current_premium is None or math.isnan(current_premium) or math.isinf(current_premium):
                return 0.0
            if entry_premium is None or math.isnan(entry_premium) or math.isinf(entry_premium) or entry_premium <= 0:
                return 0.0
                
            # Growth ratio = max(0, (current / entry) - 1.0)
            growth = max(0.0, (float(current_premium) / float(entry_premium)) - 1.0)
            
            if growth < 1e-9:
                return 0.0
                
            from config import PREMIUM_GROWTH_REFERENCE_K, PREMIUM_GROWTH_STEEPNESS_N
            k = float(PREMIUM_GROWTH_REFERENCE_K)
            n = float(PREMIUM_GROWTH_STEEPNESS_N)
            
            if k <= 0:
                k = 1.0 # Safe fallback
                
            # Hill Equation (Dose-Response Curve)
            # Score = 100 * (growth^n) / (k^n + growth^n)
            # Perfectly flat at zero, highly configurable acceleration, strictly bounded to 100.
            growth_pow = math.pow(growth, n)
            k_pow = math.pow(k, n)
            
            score = 100.0 * (growth_pow / (k_pow + growth_pow))
            return max(0.0, min(100.0, score))
            
        except Exception as e:
            msg = f"Exception in _compute_premium_growth_factor: {str(e)}"
            self._warnings.append(msg)
            logger.warning(msg)
            return 0.0
            
    def _compute_iv_expansion_factor(self, current_iv: float, entry_iv: float) -> float:
        try:
            if current_iv is None or math.isnan(current_iv) or math.isinf(current_iv):
                return 0.0
            if entry_iv is None or math.isnan(entry_iv) or math.isinf(entry_iv) or entry_iv <= 0:
                return 0.0
                
            # Expansion ratio = max(0, (current / entry) - 1.0)
            expansion = max(0.0, (float(current_iv) / float(entry_iv)) - 1.0)
            
            if expansion < 1e-9:
                return 0.0
                
            from config import IV_EXPANSION_REFERENCE, IV_EXPANSION_SHAPE_N
            ref = float(IV_EXPANSION_REFERENCE)
            n = float(IV_EXPANSION_SHAPE_N)
            
            if ref <= 0:
                ref = 1.0 # Safe fallback
                
            # Weibull CDF (Cubed Exponential Asymptote)
            # Score = 100 * (1 - exp(-k * (expansion/ref)^n))
            # Perfectly flat near zero (ignores ordinary IV fluctuations), accelerates violently during shock.
            k = 0.69314718056 # ln(2) so that score=50 when expansion==ref
            ratio = expansion / ref
            exponent = -k * math.pow(ratio, n)
            
            if exponent < -50:
                return 100.0
                
            score = 100.0 * (1.0 - math.exp(exponent))
            return max(0.0, min(100.0, score))
            
        except Exception as e:
            msg = f"Exception in _compute_iv_expansion_factor: {str(e)}"
            self._warnings.append(msg)
            logger.warning(msg)
            return 0.0

    def _compute_call_stress_breakdown(self, trend: TrendResult, regime: MarketRegimeResult, ctx: PositionContext) -> CallStressBreakdown:
        strike_dist_factor = self._compute_strike_distance_factor(ctx.futures_price, ctx.short_call_strike)
        delta_factor = self._compute_delta_factor(ctx.call_delta)
        gamma_factor = self._compute_gamma_factor(ctx.call_gamma)
        vega_factor = self._compute_vega_factor(ctx.call_vega)
        
        # Deduce entry premium
        entry_premium = ctx.metadata.get('call_entry_price', None)
        if entry_premium is None:
            from config import LOT_TO_BTC
            lots_per_leg = max(1, ctx.total_lots / 2.0)
            if LOT_TO_BTC > 0 and lots_per_leg > 0:
                entry_premium = ctx.call_mark_price + (ctx.call_leg_pnl / (lots_per_leg * LOT_TO_BTC))
            else:
                entry_premium = ctx.call_mark_price
                
        premium_growth_factor = self._compute_premium_growth_factor(ctx.call_mark_price, entry_premium)
        
        # Get entry IV
        entry_iv = ctx.metadata.get('call_entry_iv', None)
        if entry_iv is None:
            entry_iv = ctx.call_iv # fallback to current IV (no expansion)
            
        iv_expansion_factor = self._compute_iv_expansion_factor(ctx.call_iv, entry_iv)
        
        return CallStressBreakdown(
            strike_distance_factor=strike_dist_factor,
            delta_factor=delta_factor,
            gamma_factor=gamma_factor,
            vega_factor=vega_factor,
            premium_growth_factor=premium_growth_factor,
            trend_factor=0.0,
            regime_factor=0.0,
            iv_factor=0.0, # Kept for backward compatibility if needed, but not populated actively with vega anymore
            iv_expansion_factor=iv_expansion_factor,
            pnl_factor=0.0,
            final_call_stress=0.0,
            explanation="Call stress components evaluated. Strike distance, delta, gamma, vega, premium growth, and IV expansion factors implemented."
        )

    def _compute_call_stress(self, breakdown: CallStressBreakdown) -> float:
        return breakdown.final_call_stress

    def _compute_overall_risk(self, call_risk: float, put_risk: float, heat: float, urgency: float) -> float:
        return 0.0
        
    def _compute_confidence(self, ctx: PositionContext) -> float:
        if not ctx.is_valid:
            return 0.0
        return 100.0

    # ---------------------------------------

    def reset(self) -> None:
        self._warnings.clear()
        self._last_execution_time = 0.0

    def health(self) -> AnalyzerHealth:
        return AnalyzerHealth(
            loaded_evaluators=1,
            failed_evaluators=0,
            warnings=list(self._warnings),
            replay_mode=self.replay_mode,
            last_execution_time=self._last_execution_time
        )
        
    def metadata(self) -> Dict[str, Any]:
        return {
            "name": "PositionRiskEngine"
        }
