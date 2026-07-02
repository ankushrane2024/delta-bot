from .base_volatility_evaluator import AbstractVolatilityEvaluator
from hedge.models.shared import SignalEvidence
from hedge.context.market_context import MarketContext

class ExpansionEvaluator(AbstractVolatilityEvaluator):
    def evaluate(self, context: MarketContext) -> SignalEvidence:
        return SignalEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )

class CompressionEvaluator(AbstractVolatilityEvaluator):
    def evaluate(self, context: MarketContext) -> SignalEvidence:
        return SignalEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )

class VolatilitySpikeEvaluator(AbstractVolatilityEvaluator):
    def evaluate(self, context: MarketContext) -> SignalEvidence:
        return SignalEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )

class StabilityEvaluator(AbstractVolatilityEvaluator):
    def evaluate(self, context: MarketContext) -> SignalEvidence:
        return SignalEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )

class AccelerationEvaluator(AbstractVolatilityEvaluator):
    def evaluate(self, context: MarketContext) -> SignalEvidence:
        return SignalEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )
