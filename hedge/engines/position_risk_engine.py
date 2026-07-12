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
        call_stress_breakdown = self._compute_leg_stress_breakdown(trend_result, regime_result, position_context, is_call=True)
        call_stress = self._compute_leg_stress(call_stress_breakdown)
        
        put_stress_breakdown = self._compute_leg_stress_breakdown(trend_result, regime_result, position_context, is_call=False)
        put_stress = self._compute_leg_stress(put_stress_breakdown)
        
        overall_risk_score = max(call_stress, put_stress)
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
            put_stress=put_stress,
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
            debug_information={
                "warnings": list(self._warnings), 
                "total_lots": position_context.total_lots,
                "call_stress_breakdown": call_stress_breakdown,
                "put_stress_breakdown": put_stress_breakdown
            }
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

    def _compute_trend_factor(self, trend: TrendResult, is_call: bool = True) -> float:
        try:
            if trend is None:
                return 0.0
                
            from hedge.models.enums import TrendDirection
            
            # 1. Check Directional Threat
            # A BULLISH (LONG) trend threatens a Short Call.
            # A BEARISH (SHORT) trend threatens a Short Put.
            dangerous_direction = TrendDirection.LONG if is_call else TrendDirection.SHORT
            
            if trend.trend_direction != dangerous_direction:
                # Trend is either neutral or moving away from the short strike (safe)
                return 0.0
                
            strength = trend.trend_strength
            if strength is None or math.isnan(strength) or math.isinf(strength):
                return 0.0
                
            confidence = getattr(trend, 'trend_confidence', 0.0)
            if confidence is None or math.isnan(confidence):
                confidence = 0.0
                
            continuation = getattr(trend, 'continuation_probability', 0.0)
            if continuation is None or math.isnan(continuation):
                continuation = 0.0
                
            # Clamp inputs
            strength = max(0.0, min(100.0, float(strength)))
            confidence = max(0.0, min(100.0, float(confidence)))
            continuation = max(0.0, min(100.0, float(continuation)))
            
            # 2. Normalized Sigmoid for Trend Strength
            from config import TREND_SIGMOID_CENTER, TREND_SIGMOID_STEEPNESS
            midpoint = float(TREND_SIGMOID_CENTER)
            steepness = float(TREND_SIGMOID_STEEPNESS)
            
            def sigmoid(x: float) -> float:
                return 1.0 / (1.0 + math.exp(-steepness * (x - midpoint)))
                
            min_val = sigmoid(0.0)
            max_val = sigmoid(100.0)
            raw_score = sigmoid(strength)
            
            # Normalize strength to 0-100 range
            normalized_strength = 100.0 * (raw_score - min_val) / (max_val - min_val)
            
            # 3. Dampen score based on confidence and continuation
            # A strong trend with low confidence/continuation is less stressful.
            dampener = (confidence + continuation) / 200.0
            
            score = normalized_strength * dampener
            return max(0.0, min(100.0, score))
            
        except Exception as e:
            msg = f"Exception in _compute_trend_factor: {str(e)}"
            self._warnings.append(msg)
            logger.warning(msg)
            return 0.0

    def _compute_regime_factor(self, regime: MarketRegimeResult) -> float:
        try:
            if regime is None:
                return 0.0
                
            from hedge.models.enums import MarketRegime
            import config
            
            # Map MarketRegime to statically configured base scores
            base_score_map = {
                MarketRegime.SAFE_RANGE: getattr(config, 'REGIME_BASE_SCORE_SAFE_RANGE', 0.0),
                MarketRegime.WEAK_RANGE: getattr(config, 'REGIME_BASE_SCORE_WEAK_RANGE', 10.0),
                MarketRegime.TRANSITION: getattr(config, 'REGIME_BASE_SCORE_TRANSITION', 30.0),
                MarketRegime.EARLY_TREND: getattr(config, 'REGIME_BASE_SCORE_EARLY_TREND', 60.0),
                MarketRegime.CONFIRMED_TREND: getattr(config, 'REGIME_BASE_SCORE_CONFIRMED_TREND', 85.0),
                MarketRegime.ACCELERATION: getattr(config, 'REGIME_BASE_SCORE_ACCELERATION', 100.0),
                MarketRegime.TREND_EXHAUSTION: getattr(config, 'REGIME_BASE_SCORE_TREND_EXHAUSTION', 40.0),
            }
            
            current_regime = getattr(regime, 'current_regime', None)
            
            if current_regime not in base_score_map:
                return 0.0
                
            base_score = float(base_score_map[current_regime])
            
            # Dampen score by regime confidence
            confidence = getattr(regime, 'confidence', 0.0)
            if confidence is None or math.isnan(confidence):
                confidence = 0.0
                
            # Clamp confidence
            confidence = max(0.0, min(100.0, float(confidence)))
            
            score = base_score * (confidence / 100.0)
            return max(0.0, min(100.0, score))
            
        except Exception as e:
            msg = f"Exception in _compute_regime_factor: {str(e)}"
            self._warnings.append(msg)
            logger.warning(msg)
            return 0.0

    def _compute_time_to_expiry_factor(self, ctx: PositionContext) -> float:
        try:
            # Time to expiry logic
            seconds = ctx.metadata.get('seconds_to_expiry')
            if seconds is None:
                seconds = ctx.metadata.get('time_to_expiry_seconds')
            
            if seconds is None:
                expiry_ts = ctx.metadata.get('expiry_timestamp')
                if expiry_ts:
                    seconds = float(expiry_ts) - time.time()
                    
            if seconds is None or math.isnan(seconds) or math.isinf(seconds):
                return 0.0
                
            seconds = float(seconds)
            if seconds <= 0.0:
                # Option is expired or expiring precisely now, max stress
                return 100.0
                
            # Convert to days
            days_to_expiry = seconds / 86400.0
            
            from config import TIME_EXPIRY_REFERENCE_DAYS
            k = float(TIME_EXPIRY_REFERENCE_DAYS)
            if k <= 0:
                k = 10.0 # safe fallback
                
            # Standard Exponential Decay (Survival Analysis)
            # Score = 100 * exp(-t / k)
            exponent = -days_to_expiry / k
            
            if exponent < -50:
                return 0.0 # Effectively zero for very large time
                
            score = 100.0 * math.exp(exponent)
            return max(0.0, min(100.0, score))
            
        except Exception as e:
            msg = f"Exception in _compute_time_to_expiry_factor: {str(e)}"
            self._warnings.append(msg)
            logger.warning(msg)
            return 0.0

    def _compute_pnl_factor(self, ctx: PositionContext, is_call: bool = True) -> float:
        try:
            # Get the PnL of the specific leg being evaluated
            call_pnl = getattr(ctx, 'call_leg_pnl', 0.0)
            put_pnl = getattr(ctx, 'put_leg_pnl', 0.0)
            
            # Prevent NoneTypes
            if call_pnl is None or math.isnan(call_pnl) or math.isinf(call_pnl): call_pnl = 0.0
            if put_pnl is None or math.isnan(put_pnl) or math.isinf(put_pnl): put_pnl = 0.0
            
            leg_pnl = float(call_pnl) if is_call else float(put_pnl)
            combined_pnl = float(call_pnl) + float(put_pnl)
            
            # Positive P&L (profit) on the bleeding leg generates 0 stress
            if leg_pnl >= 0.0:
                return 0.0
                
            # Convert to a positive absolute loss for math
            loss = abs(leg_pnl)
            
            from config import PNL_STRESS_REFERENCE_LOSS
            ref_loss = float(PNL_STRESS_REFERENCE_LOSS)
            if ref_loss <= 0.0:
                ref_loss = 500.0 # Safe fallback
                
            # Rayleigh CDF (Squared Exponential Asymptote)
            # Score = 100 * (1 - exp(-k * (Loss/Ref)^2))
            k = 0.69314718056
            ratio = loss / ref_loss
            
            exponent = -k * (ratio ** 2)
            
            if exponent < -50:
                base_score = 100.0 # Prevent underflow
            else:
                base_score = 100.0 * (1.0 - math.exp(exponent))
                
            # NEW LOGIC: Combined PnL Awareness
            if combined_pnl > 0:
                # Trade is net profitable overall. Bleeding leg is NOT ignored,
                # but ARES stress is halved because the winning leg provides a cushion.
                final_score = base_score * 0.5
            else:
                # Trade is net losing. Treat bleeding leg with full severity.
                final_score = base_score
                
            return float(min(max(final_score, 0.0), 100.0))

        except Exception as e:
            msg = f"Exception in _compute_pnl_factor: {str(e)}"
            self._warnings.append(msg)
            logger.warning(msg)
            return 0.0

    def _compute_cluster_softmax_ev(self, inputs: Dict[str, float], base_weights: Dict[str, float], k: float) -> 'ClusterOutput':
        from hedge.models.position import ClusterOutput
        
        if not inputs:
            return ClusterOutput()
            
        total_weight = 0.0
        weighted_sum = 0.0
        max_val = -1.0
        dominant_factor = ""
        
        for name, val in inputs.items():
            base = base_weights.get(name, 1.0)
            weight = base * math.exp(k * val)
            total_weight += weight
            weighted_sum += weight * val
            
            if val > max_val:
                max_val = val
                dominant_factor = name
                
        score = weighted_sum / total_weight if total_weight > 0 else 0.0
        score = max(0.0, min(100.0, score))
        
        reason_map = {
            "strike_distance_factor": "Strike Proximity",
            "delta_factor": "Directional Threat",
            "gamma_factor": "Gamma Explosion",
            "vega_factor": "Volatility Sensitivity",
            "iv_expansion_factor": "IV Expansion",
            "premium_growth_factor": "Premium Expansion",
            "pnl_factor": "Large Unrealized Loss",
            "trend_factor": "Adverse Trend",
            "regime_factor": "Hostile Regime"
        }
        
        return ClusterOutput(
            score=score,
            confidence=100.0, # Handled by upstream evaluators
            primary_reason=reason_map.get(dominant_factor, dominant_factor),
            dominant_factor=dominant_factor,
            raw_inputs=inputs
        )

    def _apply_confidence_dampening(self, score: float, confidence: float, power: float) -> float:
        c = max(0.0, min(100.0, confidence)) / 100.0
        s = max(0.0, min(100.0, score)) / 100.0
        multiplier = c + (1.0 - c) * math.pow(s, power)
        return score * multiplier

    def _compute_mathematical_fusion(self, breakdown: 'StressFusionBreakdown', combined_pnl: float = 0.0) -> float:
        from config import CONFIDENCE_PENALTY_POWER
        
        survival = 1.0
        clusters = [
            breakdown.directional_cluster,
            breakdown.volatility_cluster,
            breakdown.financial_cluster,
            breakdown.context_cluster
        ]
        
        for cluster in clusters:
            effective_risk = self._apply_confidence_dampening(cluster.score, cluster.confidence, CONFIDENCE_PENALTY_POWER)
            p_ruin = effective_risk / 100.0
            survival *= (1.0 - p_ruin)
            
        final_stress = 100.0 * (1.0 - survival)
        
        if combined_pnl > 0.0:
            # Dampen final stress by 50% if the combined position is in profit.
            # This prevents Strike Proximity from triggering EMERGENCY_HEDGE on highly profitable trades.
            final_stress *= 0.50
            
        return final_stress

    def _compute_stress_fusion_inputs(
        self,
        strike_distance_factor: float,
        delta_factor: float,
        gamma_factor: float,
        vega_factor: float,
        premium_growth_factor: float,
        iv_expansion_factor: float,
        trend_factor: float,
        regime_factor: float,
        time_to_expiry_factor: float,
        pnl_factor: float
    ):
        from hedge.models.position import StressFusionBreakdown
        from config import FUSION_SOFTMAX_K
        
        def _safe_float(val) -> float:
            try:
                if val is None or math.isnan(val) or math.isinf(val):
                    return 0.0
                return max(0.0, min(100.0, float(val)))
            except Exception:
                return 0.0
                
        debug_info = {}
        
        factors = {
            "strike_distance_factor": _safe_float(strike_distance_factor),
            "delta_factor": _safe_float(delta_factor),
            "gamma_factor": _safe_float(gamma_factor),
            "vega_factor": _safe_float(vega_factor),
            "premium_growth_factor": _safe_float(premium_growth_factor),
            "iv_expansion_factor": _safe_float(iv_expansion_factor),
            "trend_factor": _safe_float(trend_factor),
            "regime_factor": _safe_float(regime_factor),
            "time_to_expiry_factor": _safe_float(time_to_expiry_factor),
            "pnl_factor": _safe_float(pnl_factor)
        }
        
        k = FUSION_SOFTMAX_K
        
        # 1. Directional Cluster
        dir_inputs = {
            "strike_distance_factor": factors["strike_distance_factor"],
            "delta_factor": factors["delta_factor"],
            "gamma_factor": factors["gamma_factor"]
        }
        dir_weights = {"strike_distance_factor": 0.4, "delta_factor": 0.8, "gamma_factor": 1.0}
        dir_cluster = self._compute_cluster_softmax_ev(dir_inputs, dir_weights, k)
        
        # 2. Volatility Cluster
        vol_inputs = {
            "vega_factor": factors["vega_factor"],
            "iv_expansion_factor": factors["iv_expansion_factor"]
        }
        vol_weights = {"vega_factor": 0.3, "iv_expansion_factor": 0.7}
        vol_cluster = self._compute_cluster_softmax_ev(vol_inputs, vol_weights, k)
        
        # 3. Financial Cluster
        fin_inputs = {
            "premium_growth_factor": factors["premium_growth_factor"],
            "pnl_factor": factors["pnl_factor"]
        }
        fin_weights = {"premium_growth_factor": 0.85, "pnl_factor": 1.5}
        fin_cluster = self._compute_cluster_softmax_ev(fin_inputs, fin_weights, k)
        
        # 4. Context Cluster
        ctx_inputs = {
            "trend_factor": factors["trend_factor"],
            "regime_factor": factors["regime_factor"]
        }
        ctx_weights = {"trend_factor": 0.5, "regime_factor": 0.3}
        ctx_cluster = self._compute_cluster_softmax_ev(ctx_inputs, ctx_weights, k)
        
        debug_info["normalized_factors"] = factors
        debug_info["status"] = "Fusion inputs normalized and mathematically clustered."
        
        breakdown = StressFusionBreakdown(
            strike_distance_factor=factors["strike_distance_factor"],
            delta_factor=factors["delta_factor"],
            gamma_factor=factors["gamma_factor"],
            vega_factor=factors["vega_factor"],
            premium_growth_factor=factors["premium_growth_factor"],
            iv_expansion_factor=factors["iv_expansion_factor"],
            trend_factor=factors["trend_factor"],
            regime_factor=factors["regime_factor"],
            time_to_expiry_factor=factors["time_to_expiry_factor"],
            pnl_factor=factors["pnl_factor"],
            directional_cluster=dir_cluster,
            volatility_cluster=vol_cluster,
            financial_cluster=fin_cluster,
            context_cluster=ctx_cluster,
            fused_score=0.0, 
            debug_information=debug_info
        )
        return breakdown

    def _compute_leg_stress_breakdown(self, trend: TrendResult, regime: MarketRegimeResult, ctx: PositionContext, is_call: bool = True) -> CallStressBreakdown:
        
        # Calculate combined P&L for final stress dampening
        call_pnl = ctx.metadata.get('call_pnl_usd', 0.0)
        put_pnl = ctx.metadata.get('put_pnl_usd', 0.0)
        if call_pnl is None or math.isnan(call_pnl) or math.isinf(call_pnl): call_pnl = 0.0
        if put_pnl is None or math.isnan(put_pnl) or math.isinf(put_pnl): put_pnl = 0.0
        combined_pnl = float(call_pnl) + float(put_pnl)
        
        strike = ctx.short_call_strike if is_call else ctx.short_put_strike
        strike_dist_factor = self._compute_strike_distance_factor(ctx.futures_price, strike) if is_call else self._compute_strike_distance_factor(ctx.futures_price, strike) # Actually, for put it's flipped. Let's do it properly:
        
        if not is_call:
             # For put, stress increases as futures_price drops BELOW strike.
             # x = (strike - futures_price) / strike
             if strike > 0:
                 x = (strike - ctx.futures_price) / strike
                 steepness = 100.0
                 center_offset = 0.03
                 try:
                     exponent = -steepness * (x + center_offset)
                     if exponent > 50: strike_dist_factor = 0.0
                     elif exponent < -50: strike_dist_factor = 100.0
                     else: strike_dist_factor = max(0.0, min(100.0, 100.0 / (1.0 + math.exp(exponent))))
                 except OverflowError:
                     strike_dist_factor = 100.0 if x > -center_offset else 0.0
             else:
                 strike_dist_factor = 0.0
        else:
             strike_dist_factor = self._compute_strike_distance_factor(ctx.futures_price, strike)
             
        delta = ctx.call_delta if is_call else ctx.put_delta
        delta_factor = self._compute_delta_factor(delta)
        
        gamma = ctx.call_gamma if is_call else ctx.put_gamma
        gamma_factor = self._compute_gamma_factor(gamma)
        
        vega = ctx.call_vega if is_call else ctx.put_vega
        vega_factor = self._compute_vega_factor(vega)
        
        # Deduce entry premium
        leg_prefix = "call" if is_call else "put"
        entry_premium = ctx.metadata.get(f'{leg_prefix}_entry_price', None)
        if entry_premium is None:
            from config import LOT_TO_BTC
            lots_per_leg = max(1, ctx.total_lots / 2.0)
            leg_mark = ctx.call_mark_price if is_call else ctx.put_mark_price
            leg_pnl = ctx.call_leg_pnl if is_call else ctx.put_leg_pnl
            
            if LOT_TO_BTC > 0 and lots_per_leg > 0:
                entry_premium = leg_mark + (leg_pnl / (lots_per_leg * LOT_TO_BTC))
            else:
                entry_premium = leg_mark
                
        mark_price = ctx.call_mark_price if is_call else ctx.put_mark_price
        premium_growth_factor = self._compute_premium_growth_factor(mark_price, entry_premium)
        
        # Get entry IV
        entry_iv = ctx.metadata.get(f'{leg_prefix}_entry_iv', None)
        current_iv = ctx.call_iv if is_call else ctx.put_iv
        if entry_iv is None:
            entry_iv = current_iv # fallback to current IV (no expansion)
            
        iv_expansion_factor = self._compute_iv_expansion_factor(current_iv, entry_iv)
        trend_factor = self._compute_trend_factor(trend, is_call=is_call)
        regime_factor = self._compute_regime_factor(regime)
        time_to_expiry_factor = self._compute_time_to_expiry_factor(ctx)
        pnl_factor = self._compute_pnl_factor(ctx, is_call=is_call)
        
        fusion_breakdown = self._compute_stress_fusion_inputs(
            strike_distance_factor=strike_dist_factor,
            delta_factor=delta_factor,
            gamma_factor=gamma_factor,
            vega_factor=vega_factor,
            premium_growth_factor=premium_growth_factor,
            iv_expansion_factor=iv_expansion_factor,
            trend_factor=trend_factor,
            regime_factor=regime_factor,
            time_to_expiry_factor=time_to_expiry_factor,
            pnl_factor=pnl_factor
        )
        
        fusion_breakdown.fused_score = self._compute_mathematical_fusion(fusion_breakdown, combined_pnl)

        return CallStressBreakdown(
            strike_distance_factor=strike_dist_factor,
            delta_factor=delta_factor,
            gamma_factor=gamma_factor,
            vega_factor=vega_factor,
            premium_growth_factor=premium_growth_factor,
            trend_factor=trend_factor,
            regime_factor=regime_factor,
            time_to_expiry_factor=time_to_expiry_factor,
            iv_factor=0.0,
            iv_expansion_factor=iv_expansion_factor,
            pnl_factor=pnl_factor,
            final_call_stress=fusion_breakdown.fused_score,
            explanation=f"{'Call' if is_call else 'Put'} stress components evaluated.",
            fusion_breakdown=fusion_breakdown
        )


    def _compute_leg_stress(self, breakdown: CallStressBreakdown) -> float:
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
