from .base_iv_evaluator import AbstractIVEvaluator
from hedge.models.shared import SignalEvidence
from hedge.context.market_context import MarketContext

class IVExpansionEvaluator(AbstractIVEvaluator):
    def evaluate(self, context: MarketContext) -> SignalEvidence:
        return SignalEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )

class IVCompressionEvaluator(AbstractIVEvaluator):
    def evaluate(self, context: MarketContext) -> SignalEvidence:
        return SignalEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )

class IVAccelerationEvaluator(AbstractIVEvaluator):
    def evaluate(self, context: MarketContext) -> SignalEvidence:
        return SignalEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )

class IVSkewEvaluator(AbstractIVEvaluator):
    def evaluate(self, context: MarketContext) -> SignalEvidence:
        return SignalEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )

class IVShockEvaluator(AbstractIVEvaluator):
    def evaluate(self, context: MarketContext) -> SignalEvidence:
        return SignalEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )
