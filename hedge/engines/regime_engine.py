import uuid
import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from hedge.engines.base_engine import AbstractBaseEngine
from hedge.models.trend import TrendResult
from hedge.models.enums import MarketRegime
from hedge.models.regime import MarketRegimeResult, TransitionRecord
from hedge.models.shared import AnalyzerHealth

logger = logging.getLogger("ARES.MarketRegimeEngine")

class MarketRegimeEngine(AbstractBaseEngine):
    def __init__(self, replay_mode: bool = False):
        self.replay_mode = replay_mode
        self._warnings: List[str] = []
        
        # State tracking
        self.current_regime: MarketRegime = MarketRegime.SAFE_RANGE
        self.regime_entered_at: float = time.time()
        self.transition_history: List[TransitionRecord] = []
        self._last_execution_time: float = 0.0
        
        # Define allowed transitions for validation
        self.valid_transitions = {
            MarketRegime.SAFE_RANGE: [MarketRegime.WEAK_RANGE, MarketRegime.TRANSITION, MarketRegime.SAFE_RANGE],
            MarketRegime.WEAK_RANGE: [MarketRegime.SAFE_RANGE, MarketRegime.TRANSITION, MarketRegime.WEAK_RANGE],
            MarketRegime.TRANSITION: [MarketRegime.SAFE_RANGE, MarketRegime.WEAK_RANGE, MarketRegime.EARLY_TREND, MarketRegime.TRANSITION],
            MarketRegime.EARLY_TREND: [MarketRegime.TRANSITION, MarketRegime.CONFIRMED_TREND, MarketRegime.EARLY_TREND],
            MarketRegime.CONFIRMED_TREND: [MarketRegime.EARLY_TREND, MarketRegime.ACCELERATION, MarketRegime.TREND_EXHAUSTION, MarketRegime.CONFIRMED_TREND],
            MarketRegime.ACCELERATION: [MarketRegime.CONFIRMED_TREND, MarketRegime.TREND_EXHAUSTION, MarketRegime.ACCELERATION],
            MarketRegime.TREND_EXHAUSTION: [MarketRegime.TRANSITION, MarketRegime.CONFIRMED_TREND, MarketRegime.TREND_EXHAUSTION],
        }

    def initialize(self) -> None:
        logger.info("Initialized MarketRegimeEngine.")
        self.reset()

    def evaluate(self, trend_result: TrendResult) -> MarketRegimeResult:
        started_at = time.time()
        evaluation_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        self._warnings.clear()
        
        # 1. Determine the candidate regime based on the TrendResult
        candidate_regime = self._determine_candidate_regime(trend_result)
        is_external = "external_regime" in trend_result.debug_information
        
        # 2. Validate the transition (external overrides bypass strict state machine)
        if is_external:
            is_allowed = True
            reason = f"External signal override: {trend_result.debug_information.get('external_regime', '?')}"
        else:
            is_allowed, reason = self._validate_transition(self.current_regime, candidate_regime)
        
        # 3. Compute auxiliary metrics
        confidence = self._compute_confidence(trend_result)
        strength = self._compute_strength(trend_result)
        stability = self._compute_stability(trend_result)
        
        previous_regime = self.current_regime
        
        # 4. Update state if allowed
        if is_allowed and candidate_regime != self.current_regime:
            self._update_state(candidate_regime)
            
        # 5. Record the transition history
        record = TransitionRecord(
            previous_regime=previous_regime,
            requested_regime=candidate_regime,
            accepted=is_allowed,
            reason=reason,
            confidence=confidence,
            timestamp=timestamp
        )
        self.transition_history.append(record)
        
        regime_duration = time.time() - self.regime_entered_at
        
        completed_at = time.time()
        execution_time_ms = (completed_at - started_at) * 1000.0
        self._last_execution_time = execution_time_ms
        
        result = MarketRegimeResult(
            evaluation_id=evaluation_id,
            current_regime=self.current_regime,
            previous_regime=previous_regime if self.current_regime != previous_regime else None,
            confidence=confidence,
            transition_reason=reason,
            transition_allowed=is_allowed,
            regime_duration=regime_duration,
            regime_strength=strength,
            stability_score=stability,
            timestamp=timestamp,
            debug_information={"warnings": list(self._warnings)}
        )
        
        logger.debug(f"MarketRegimeEngine evaluated in {execution_time_ms:.2f}ms. State: {self.current_regime.name}")
        return result

    # --- Placeholder Logic Methods ---
    
    def _determine_candidate_regime(self, trend_result: TrendResult) -> MarketRegime:
        """Map trend signals to regime states. Uses external_regime override
        injected by the orchestrator from the filters.py ADX+BB+RSI engine."""
        
        # Check for external regime override injected by orchestrator
        if "external_regime" in trend_result.debug_information:
            external = trend_result.debug_information["external_regime"]
            # Map the filters.py signal strings to MarketRegime enum
            regime_map = {
                "UPTREND START": MarketRegime.CONFIRMED_TREND,
                "DOWNTREND START": MarketRegime.CONFIRMED_TREND,
                "STRENGTHENING UP": MarketRegime.ACCELERATION,
                "STRENGTHENING DOWN": MarketRegime.ACCELERATION,
                "TRENDING": MarketRegime.CONFIRMED_TREND,
                "WEAKENING": MarketRegime.TREND_EXHAUSTION,
                "SIDEWAYS": MarketRegime.SAFE_RANGE,
                "WAITING": MarketRegime.SAFE_RANGE,
            }
            candidate = regime_map.get(external, MarketRegime.SAFE_RANGE)
            logger.info(f"External regime signal '{external}' -> {candidate.name}")
            return candidate
        
        # Legacy: use force_regime for tests
        if "force_regime" in trend_result.debug_information:
            return trend_result.debug_information["force_regime"]
        return self.current_regime

    def _validate_transition(self, current: MarketRegime, candidate: MarketRegime) -> tuple[bool, str]:
        if candidate == current:
            return True, "Maintained current regime."
            
        allowed_targets = self.valid_transitions.get(current, [])
        if candidate in allowed_targets:
            return True, f"Valid transition from {current.name} to {candidate.name}."
        
        msg = f"Invalid transition attempt from {current.name} to {candidate.name}."
        self._warnings.append(msg)
        return False, msg

    def _update_state(self, new_regime: MarketRegime) -> None:
        self.current_regime = new_regime
        self.regime_entered_at = time.time()

    def _compute_confidence(self, trend_result: TrendResult) -> float:
        return 0.0

    def _compute_strength(self, trend_result: TrendResult) -> float:
        return 0.0

    def _compute_stability(self, trend_result: TrendResult) -> float:
        return 0.0

    # ---------------------------------

    def reset(self) -> None:
        self._warnings.clear()
        self.current_regime = MarketRegime.SAFE_RANGE
        self.regime_entered_at = time.time()
        self.transition_history.clear()
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
            "name": "MarketRegimeEngine",
            "current_regime": self.current_regime.name,
            "transitions_recorded": len(self.transition_history)
        }
