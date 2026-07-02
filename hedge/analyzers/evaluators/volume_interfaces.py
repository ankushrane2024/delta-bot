from .base_volume_evaluator import AbstractVolumeEvaluator
from hedge.models.shared import SignalEvidence
from hedge.context.market_context import MarketContext

class VolumeExpansionEvaluator(AbstractVolumeEvaluator):
    def evaluate(self, context: MarketContext) -> SignalEvidence:
        return SignalEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )

class ParticipationEvaluator(AbstractVolumeEvaluator):
    def evaluate(self, context: MarketContext) -> SignalEvidence:
        return SignalEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )

class BreakoutConfirmationEvaluator(AbstractVolumeEvaluator):
    def evaluate(self, context: MarketContext) -> SignalEvidence:
        return SignalEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )

class ExhaustionEvaluator(AbstractVolumeEvaluator):
    def evaluate(self, context: MarketContext) -> SignalEvidence:
        return SignalEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )

class VolumeTrendEvaluator(AbstractVolumeEvaluator):
    def evaluate(self, context: MarketContext) -> SignalEvidence:
        return SignalEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )
