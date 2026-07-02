from .base_structure_evaluator import AbstractStructureEvaluator
from hedge.models.shared import SignalEvidence
from hedge.context.market_context import MarketContext

class StructureBreakEvaluator(AbstractStructureEvaluator):
    def evaluate(self, context: MarketContext) -> SignalEvidence:
        return SignalEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )

class HigherHighEvaluator(AbstractStructureEvaluator):
    def evaluate(self, context: MarketContext) -> SignalEvidence:
        return SignalEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )

class LowerLowEvaluator(AbstractStructureEvaluator):
    def evaluate(self, context: MarketContext) -> SignalEvidence:
        return SignalEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )

class SupportResistanceEvaluator(AbstractStructureEvaluator):
    def evaluate(self, context: MarketContext) -> SignalEvidence:
        return SignalEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )

class TrendIntegrityEvaluator(AbstractStructureEvaluator):
    def evaluate(self, context: MarketContext) -> SignalEvidence:
        return SignalEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )

class ChangeOfCharacterEvaluator(AbstractStructureEvaluator):
    def evaluate(self, context: MarketContext) -> SignalEvidence:
        return SignalEvidence(
            source=self.name, score=0.0, confidence=0.0, quality=0.0, explanation="Placeholder"
        )
