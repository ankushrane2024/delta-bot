from dataclasses import dataclass, field
from typing import Dict, Any, List

@dataclass
class SignalEvidence:
    source: str
    score: float
    confidence: float
    quality: float
    explanation: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    debug_information: Dict[str, Any] = field(default_factory=dict)

@dataclass
class AnalyzerHealth:
    loaded_evaluators: int
    failed_evaluators: int
    warnings: List[str]
    replay_mode: bool
    last_execution_time: float
