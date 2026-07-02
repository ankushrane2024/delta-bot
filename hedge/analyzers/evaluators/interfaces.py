from .base_evaluator import AbstractPriceEvaluator
from hedge.models.price_action import PriceActionEvidence
from hedge.context.market_context import MarketContext

class CandleEvaluator(AbstractPriceEvaluator):
    def evaluate(self, context: MarketContext) -> PriceActionEvidence:
        return PriceActionEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )

class SwingEvaluator(AbstractPriceEvaluator):
    def evaluate(self, context: MarketContext) -> PriceActionEvidence:
        return PriceActionEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )

class BreakoutEvaluator(AbstractPriceEvaluator):
    def evaluate(self, context: MarketContext) -> PriceActionEvidence:
        return PriceActionEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )

class RejectionEvaluator(AbstractPriceEvaluator):
    def evaluate(self, context: MarketContext) -> PriceActionEvidence:
        return PriceActionEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )

class MomentumEvaluator(AbstractPriceEvaluator):
    def evaluate(self, context: MarketContext) -> PriceActionEvidence:
        return PriceActionEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )
