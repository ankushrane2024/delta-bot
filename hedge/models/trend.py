from dataclasses import dataclass
from typing import Optional
from .enums import TrendDirection

@dataclass
class TrendScore:
    direction: TrendDirection
    score: float
    momentum: float
    timeframe: str
