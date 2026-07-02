from typing import Dict, Any, List
import uuid
import time
import logging
from datetime import datetime, timezone
from hedge.engines.base_engine import AbstractBaseEngine
from hedge.context.market_context import MarketContext
from hedge.models.trend import TrendResult
from hedge.models.enums import TrendDirection
from hedge.models.shared import AnalyzerHealth

logger = logging.getLogger("ARES.TrendEngine")

class TrendEngine(AbstractBaseEngine):
    def __init__(self, analyzers: Dict[str, AbstractBaseEngine] = None, replay_mode: bool = False):
        self.analyzers = analyzers or {}
        self.replay_mode = replay_mode
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
        
        supporting_signals: Dict[str, Any] = {}
        analyzer_health_summary: Dict[str, Any] = {}
        
        # 1. Evidence Collection
        for name, analyzer in self.analyzers.items():
            try:
                # Ensure the analyzer is healthy before calling it, though this is optional
                result = analyzer.evaluate(context)
                supporting_signals[name] = result
                
                # Record the health state of each analyzer
                if hasattr(analyzer, 'health'):
                    health_obj = analyzer.health()
                    # Assuming health_obj is a dataclass, we can log its dict representation
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

        # 2. Check for missing critical analyzers
        if not self.analyzers:
            msg = "TrendEngine executed with ZERO injected analyzers. Reverting to SAFE defaults."
            self._warnings.append(msg)
            logger.warning(msg)

        # 3. Evidence Aggregation (Placeholder framework)
        trend_direction = self._aggregate_direction(supporting_signals)
        trend_strength = self._aggregate_strength(supporting_signals)
        trend_confidence = self._aggregate_confidence(supporting_signals)
        continuation_prob = self._aggregate_continuation(supporting_signals)
        reversal_prob = self._aggregate_reversal(supporting_signals)
        whipsaw_prob = self._aggregate_whipsaw(supporting_signals)
        
        # Reliability drops if analyzers fail
        # Reliability drops if analyzers fail. If 0 analyzers, reliability is 0.
        if not self.analyzers:
            signal_reliability = 0.0
        else:
            signal_reliability = 100.0 * (1 - (self._failed_analyzers / len(self.analyzers)))
        
        completed_at = time.time()
        execution_time_ms = (completed_at - started_at) * 1000.0
        self._last_execution_time = execution_time_ms
        
        result = TrendResult(
            evaluation_id=evaluation_id,
            trend_direction=trend_direction,
            trend_strength=trend_strength,
            trend_confidence=trend_confidence,
            trend_persistence=0.0,  # Placeholder
            trend_acceleration=0.0, # Placeholder
            continuation_probability=continuation_prob,
            reversal_probability=reversal_prob,
            whipsaw_probability=whipsaw_prob,
            signal_reliability=signal_reliability,
            timestamp=timestamp,
            started_at=started_at,
            completed_at=completed_at,
            execution_time_ms=execution_time_ms,
            explanation=f"Aggregated {len(supporting_signals)} active analyzers.",
            supporting_signals=supporting_signals,
            analyzer_health_summary=analyzer_health_summary,
            debug_information={"warnings": list(self._warnings)}
        )
        
        logger.debug(f"TrendEngine evaluated in {execution_time_ms:.2f}ms. ID: {evaluation_id}")
        return result

    # --- Placeholder Aggregation Framework ---
    
    def _aggregate_direction(self, signals: Dict[str, Any]) -> TrendDirection:
        return TrendDirection.NONE

    def _aggregate_strength(self, signals: Dict[str, Any]) -> float:
        return 0.0

    def _aggregate_confidence(self, signals: Dict[str, Any]) -> float:
        return 0.0

    def _aggregate_continuation(self, signals: Dict[str, Any]) -> float:
        return 0.0

    def _aggregate_reversal(self, signals: Dict[str, Any]) -> float:
        return 0.0

    def _aggregate_whipsaw(self, signals: Dict[str, Any]) -> float:
        return 0.0

    # -----------------------------------------

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
