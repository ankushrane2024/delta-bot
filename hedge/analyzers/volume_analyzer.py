from typing import Dict, Any, List
import uuid
import time
import logging
from datetime import datetime, timezone
from hedge.engines.base_engine import AbstractBaseEngine
from hedge.context.market_context import MarketContext
from hedge.models.volume import VolumeResult
from hedge.models.shared import SignalEvidence, AnalyzerHealth
from hedge.analyzers.evaluators.base_volume_evaluator import AbstractVolumeEvaluator

logger = logging.getLogger("ARES.VolumeAnalyzer")

class VolumeAnalyzer(AbstractBaseEngine):
    def __init__(self, evaluators: List[AbstractVolumeEvaluator] = None, replay_mode: bool = False):
        self.evaluators = evaluators or []
        self.replay_mode = replay_mode
        self._warnings: List[str] = []
        self._failed_evaluators = 0
        self._last_execution_time = 0.0

    def initialize(self) -> None:
        logger.info(f"Initialized VolumeAnalyzer with {len(self.evaluators)} evaluators.")

    def evaluate(self, context: MarketContext) -> VolumeResult:
        started_at = time.time()
        evaluation_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        self._warnings.clear()
        self._failed_evaluators = 0
        
        evidence_list: List[SignalEvidence] = []
        
        for evaluator in self.evaluators:
            try:
                evidence = evaluator.evaluate(context)
                evidence_list.append(evidence)
            except Exception as e:
                self._failed_evaluators += 1
                msg = f"Evaluator {evaluator.name} failed: {str(e)}"
                self._warnings.append(msg)
                logger.error(msg)
                
        completed_at = time.time()
        execution_time_ms = (completed_at - started_at) * 1000.0
        self._last_execution_time = execution_time_ms
        
        result = VolumeResult(
            evaluation_id=evaluation_id,
            volume_level=0.0,
            volume_strength=0.0,
            volume_expansion=0.0,
            volume_contraction=0.0,
            participation_strength=0.0,
            breakout_confirmation=0.0,
            exhaustion_probability=0.0,
            continuation_confirmation=0.0,
            confidence=0.0,
            timestamp=timestamp,
            started_at=started_at,
            completed_at=completed_at,
            execution_time_ms=execution_time_ms,
            explanation=f"Aggregated {len(evidence_list)} pieces of volume evidence.",
            supporting_evidence=evidence_list,
            debug_information={"warnings": list(self._warnings)}
        )
        
        logger.debug(f"Evaluated volume in {execution_time_ms:.2f}ms. ID: {evaluation_id}")
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
            "name": "VolumeAnalyzer",
            "evaluators": [e.name for e in self.evaluators]
        }
