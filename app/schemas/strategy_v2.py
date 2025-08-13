"""
Pydantic schemas for the consolidated strategy module v2.
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


# ============= Unified Analyze Models =============

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


class AnalyzeRequest(BaseModel):
    """Unified request for trade analysis."""
    action: Literal["entry", "exit", "slippage"] = Field(..., description="Type of analysis to perform")
    
    # Action-specific data
    entry_data: Optional[AnalyzeEntryData] = None
    exit_data: Optional[AnalyzeExitData] = None
    slippage_data: Optional[AnalyzeSlippageData] = None
    
    @property
    def pool_address(self) -> Optional[str]:
        """Get pool address from appropriate data field."""
        if self.action == "entry" and self.entry_data:
            return self.entry_data.pool_address
        elif self.action == "slippage" and self.slippage_data:
            return self.slippage_data.pool_address
        return None
    
    @property
    def amount_usdc(self) -> Optional[float]:
        """Get amount from appropriate data field."""
        if self.action == "entry" and self.entry_data:
            return self.entry_data.amount_usdc
        elif self.action == "slippage" and self.slippage_data:
            return self.slippage_data.amount_usdc
        return None


class AnalyzeEntryResponse(BaseModel):
    """Response for entry analysis."""
    should_enter: bool
    confidence_score: float = Field(..., ge=0, le=100)
    slippage: SlippageInfo
    risk_analysis: RiskAnalysis
    optimal_range: RangeParameters
    effective_apr: float
    apr_efficiency: float = Field(..., ge=0, le=100)
    warnings: List[str] = Field(default_factory=list)


class AnalyzeExitResponse(BaseModel):
    """Response for exit analysis."""
    should_exit: bool
    exit_strategy: Literal["immediate", "graduated", "wait"]
    optimal_timing: OptimalTiming
    slippage_estimate: float
    expected_proceeds: float
    roi_percentage: float
    tax_implications: Optional[str] = None


class AnalyzeSlippageResponse(BaseModel):
    """Response for slippage analysis."""
    base_slippage: float
    size_impact: float
    volatility_adjustment: float
    total_slippage: float
    max_recommended: float
    pair_classification: Literal["stable", "semi-volatile", "volatile", "memecoin"]


class AnalyzeResponse(BaseModel):
    """Unified response for trade analysis."""
    action: Literal["entry", "exit", "slippage"]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Action-specific responses
    entry_response: Optional[AnalyzeEntryResponse] = None
    exit_response: Optional[AnalyzeExitResponse] = None
    slippage_response: Optional[AnalyzeSlippageResponse] = None


# ============= Enhanced Monitor Models =============

class RangeBreakAlert(BaseModel):
    """Alert for range break detection."""
    token_id: int
    pool_address: str
    severity: float = Field(..., ge=0, le=100)
    action: Literal["emergency_exit", "partial_exit", "rebalance", "monitor"]
    urgency: Literal["low", "medium", "high", "critical"]
    reversal_probability: float = Field(..., ge=0, le=1)
    expected_loss_if_reversal: float


class WhipsawAlert(BaseModel):
    """Alert for whipsaw pattern detection."""
    token_id: int
    pool_address: str
    whipsaw_detected: bool
    severity: float = Field(..., ge=0, le=100)
    pattern: Literal["high_frequency_reversal", "expanding_volatility", "none"]
    recommended_action: Literal["exit", "reduce", "widen_range", "monitor"]


class MonitorRequest(BaseModel):
    """Enhanced request for position monitoring."""
    user_address: str = Field(..., description="User wallet address to monitor")
    
    # Optional filters for specific checks
    check_range_breaks: bool = Field(default=True, description="Check for range breaks")
    check_whipsaw: bool = Field(default=True, description="Check for whipsaw patterns")
    token_ids: Optional[List[int]] = Field(default=None, description="Filter specific positions by token ID")


class MonitorResponse(BaseModel):
    """Enhanced response for position monitoring."""
    positions: List[PositionStatus]
    portfolio_metrics: PortfolioMetrics
    
    # Additional monitoring data
    range_breaks: List[RangeBreakAlert] = Field(default_factory=list)
    whipsaw_detections: List[WhipsawAlert] = Field(default_factory=list)
    
    # Summary
    total_alerts: int = Field(default=0)
    critical_alerts: int = Field(default=0)
    recommended_actions: List[str] = Field(default_factory=list)
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============= Screen Models (renamed opportunities) =============

class ScreenRequest(BaseModel):
    """Request for screening pool opportunities."""
    executor_address: str
    available_capital: float = Field(..., gt=0)


class ScreenResponse(BaseModel):
    """Response for pool screening."""
    opportunities: List[PoolOpportunity]
    optimal_position_count: int = Field(..., description="Recommended total number of positions")
    minimum_position_size: float = Field(..., description="Minimum viable position size in USDC")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============= Portfolio Models =============

class PortfolioAction(BaseModel):
    """Base class for portfolio actions."""
    action: Literal["rebalance", "optimize", "analyze"]


class PortfolioRebalanceRequest(BaseModel):
    """Request for portfolio rebalancing."""
    user_address: str = Field(..., description="User wallet address")
    available_capital: float = Field(default=0, ge=0)


class PortfolioResponse(BaseModel):
    """Unified response for portfolio operations."""
    action: Literal["rebalance", "optimize", "analyze"]
    recommendations: List[RebalanceRecommendation]
    expected_improvement: PortfolioImprovement
    is_full_rebalance: bool = Field(default=False)
    timestamp: datetime = Field(default_factory=datetime.utcnow)