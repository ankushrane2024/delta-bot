from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class PositionRiskResult:
    evaluation_id: str
    overall_risk_score: float
    call_side_risk: float
    put_side_risk: float
    delta_exposure: float
    gamma_exposure: float
    theta_exposure: float
    vega_exposure: float
    stop_loss_proximity: float
    portfolio_heat: float
    hedge_urgency: float
    
    # New placeholders for Module 16 enhancement
    call_stress: float
    put_stress: float
    portfolio_stress: float
    stress_velocity: float
    recovery_probability: float
    hedge_efficiency_estimate: float
    
    confidence: float
    timestamp: str
    started_at: float
    completed_at: float
    execution_time_ms: float
    explanation: str
    call_breakdown: Any = None
    put_breakdown: Any = None
    debug_information: Dict[str, Any] = field(default_factory=dict)

@dataclass
class CallStressBreakdown:
    strike_distance_factor: float = 0.0
    delta_factor: float = 0.0
    gamma_factor: float = 0.0
    vega_factor: float = 0.0
    premium_growth_factor: float = 0.0
    trend_factor: float = 0.0
    regime_factor: float = 0.0
    time_to_expiry_factor: float = 0.0
    iv_factor: float = 0.0
    iv_expansion_factor: float = 0.0
    pnl_factor: float = 0.0
    final_call_stress: float = 0.0
    explanation: str = ""
    fusion_breakdown: Any = None

@dataclass
class ClusterOutput:
    score: float = 0.0
    confidence: float = 100.0
    primary_reason: str = ""
    dominant_factor: str = ""
    raw_inputs: Dict[str, float] = field(default_factory=dict)

@dataclass
class StressFusionBreakdown:
    # Individual Normalized Factors
    strike_distance_factor: float = 0.0
    delta_factor: float = 0.0
    gamma_factor: float = 0.0
    vega_factor: float = 0.0
    premium_growth_factor: float = 0.0
    iv_expansion_factor: float = 0.0
    trend_factor: float = 0.0
    regime_factor: float = 0.0
    time_to_expiry_factor: float = 0.0
    pnl_factor: float = 0.0
    
    # Orthogonal Clusters
    directional_cluster: ClusterOutput = field(default_factory=ClusterOutput)
    volatility_cluster: ClusterOutput = field(default_factory=ClusterOutput)
    financial_cluster: ClusterOutput = field(default_factory=ClusterOutput)
    context_cluster: ClusterOutput = field(default_factory=ClusterOutput)
    
    # Final Fused Bayesian Score
    fused_score: float = 0.0
    
    debug_information: Dict[str, Any] = field(default_factory=dict)
