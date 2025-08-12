"""
Pydantic schemas for the strategy module.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, validator
from decimal import Decimal


# ============= Common Models =============

class RangeParameters(BaseModel):
    """Concentrated liquidity range parameters."""
    lower_tick: int
    upper_tick: int
    lower_price: Optional[float] = None
    upper_price: Optional[float] = None
    range_percentage: Optional[float] = Field(None, description="Range width as percentage from current price")
    lower_percentage: Optional[float] = Field(None, description="Percentage below current price")
    upper_percentage: Optional[float] = Field(None, description="Percentage above current price")


class RiskMetrics(BaseModel):
    """Risk metrics for a position or pool."""
    volatility_24h: float = Field(..., description="24-hour volatility percentage")
    volume_tvl_ratio: float = Field(..., description="Volume to TVL ratio")
    slippage_estimate: float = Field(..., description="Estimated slippage percentage")


class SlippageInfo(BaseModel):
    """Slippage calculation details."""
    estimated_percentage: float
    max_acceptable: float
    pair_volatility_class: Literal["stable", "semi-volatile", "volatile", "memecoin"]


class ExecutionParams(BaseModel):
    """Execution parameters for trades."""
    exit_percentage: float = Field(..., ge=0, le=100)
    max_slippage: float = Field(..., ge=0, le=10)
    deadline: int = Field(..., description="Deadline in seconds")


# ============= Request Models =============

class OpportunitiesRequest(BaseModel):
    """Request for finding pool opportunities."""
    executor_address: str
    available_capital: float = Field(..., gt=0)


class AnalyzeEntryRequest(BaseModel):
    """Request for analyzing position entry."""
    pool_address: str
    amount_usdc: float = Field(..., gt=0)


class PositionInfo(BaseModel):
    """Information about a position."""
    pool_address: str
    token_id: int
    entry_price: float
    current_range: RangeParameters
    invested_amount: float
    entry_timestamp: datetime


class MonitorPositionsRequest(BaseModel):
    """Request for monitoring active positions."""
    user_address: str = Field(..., description="User wallet address to monitor positions for")


class RangeBreakRequest(BaseModel):
    """Request for handling range breaks."""
    token_id: int = Field(..., description="NFT token ID of the position to check")


class ExitAnalysisRequest(BaseModel):
    """Request for analyzing position exit."""
    token_id: int = Field(..., description="NFT token ID of the position")
    exit_reason: Literal["manual", "stop_loss", "take_profit", "range_break", "rebalance"]


class WhipsawDetectionRequest(BaseModel):
    """Request for detecting whipsaw patterns."""
    token_id: int = Field(..., description="NFT token ID of the position")


class PortfolioRebalanceRequest(BaseModel):
    """Request for portfolio rebalancing."""
    user_address: str = Field(..., description="User wallet address")
    available_capital: float = Field(default=0, ge=0)


class SlippageCalculationRequest(BaseModel):
    """Request for calculating slippage."""
    pool_address: str
    action: Literal["enter", "exit"]
    amount_usdc: float = Field(..., gt=0)


# ============= Response Models =============

class PoolOpportunity(BaseModel):
    """Pool opportunity information."""
    pool_address: str
    pair: str
    score: float = Field(..., ge=0, le=100)
    expected_apr: float
    effective_apr: float = Field(..., description="Effective APR based on recommended range")
    apr_efficiency: float = Field(..., ge=0, le=100, description="Percentage of base APR captured")
    recommended_amount: float
    recommended_range: RangeParameters
    risk_metrics: RiskMetrics
    entry_conditions_met: bool


class OpportunitiesResponse(BaseModel):
    """Response for pool opportunities."""
    opportunities: List[PoolOpportunity]
    optimal_position_count: int = Field(..., description="Recommended total number of positions")
    minimum_position_size: float = Field(..., description="Minimum viable position size in USDC")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class RiskAnalysis(BaseModel):
    """Risk analysis for a position."""
    position_var_1d: float
    portfolio_impact: float
    correlation_benefit: float


class AnalyzeEntryResponse(BaseModel):
    """Response for entry analysis."""
    should_enter: bool
    confidence_score: float = Field(..., ge=0, le=100)
    slippage: SlippageInfo
    risk_analysis: RiskAnalysis
    optimal_range: RangeParameters
    effective_apr: float = Field(..., description="Effective APR for the optimal range")
    apr_efficiency: float = Field(..., ge=0, le=100, description="Percentage of base APR captured")
    warnings: List[str] = Field(default_factory=list)


class RangeStatus(BaseModel):
    """Range status information."""
    in_range: bool
    price_position: float = Field(..., ge=0, le=1, description="Position within range (0-1)")
    range_break_severity: float = Field(..., ge=0, le=100)


class PositionStatus(BaseModel):
    """Position monitoring status."""
    token_id: int
    pool_address: str
    status: Literal["in_range", "out_of_range", "critical"]
    health_score: float = Field(..., ge=0, le=100)
    current_apr: float
    accumulated_fees: float
    accumulated_rewards: float
    range_status: RangeStatus
    recommended_action: Literal["hold", "monitor", "rebalance", "exit"]
    action_details: Optional[Dict[str, Any]] = None


class PortfolioMetrics(BaseModel):
    """Portfolio-level metrics."""
    total_value: float
    unrealized_pnl: float
    current_apr: float
    risk_score: float = Field(..., ge=0, le=100)


class MonitorPositionsResponse(BaseModel):
    """Response for position monitoring."""
    positions: List[PositionStatus]
    portfolio_metrics: PortfolioMetrics


class AlternativeAction(BaseModel):
    """Alternative action for range breaks."""
    type: Literal["rebalance", "partial_exit", "hold"]
    new_range: Optional[RangeParameters] = None
    expected_cost: float


class RangeBreakMetrics(BaseModel):
    """Metrics for range break analysis."""
    reversal_probability: float = Field(..., ge=0, le=1)
    expected_loss_if_reversal: float
    break_severity: float = Field(..., ge=0, le=100)


class RangeBreakResponse(BaseModel):
    """Response for range break handling."""
    action: Literal["emergency_exit", "partial_exit", "rebalance", "monitor"]
    urgency: Literal["low", "medium", "high", "critical"]
    reasoning: str
    execution_params: ExecutionParams
    alternative_action: AlternativeAction
    risk_metrics: RangeBreakMetrics


class OptimalTiming(BaseModel):
    """Optimal timing for exit."""
    execute_now: bool
    wait_minutes: int = Field(..., ge=0)


class ExitAnalysisResponse(BaseModel):
    """Response for exit analysis."""
    should_exit: bool
    exit_strategy: Literal["immediate", "graduated", "wait"]
    optimal_timing: OptimalTiming
    slippage_estimate: float
    expected_proceeds: float
    roi_percentage: float
    tax_implications: Optional[str] = None


class AlternativeStrategy(BaseModel):
    """Alternative strategy for whipsaw."""
    type: Literal["widen_range", "reduce_position", "exit"]
    new_range_multiplier: Optional[float] = None
    reduction_percentage: Optional[float] = None


class WhipsawDetectionResponse(BaseModel):
    """Response for whipsaw detection."""
    whipsaw_detected: bool
    severity: float = Field(..., ge=0, le=100)
    pattern: Literal["high_frequency_reversal", "expanding_volatility", "none"]
    recommended_action: Literal["exit", "reduce", "widen_range", "monitor"]
    alternative_strategies: List[AlternativeStrategy]


class RebalanceRecommendation(BaseModel):
    """Rebalancing recommendation."""
    action: Literal["close", "reduce", "open", "increase"]
    token_id: Optional[int] = None
    pool_address: Optional[str] = None
    target_percentage: Optional[float] = None
    suggested_amount: Optional[float] = None
    reason: str


class PortfolioImprovement(BaseModel):
    """Expected portfolio improvement metrics."""
    apr_increase: float
    risk_reduction: float
    sharpe_improvement: float


class PortfolioRebalanceResponse(BaseModel):
    """Response for portfolio rebalancing."""
    recommendations: List[RebalanceRecommendation]
    expected_portfolio_improvement: PortfolioImprovement
    is_full_rebalance: bool = Field(default=False, description="True if withdrawal detected requiring full rebalance")


class SlippageCalculationResponse(BaseModel):
    """Response for slippage calculation."""
    base_slippage: float
    size_impact: float
    volatility_adjustment: float
    total_slippage: float
    max_recommended: float
    pair_classification: Literal["stable", "semi-volatile", "volatile", "memecoin"]


class PortfolioVaR(BaseModel):
    """Portfolio Value at Risk metrics."""
    var_1d_95: float
    var_7d_95: float


class ConcentrationRisk(BaseModel):
    """Concentration risk metrics."""
    highest_pool_percentage: float
    highest_token_percentage: float


class RangeBreakRisk(BaseModel):
    """Range break risk metrics."""
    positions_at_risk: int
    potential_loss: float


class RiskAssessmentResponse(BaseModel):
    """Response for risk assessment."""
    portfolio_var: PortfolioVaR
    concentration_risk: ConcentrationRisk
    range_break_risk: RangeBreakRisk
    warnings: List[str]
    risk_score: float = Field(..., ge=0, le=100)
    recommended_actions: List[str]


class ReturnMetrics(BaseModel):
    """Return metrics."""
    total_pnl: float
    roi_percentage: float
    apr: float


class FeeBreakdown(BaseModel):
    """Fee breakdown."""
    trading_fees: float
    rewards: float
    gas_costs: float
    slippage_costs: float


class RiskPerformanceMetrics(BaseModel):
    """Risk-adjusted performance metrics."""
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float = Field(..., ge=0, le=1)


class ExecutionQuality(BaseModel):
    """Execution quality metrics."""
    avg_slippage: float
    successful_entries: int
    successful_exits: int
    range_breaks_handled: int


class PerformanceAnalyticsResponse(BaseModel):
    """Response for performance analytics."""
    returns: ReturnMetrics
    fee_breakdown: FeeBreakdown
    risk_metrics: RiskPerformanceMetrics
    execution_quality: ExecutionQuality


# ============= Error Models =============

class ErrorDetail(BaseModel):
    """Error detail information."""
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: ErrorDetail