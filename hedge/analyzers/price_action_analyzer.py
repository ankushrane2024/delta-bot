from typing import Dict, Any, List
import uuid
import time
import logging
from datetime import datetime, timezone
from hedge.engines.base_engine import AbstractBaseEngine
from hedge.context.market_context import MarketContext
from hedge.models.price_action import PriceActionResult, PriceActionEvidence, AnalyzerHealth
from hedge.models.enums import TrendDirection
from hedge.analyzers.evaluators.base_evaluator import AbstractPriceEvaluator

logger = logging.getLogger("ARES.PriceActionAnalyzer")

class PriceActionAnalyzer(AbstractBaseEngine):
    def __init__(self, evaluators: List[AbstractPriceEvaluator] = None, replay_mode: bool = False):
        self.evaluators = evaluators or []
        self.replay_mode = replay_mode
        self._warnings: List[str] = []
        self._failed_evaluators = 0
        self._last_execution_time = 0.0

    def initialize(self) -> None:
        logger.info(f"Initialized PriceActionAnalyzer with {len(self.evaluators)} evaluators.")

    def evaluate(self, context: MarketContext) -> PriceActionResult:
        started_at = time.time()
        evaluation_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        self._warnings.clear()
        self._failed_evaluators = 0
        
        evidence_list: List[PriceActionEvidence] = []
        
        for evaluator in self.evaluators:
            try:
                evidence = evaluator.evaluate(context)
                evidence_list.append(evidence)
            except Exception as e:
                self._failed_evaluators += 1
                msg = f"Evaluator {evaluator.name} failed: {str(e)}"
                self._warnings.append(msg)
                logger.error(msg)
                
        # Aggregate scores (Placeholder for actual weighted math)
        # We ensure it returns the strict PriceActionResult structure
        
        completed_at = time.time()
        execution_time_ms = (completed_at - started_at) * 1000.0
        self._last_execution_time = execution_time_ms
        
        result = PriceActionResult(
            evaluation_id=evaluation_id,
            direction=TrendDirection.NONE,
            movement_strength=0.0,
            momentum_strength=0.0,
            impulse_strength=0.0,
            pullback_strength=0.0,
            breakout_quality=0.0,
            rejection_strength=0.0,
            continuation_bias=0.0,
            reversal_bias=0.0,
            confidence=0.0,
            timestamp=timestamp,
            started_at=started_at,
            completed_at=completed_at,
            execution_time_ms=execution_time_ms,
            explanation=f"Aggregated {len(evidence_list)} pieces of evidence.",
            supporting_evidence=evidence_list,
            debug_information={"warnings": self._warnings}
        )
        
        logger.debug(f"Evaluated price action in {execution_time_ms:.2f}ms. ID: {evaluation_id}")
        return result

    def reset(self) -> None:
        self._warnings.clear()
        self._failed_evaluators = 0
        self._last_execution_time = 0.0

    def health(self) -> AnalyzerHealth:
        return AnalyzerHealth(
            loaded_evaluators=len(self.evaluators),
            failed_evaluators=self._failed_evaluators,
            warnings=list(self._warnings),
            replay_mode=self.replay_mode,
            last_execution_time=self._last_execution_time
        )
        
    def metadata(self) -> Dict[str, Any]:
        return {
            "name": "PriceActionAnalyzer",
            "evaluators": [e.name for e in self.evaluators]
        }
