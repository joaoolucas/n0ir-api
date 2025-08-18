"""
Enhanced Pydantic schemas for comprehensive strategy screening.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field

# Import existing models to reuse
from app.schemas.strategy import (
    RangeParameters,
    RiskMetrics,
    SlippageInfo,
    ExecutionParams,
    PoolOpportunity,
    PositionStatus,
    PortfolioMetrics,
    RiskAnalysis,
    OptimalTiming,
    AlternativeAction,
    RangeBreakMetrics,
    AlternativeStrategy,
    RebalanceRecommendation,
    PortfolioImprovement,
    ErrorDetail,
    ErrorResponse
)

# ============= New Models for Enhanced Screening =============

class UserContext(BaseModel):
    """User context information for comprehensive screening."""
    executor_address: str
    available_capital: float
    positions_value: float
    total_portfolio_value: float
    active_positions: int


class EntryAnalysis(BaseModel):
    """Detailed entry analysis for a pool opportunity."""
    pool_address: str
    pool_name: str
    confidence_score: float = Field(..., ge=0, le=100)
    optimal_allocation: float
    expected_apr: float
    risk_metrics: Dict[str, Any]
    optimal_range: Dict[str, Any]


class ExitRecommendation(BaseModel):
    """Exit recommendation for an existing position."""
    token_id: int
    pool_address: str
    urgency: Literal["low", "medium", "high", "critical"]
    reason: str
    expected_proceeds: float
    roi_percentage: float
    slippage_estimate: float


class SwitchRecommendation(BaseModel):
    """Switch recommendation from one position to another."""
    from_token_id: int
    from_pool: str
    to_pool_address: str
    to_pool_name: str
    apr_improvement: float
    net_benefit_after_costs: float
    confidence: float = Field(..., ge=0, le=100)


class ImmediateAction(BaseModel):
    """Immediate action to take."""
    type: Literal["entry", "exit", "switch"]
    priority: int
    details: Dict[str, Any]


class ScheduledAction(BaseModel):
    """Scheduled action for future execution."""
    type: Literal["entry", "exit", "switch", "rebalance"]
    schedule: str  # e.g., "tomorrow", "in_2_hours", etc.
    details: Dict[str, Any]


class CapitalAllocation(BaseModel):
    """Capital allocation recommendations."""
    recommended_positions: int
    allocation_per_position: float
    active_positions: int


class DecisionMatrix(BaseModel):
    """Decision matrix for strategic actions."""
    immediate_actions: List[ImmediateAction]
    scheduled_actions: List[ScheduledAction]
    capital_allocation: CapitalAllocation


class RiskAlert(BaseModel):
    """Risk alert for portfolio."""
    type: Literal["concentration", "portfolio_health", "over_diversification", "capital_fragmentation"]
    message: str
    severity: Literal["low", "medium", "high", "critical"]


class EnhancedScreenRequest(BaseModel):
    """Enhanced request for comprehensive screening."""
    executor_address: str
    available_capital: float = Field(..., gt=0)


class EnhancedScreenResponse(BaseModel):
    """Enhanced response with comprehensive analysis."""
    # User context
    user_context: UserContext
    
    # Opportunities (existing field for backward compatibility)
    opportunities: List[PoolOpportunity]
    
    # New comprehensive analysis fields
    entry_analyses: List[EntryAnalysis] = Field(default_factory=list)
    exit_recommendations: List[ExitRecommendation] = Field(default_factory=list)
    switch_recommendations: List[SwitchRecommendation] = Field(default_factory=list)
    
    # Decision support
    decision_matrix: Optional[DecisionMatrix] = None
    risk_alerts: List[RiskAlert] = Field(default_factory=list)
    
    # Existing fields for backward compatibility
    optimal_position_count: int = Field(..., description="Recommended total number of positions")
    minimum_position_size: float = Field(..., description="Minimum viable position size in USDC")
    
    # Metadata
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    analysis_timestamp: Optional[datetime] = None
    cache_hit: bool = Field(default=False)
    analysis_time_ms: Optional[int] = None