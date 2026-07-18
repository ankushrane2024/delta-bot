from typing import Dict, Any, List, Tuple
import uuid
import time
import logging
from datetime import datetime, timezone
from hedge.engines.base_engine import AbstractBaseEngine
from hedge.context.market_context import MarketContext
from hedge.models.trend import TrendResult
from hedge.models.enums import TrendDirection
from hedge.models.shared import AnalyzerHealth, SignalEvidence

logger = logging.getLogger("ARES.TrendEngine")

class TrendEngine(AbstractBaseEngine):
    def __init__(self, analyzers: Dict[str, AbstractBaseEngine] = None, replay_mode: bool = False, analyzer_weights: Dict[str, float] = None):
        self.analyzers = analyzers or {}
        self.replay_mode = replay_mode
        self.analyzer_weights = analyzer_weights or {}
        self._warnings: List[str] = []
        self._failed_analyzers = 0
        self._last_execution_time = 0.0

    def initialize(self) -> None:
        logger.info(f"Initialized TrendEngine with {len(self.analyzers)} analyzers.")
        for name, analyzer in self.analyzers.items():
            analyzer.initialize()

    def evaluate(self, context: MarketContext) -> TrendResult:
        started_at = time.time()
        evaluation_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        self._warnings.clear()
        self._failed_analyzers = 0
        
        # Pipeline execution
        evidence_list, health_summary = self._collect_evidence(context)
        valid_evidence = self._validate_evidence(evidence_list)
        result = self._build_trend_result(
            evaluation_id=evaluation_id,
            timestamp=timestamp,
            started_at=started_at,
            evidence_list=valid_evidence,
            analyzer_health_summary=health_summary
        )
        
        logger.debug(f"TrendEngine evaluated in {result.execution_time_ms:.2f}ms. ID: {evaluation_id}")
        return result
        
    def _collect_evidence(self, context: MarketContext) -> Tuple[List[SignalEvidence], Dict[str, Any]]:
        evidence_list: List[SignalEvidence] = []
        analyzer_health_summary: Dict[str, Any] = {}
        
        for name, analyzer in self.analyzers.items():
            try:
                result = analyzer.evaluate(context)
                
                # Extract SignalEvidence objects if the result contains them
                if hasattr(result, 'supporting_evidence'):
                    evidence_list.extend(result.supporting_evidence)
                elif isinstance(result, dict) and 'supporting_evidence' in result:
                    evidence_list.extend(result['supporting_evidence'])
                elif isinstance(result, dict) and 'dummy_field' in result:
                    # For dummy analyzers in tests
                    evidence_list.append(SignalEvidence(source=name, score=result.get('dummy_field', 0), confidence=0.0, quality=0.0, explanation="dummy"))
                
                # Record health
                if hasattr(analyzer, 'health'):
                    health_obj = analyzer.health()
                    analyzer_health_summary[name] = {
                        "failed_evaluators": getattr(health_obj, "failed_evaluators", 0),
                        "warnings": getattr(health_obj, "warnings", [])
                    }
            except Exception as e:
                self._failed_analyzers += 1
                msg = f"Analyzer {name} failed during evaluation: {str(e)}"
                self._warnings.append(msg)
                logger.error(msg)
                analyzer_health_summary[name] = {"error": str(e)}

        if not self.analyzers:
            msg = "TrendEngine executed with ZERO injected analyzers. Reverting to SAFE defaults."
            self._warnings.append(msg)
            logger.warning(msg)
            
        return evidence_list, analyzer_health_summary

    def _validate_evidence(self, evidence_list: List[SignalEvidence]) -> List[SignalEvidence]:
        # Placeholder for evidence validation logic
        return evidence_list
        
    def _compute_reliability(self) -> float:
        # Reliability drops if analyzers fail. If 0 analyzers, reliability is 0.
        if not self.analyzers:
            return 0.0
        return 100.0 * (1 - (self._failed_analyzers / len(self.analyzers)))

    def _build_trend_result(self, evaluation_id: str, timestamp: str, started_at: float, evidence_list: List[SignalEvidence], analyzer_health_summary: Dict[str, Any]) -> TrendResult:
        trend_direction = self._aggregate_direction(evidence_list, self.analyzer_weights)
        trend_strength = self._aggregate_strength(evidence_list, self.analyzer_weights)
        trend_confidence = self._aggregate_confidence(evidence_list, self.analyzer_weights)
        continuation_prob = self._aggregate_continuation(evidence_list, self.analyzer_weights)
        reversal_prob = self._aggregate_reversal(evidence_list, self.analyzer_weights)
        whipsaw_prob = self._aggregate_whipsaw(evidence_list, self.analyzer_weights)
        
        signal_reliability = self._compute_reliability()
        
        completed_at = time.time()
        execution_time_ms = (completed_at - started_at) * 1000.0
        self._last_execution_time = execution_time_ms
        
        return TrendResult(
            evaluation_id=evaluation_id,
            trend_direction=trend_direction,
            trend_strength=trend_strength,
            trend_confidence=trend_confidence,
            trend_persistence=0.0,
            trend_acceleration=0.0,
            continuation_probability=continuation_prob,
            reversal_probability=reversal_prob,
            whipsaw_probability=whipsaw_prob,
            signal_reliability=signal_reliability,
            timestamp=timestamp,
            started_at=started_at,
            completed_at=completed_at,
            execution_time_ms=execution_time_ms,
            explanation=f"Aggregated {len(evidence_list)} pieces of valid evidence.",
            supporting_evidence=evidence_list,
            analyzer_health_summary=analyzer_health_summary,
            debug_information={"warnings": list(self._warnings)}
        )

    # --- Placeholder Aggregation Framework (Ready for Weights) ---
    
    def _aggregate_direction(self, evidence: List[SignalEvidence], weights: Dict[str, float] = None) -> TrendDirection:
        return TrendDirection.NONE

    def _aggregate_strength(self, evidence: List[SignalEvidence], weights: Dict[str, float] = None) -> float:
        return 0.0

    def _aggregate_confidence(self, evidence: List[SignalEvidence], weights: Dict[str, float] = None) -> float:
        return 0.0

    def _aggregate_continuation(self, evidence: List[SignalEvidence], weights: Dict[str, float] = None) -> float:
        return 0.0

    def _aggregate_reversal(self, evidence: List[SignalEvidence], weights: Dict[str, float] = None) -> float:
        return 0.0

    def _aggregate_whipsaw(self, evidence: List[SignalEvidence], weights: Dict[str, float] = None) -> float:
        return 0.0

    # -------------------------------------------------------------

    def reset(self) -> None:
        self._warnings.clear()
        self._failed_analyzers = 0
        self._last_execution_time = 0.0
        for analyzer in self.analyzers.values():
            analyzer.reset()

    def health(self) -> AnalyzerHealth:
        return AnalyzerHealth(
            loaded_evaluators=len(self.analyzers),
            failed_evaluators=self._failed_analyzers,
            warnings=list(self._warnings),
            replay_mode=self.replay_mode,
            last_execution_time=self._last_execution_time
        )
        
    def metadata(self) -> Dict[str, Any]:
        return {
            "name": "TrendEngine",
            "analyzers": list(self.analyzers.keys())
        }
