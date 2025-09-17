"""
Consolidated Pydantic schemas for strategy-related endpoints.

This module combines all strategy schemas (v1, v2, v2_enhanced) into a single file
with clear organization and version support for backwards compatibility.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any, Literal, Union
from pydantic import BaseModel, Field, validator
from decimal import Decimal


# ============= Base/Common Models =============

class ErrorDetail(BaseModel):
    """Detailed error information."""
    field: Optional[str] = None
    message: str
    code: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    details: Optional[ErrorDetail] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class RangeParameters(BaseModel):
    """Range parameters for a position."""
    tick_lower: int
    tick_upper: int
    price_lower: float
    price_upper: float
    width_percentage: float = Field(..., ge=0, le=100)


class RangeStatus(BaseModel):
    """Range status for a position."""
    in_range: bool = Field(..., description="Whether the position is currently in range")
    price_position: float = Field(..., description="Current price relative to range (0.0 = lower bound, 1.0 = upper bound)")
    range_break_severity: float = Field(..., ge=0, le=100, description="Severity of range break (0-100)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "in_range": True,
                "price_position": 0.5,
                "range_break_severity": 0
            }
        }


class RiskMetrics(BaseModel):
    """Risk metrics for position/pool analysis."""
    volatility_1d: float = Field(..., ge=0)
    volatility_7d: float = Field(..., ge=0)
    var_95_1d: float
    var_95_7d: float
    sharpe_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    impermanent_loss_estimate: float


class SlippageInfo(BaseModel):
    """Slippage information for transactions."""
    estimated_slippage_bps: float
    max_slippage_bps: float
    price_impact: float
    execution_price: float


class ExecutionParams(BaseModel):
    """Parameters for transaction execution."""
    gas_estimate: int
    gas_price_gwei: float
    max_priority_fee_gwei: float
    deadline_minutes: int = 30


# ============= Pool & Position Models =============

class PoolInfo(BaseModel):
    """Basic pool information."""
    address: str
    token0_symbol: str
    token1_symbol: str
    fee: int
    tick_spacing: int
    current_tick: int
    current_price: float
    liquidity: float
    volume_24h: float
    tvl_usd: float


class PositionStatus(BaseModel):
    """Status of an existing position."""
    token_id: int
    pool_address: str
    status: str = Field(..., description="Position status (active, inactive, etc.)")
    health_score: float = Field(..., ge=0, le=100, description="Position health score")
    current_apr: float = Field(..., description="Current effective APR")
    accumulated_fees: float = Field(..., description="Accumulated fees in USD")
    accumulated_rewards: float = Field(..., description="Accumulated rewards in USD")
    range_status: RangeStatus = Field(..., description="Range status information")
    recommended_action: str = Field(..., description="Recommended action (hold, rebalance, exit, monitor)")
    action_details: Optional[Dict[str, Any]] = Field(None, description="Details about the recommended action")


class PoolOpportunity(BaseModel):
    """Complete pool opportunity analysis."""
    pool: PoolInfo
    score: float = Field(..., ge=0, le=100)
    expected_apr: float
    confidence_level: float = Field(..., ge=0, le=100)
    optimal_range: RangeParameters
    risk_metrics: RiskMetrics
    recommended_amount_usdc: float
    reasoning: str


# ============= Portfolio & Analysis Models =============

class PortfolioMetrics(BaseModel):
    """Portfolio-level metrics."""
    total_value_usd: float
    total_pnl_usd: float
    total_pnl_percentage: float
    active_positions: int
    average_apr: float
    portfolio_volatility: float
    diversification_score: float = Field(..., ge=0, le=100)


class RiskAnalysis(BaseModel):
    """Comprehensive risk analysis."""
    overall_risk_score: float = Field(..., ge=0, le=100)
    concentration_risk: float = Field(..., ge=0, le=100)
    market_risk: float = Field(..., ge=0, le=100)
    liquidity_risk: float = Field(..., ge=0, le=100)
    warnings: List[str]
    recommendations: List[str]


class OptimalTiming(BaseModel):
    """Optimal timing recommendations."""
    recommended_action: Literal["immediate", "wait", "dca"]
    reasoning: str
    wait_hours: Optional[int] = None
    confidence: float = Field(..., ge=0, le=100)


class AlternativeAction(BaseModel):
    """Alternative action suggestion."""
    action_type: Literal["switch_pool", "adjust_range", "partial_exit", "add_liquidity"]
    description: str
    expected_improvement: float
    confidence: float = Field(..., ge=0, le=100)


# ============= V2 Models (Analyze) =============

class AnalyzeEntryData(BaseModel):
    """Entry-specific data for analyze request."""
    pool_address: str
    amount_usdc: float = Field(..., gt=0)


class AnalyzeExitData(BaseModel):
    """Exit-specific data for analyze request."""
    token_id: int = Field(..., description="NFT token ID of the position")
    exit_reason: Literal["manual", "stop_loss", "take_profit", "range_break", "rebalance"]


class AnalyzeSlippageData(BaseModel):
    """Slippage-specific data for analyze request."""
    pool_address: str
    action: Literal["enter", "exit"]
    amount_usdc: float = Field(..., gt=0)


class AnalyzeSwitchData(BaseModel):
    """Switch-specific data for analyze request."""
    from_token_id: int
    to_pool_address: str
    amount_usdc: Optional[float] = None


class AnalyzeRequest(BaseModel):
    """Unified analyze request supporting multiple analyze types."""
    analyze_type: Literal["entry", "exit", "slippage", "switch"]
    executor_address: str
    
    # Type-specific data (only one should be provided based on analyze_type)
    entry_data: Optional[AnalyzeEntryData] = None
    exit_data: Optional[AnalyzeExitData] = None
    slippage_data: Optional[AnalyzeSlippageData] = None
    switch_data: Optional[AnalyzeSwitchData] = None
    
    @validator('entry_data', 'exit_data', 'slippage_data', 'switch_data')
    def validate_type_data(cls, v, values):
        """Ensure the correct data field is provided for the analyze_type."""
        if 'analyze_type' not in values:
            return v
            
        analyze_type = values['analyze_type']
        field_map = {
            'entry': 'entry_data',
            'exit': 'exit_data',
            'slippage': 'slippage_data',
            'switch': 'switch_data'
        }
        
        expected_field = field_map[analyze_type]
        current_field = None
        
        for field, data_field in field_map.items():
            if v is not None and data_field == expected_field:
                current_field = data_field
                break
                
        if current_field and current_field != expected_field:
            raise ValueError(f"For analyze_type '{analyze_type}', only '{expected_field}' should be provided")
            
        return v


# ============= Screen Models =============

class ScreenRequest(BaseModel):
    """Enhanced screening request."""
    executor_address: str
    available_capital: Optional[float] = Field(
        default=None,
        ge=0,
        description="Optional available capital override; if omitted the API fetches on-chain balance."
    )


class ScreenResponse(BaseModel):
    """Screening response with opportunities."""
    opportunities: List[PoolOpportunity]
    portfolio_metrics: Optional[PortfolioMetrics] = None
    risk_analysis: Optional[RiskAnalysis] = None
    optimal_position_count: int
    minimum_position_size: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    cache_hit: bool = False
    analysis_time_ms: Optional[int] = None


# ============= Monitor Models =============

class MonitorRequest(BaseModel):
    """Request for position monitoring."""
    executor_address: str
    check_all_positions: bool = True
    position_ids: Optional[List[int]] = None
    check_range_breaks: bool = True
    check_whipsaw: bool = True


class RangeBreakAlert(BaseModel):
    """Alert for range break detection."""
    token_id: int
    pool_address: str
    severity: float = Field(..., description="Severity of the range break")
    action: str = Field(..., description="Recommended action")
    urgency: str = Field(..., description="Urgency level")
    reversal_probability: float = Field(..., description="Probability of price reversal")
    expected_loss_if_reversal: float = Field(..., description="Expected loss if reversal occurs")


class WhipsawAlert(BaseModel):
    """Alert for whipsaw detection."""
    token_id: int
    pool_address: str
    whipsaw_detected: bool = Field(..., description="Whether whipsaw was detected")
    severity: float = Field(..., description="Severity of the whipsaw pattern")
    pattern: str = Field(..., description="Description of the whipsaw pattern")
    recommended_action: str = Field(..., description="Recommended action")


class MonitorResponse(BaseModel):
    """Response from position monitoring."""
    positions: List[PositionStatus]
    portfolio_metrics: PortfolioMetrics
    range_breaks: List[RangeBreakAlert]
    whipsaw_detections: List[WhipsawAlert]
    total_alerts: int
    critical_alerts: int
    recommended_actions: List[str]
    average_apr: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============= V2 Enhanced Models =============

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


# ============= Legacy/Compatibility Models =============

class OpportunitiesRequest(BaseModel):
    """Request for pool opportunities (legacy)."""
    executor_address: str
    available_capital: float = Field(..., gt=0)
    min_apr: Optional[float] = Field(None, ge=0)
    max_positions: Optional[int] = Field(None, ge=1, le=20)


class MonitorPositionsRequest(BaseModel):
    """Request for monitoring positions (legacy)."""
    user_address: str  # This is what strategy_service expects
    executor_address: Optional[str] = None  # Keep for compatibility
    check_all_positions: bool = True
    position_ids: Optional[List[int]] = None


class RangeBreakRequest(BaseModel):
    """Request for range break detection (legacy)."""
    token_id: int
    executor_address: str


class WhipsawDetectionRequest(BaseModel):
    """Request for whipsaw detection (legacy)."""
    token_id: int
    executor_address: str
    time_window_hours: Optional[float] = Field(24.0, gt=0)


class RangeBreakMetrics(BaseModel):
    """Metrics for range break analysis."""
    break_detected: bool
    break_type: Optional[Literal["upward", "downward"]] = None
    current_price: float
    range_lower: float
    range_upper: float
    break_percentage: float
    time_since_break_hours: Optional[float] = None
    reversal_probability: float
    false_break_probability: float


class AlternativeStrategy(BaseModel):
    """Alternative strategy suggestion."""
    strategy_type: Literal["widen_range", "narrow_range", "shift_range", "exit_position"]
    description: str
    expected_improvement_percentage: float
    implementation_difficulty: Literal["easy", "medium", "hard"]
    estimated_gas_cost_usd: float


class RebalanceRecommendation(BaseModel):
    """Recommendation for position rebalancing."""
    should_rebalance: bool
    urgency: Literal["low", "medium", "high", "critical"]
    new_range: Optional[RangeParameters] = None
    expected_apr_improvement: float
    cost_benefit_ratio: float
    reasoning: str


class PortfolioImprovement(BaseModel):
    """Suggestions for portfolio improvement."""
    action: Literal["add_position", "remove_position", "rebalance_allocation"]
    target_pool: Optional[str] = None
    target_position_id: Optional[int] = None
    allocation_change_usdc: float
    expected_portfolio_apr_change: float
    reasoning: str


# ============= Response Aggregators =============

class OpportunitiesResponse(BaseModel):
    """Response containing filtered and ranked opportunities."""
    opportunities: List[PoolOpportunity]
    total_opportunities_found: int
    filters_applied: List[str]
    portfolio_metrics: Optional[PortfolioMetrics] = None
    recommended_allocation: Dict[str, float] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class MonitorPositionsResponse(BaseModel):
    """Response from monitoring multiple positions."""
    positions: List[PositionStatus]
    alerts: List[Dict[str, Any]]
    portfolio_metrics: PortfolioMetrics
    risk_analysis: RiskAnalysis
    recommended_actions: List[str]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class RangeBreakResponse(BaseModel):
    """Response for range break analysis."""
    position_status: PositionStatus
    range_break_metrics: RangeBreakMetrics
    rebalance_recommendation: RebalanceRecommendation
    alternative_strategies: List[AlternativeStrategy]
    risk_analysis: RiskAnalysis
    optimal_timing: OptimalTiming
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WhipsawDetectionResponse(BaseModel):
    """Response for whipsaw detection."""
    whipsaw_detected: bool
    whipsaw_count: int
    false_signals: int
    time_window_hours: float
    confidence_score: float = Field(..., ge=0, le=100)
    price_oscillations: List[Dict[str, Any]]
    recommended_action: Literal["wait", "widen_range", "exit"]
    alternative_actions: List[AlternativeAction]
    reasoning: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============= Backwards Compatibility Exports =============
# These allow importing from this module directly for backwards compatibility

__all__ = [
    # Base models
    'ErrorDetail',
    'ErrorResponse',
    'RangeParameters',
    'RangeStatus',
    'RiskMetrics',
    'SlippageInfo',
    'ExecutionParams',
    
    # Pool & Position
    'PoolInfo',
    'PositionStatus',
    'PoolOpportunity',
    
    # Portfolio & Analysis
    'PortfolioMetrics',
    'RiskAnalysis',
    'OptimalTiming',
    'AlternativeAction',
    
    # V2 Models
    'AnalyzeEntryData',
    'AnalyzeExitData',
    'AnalyzeSlippageData',
    'AnalyzeSwitchData',
    'AnalyzeRequest',
    
    # Screen Models
    'ScreenRequest',
    'ScreenResponse',
    
    # Monitor Models
    'MonitorRequest',
    'RangeBreakAlert',
    'WhipsawAlert',
    'MonitorResponse',
    
    # Enhanced Models
    'UserContext',
    'EntryAnalysis',
    'ExitRecommendation',
    'SwitchRecommendation',
    'ImmediateAction',
    'ScheduledAction',
    'CapitalAllocation',
    'DecisionMatrix',
    'RiskAlert',
    'EnhancedScreenRequest',
    'EnhancedScreenResponse',
    
    # Legacy Models
    'OpportunitiesRequest',
    'MonitorPositionsRequest',
    'RangeBreakRequest',
    'WhipsawDetectionRequest',
    'RangeBreakMetrics',
    'AlternativeStrategy',
    'RebalanceRecommendation',
    'PortfolioImprovement',
    'OpportunitiesResponse',
    'MonitorPositionsResponse',
    'RangeBreakResponse',
    'WhipsawDetectionResponse',
]
