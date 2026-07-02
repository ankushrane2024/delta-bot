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

class AresDecision(Enum):
    HOLD = auto()
    PREPARE_HEDGE = auto()
    OPEN_HEDGE = auto()
    INCREASE_HEDGE = auto()
    REDUCE_HEDGE = auto()
    CLOSE_HEDGE = auto()
    EMERGENCY_EXIT = auto()

class MarginStatus(Enum):
    SAFE = auto()
    WARNING = auto()
    CRITICAL = auto()

class HedgeState(Enum):
    NOT_ACTIVE = auto()
    PENDING_OPEN = auto()
    ACTIVE = auto()
    SCALING_UP = auto()
    SCALING_DOWN = auto()
    PENDING_CLOSE = auto()
    CLOSED = auto()
    CANCELLED = auto()

class HedgeSide(Enum):
    NONE = auto()
    LONG = auto()
    SHORT = auto()

class ExecutionStatus(Enum):
    PENDING = auto()
    VALIDATED = auto()
    READY = auto()
    SUBMITTED = auto()
    PARTIALLY_FILLED = auto()
    FILLED = auto()
    FAILED = auto()
    CANCELLED = auto()
