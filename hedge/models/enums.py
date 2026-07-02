from enum import Enum, auto

class MarketRegime(Enum):
    SAFE_RANGE = auto()
    WEAK_RANGE = auto()
    TRANSITION = auto()
    EARLY_TREND = auto()
    CONFIRMED_TREND = auto()
    ACCELERATION = auto()
    TREND_EXHAUSTION = auto()

class TrendDirection(Enum):
    NONE = auto()
    LONG = auto()
    SHORT = auto()

class DecisionAction(Enum):
    NO_ACTION = auto()
    OPEN_HEDGE = auto()
    INCREASE_HEDGE = auto()
    REDUCE_HEDGE = auto()
    CLOSE_HEDGE = auto()
    EXIT_POSITION = auto()

class MarginStatus(Enum):
    SAFE = auto()
    WARNING = auto()
    CRITICAL = auto()
