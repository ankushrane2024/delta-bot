from dataclasses import dataclass
from typing import Dict, Any, List

@dataclass
class AnalyticsRecord:
    timestamp: str
    trade_id: str
    hedge_id: str
    market_state: str
    trend_score: float
    risk_score: float
    decision: str
    confidence: float
    reason: str

@dataclass
class TradeTimeline:
    trade_id: str
    events: List[AnalyticsRecord]
    
@dataclass
class DailySummary:
    date: str
    total_trades: int
    hedged_trades: int
    net_pnl: float

@dataclass
class MonthlySummary:
    month: str
    daily_summaries: List[DailySummary]
    total_pnl: float

@dataclass
class PerformanceMetrics:
    win_rate: float
    profit_factor: float
    max_drawdown: float

@dataclass
class CounterfactualAnalysis:
    scenario_id: str
    hypothetical_pnl: float
    actual_pnl: float
    difference: float
