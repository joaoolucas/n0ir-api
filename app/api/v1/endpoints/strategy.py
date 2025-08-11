"""
Strategy API endpoints for the n0ir DeFi strategy module.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends
import logging

from app.core.strategy_service import strategy_service
from app.schemas.strategy import (
    OpportunitiesRequest, OpportunitiesResponse,
    AnalyzeEntryRequest, AnalyzeEntryResponse,
    MonitorPositionsRequest, MonitorPositionsResponse,
    RangeBreakRequest, RangeBreakResponse,
    ExitAnalysisRequest, ExitAnalysisResponse,
    WhipsawDetectionRequest, WhipsawDetectionResponse,
    PortfolioRebalanceRequest, PortfolioRebalanceResponse,
    SlippageCalculationRequest, SlippageCalculationResponse,
    RiskAssessmentResponse, PerformanceAnalyticsResponse,
    ErrorResponse, ErrorDetail
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strategy", tags=["strategy"])


@router.post(
    "/opportunities",
    response_model=OpportunitiesResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Bad request"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def get_pool_opportunities(request: OpportunitiesRequest) -> OpportunitiesResponse:
    """
    Find and rank pool opportunities based on the quantitative scoring model.
    
    Analyzes whitelisted pools and returns ranked opportunities based on:
    - Composite scoring model (fee efficiency, volume, liquidity, etc.)
    - Risk-adjusted returns
    - Position sizing recommendations
    - Optimal range calculations
    """
    try:
        return await strategy_service.find_opportunities(request)
    except Exception as e:
        logger.error(f"Error finding opportunities: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "STRATEGY_ERROR",
                    "message": "Failed to find opportunities",
                    "details": {"error": str(e)}
                }
            }
        )


@router.post(
    "/analyze/entry",
    response_model=AnalyzeEntryResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Bad request"},
        404: {"model": ErrorResponse, "description": "Pool not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def analyze_position_entry(request: AnalyzeEntryRequest) -> AnalyzeEntryResponse:
    """
    Analyze a potential position entry with detailed risk assessment.
    
    Provides:
    - Entry recommendation (should_enter)
    - Confidence score
    - Dynamic slippage calculation
    - Risk analysis (VaR, portfolio impact)
    - Optimal range parameters
    - Warning flags
    """
    try:
        return await strategy_service.analyze_entry(request)
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "POOL_NOT_FOUND",
                    "message": str(e)
                }
            }
        )
    except Exception as e:
        logger.error(f"Error analyzing entry: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "ANALYSIS_ERROR",
                    "message": "Failed to analyze entry",
                    "details": {"error": str(e)}
                }
            }
        )


@router.post(
    "/monitor",
    response_model=MonitorPositionsResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Bad request"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def monitor_active_positions(request: MonitorPositionsRequest) -> MonitorPositionsResponse:
    """
    Monitor active positions and return recommended actions.
    
    Monitors:
    - Range status (in/out of range)
    - Health scores
    - Current APR performance
    - Accumulated fees and rewards
    - Portfolio-level metrics
    
    Returns specific action recommendations for each position.
    """
    try:
        return await strategy_service.monitor_positions(request)
    except Exception as e:
        logger.error(f"Error monitoring positions: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "MONITORING_ERROR",
                    "message": "Failed to monitor positions",
                    "details": {"error": str(e)}
                }
            }
        )


@router.post(
    "/range-break",
    response_model=RangeBreakResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Bad request"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def handle_range_break(request: RangeBreakRequest) -> RangeBreakResponse:
    """
    Get immediate action recommendations when a position breaks its range.
    
    Analyzes:
    - Break severity (mild to critical)
    - Reversal probability (70% for upward breaks)
    - Expected loss if reversal occurs
    
    Returns:
    - Action recommendation (emergency_exit, rebalance, monitor)
    - Execution parameters (slippage, deadline)
    - Risk metrics
    """
    try:
        return await strategy_service.handle_range_break(request)
    except Exception as e:
        logger.error(f"Error handling range break: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "RANGE_BREAK_ERROR",
                    "message": "Failed to handle range break",
                    "details": {"error": str(e)}
                }
            }
        )


@router.post(
    "/analyze/exit",
    response_model=ExitAnalysisResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Bad request"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def analyze_position_exit(request: ExitAnalysisRequest) -> ExitAnalysisResponse:
    """
    Analyze whether and how to exit a position.
    
    Analyzes:
    - Exit reason (manual, stop_loss, take_profit, range_break)
    - Current ROI including fees and rewards
    - Optimal exit timing
    - Expected slippage and proceeds
    
    Returns exit strategy (immediate, graduated, or wait).
    """
    try:
        return await strategy_service.analyze_exit(request)
    except Exception as e:
        logger.error(f"Error analyzing exit: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "EXIT_ANALYSIS_ERROR",
                    "message": "Failed to analyze exit",
                    "details": {"error": str(e)}
                }
            }
        )


@router.post(
    "/whipsaw/detect",
    response_model=WhipsawDetectionResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Bad request"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def detect_whipsaw_pattern(request: WhipsawDetectionRequest) -> WhipsawDetectionResponse:
    """
    Detect and analyze whipsaw patterns in positions.
    
    Identifies:
    - High frequency reversals
    - Expanding volatility patterns
    - Pattern severity (0-100)
    
    Returns recommendations:
    - Exit, reduce position, or widen range
    - Alternative strategies
    """
    try:
        return await strategy_service.detect_whipsaw(request)
    except Exception as e:
        logger.error(f"Error detecting whipsaw: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "WHIPSAW_DETECTION_ERROR",
                    "message": "Failed to detect whipsaw",
                    "details": {"error": str(e)}
                }
            }
        )


@router.post(
    "/portfolio/rebalance",
    response_model=PortfolioRebalanceResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Bad request"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def rebalance_portfolio(request: PortfolioRebalanceRequest) -> PortfolioRebalanceResponse:
    """
    Get portfolio-level rebalancing recommendations.
    
    Analyzes:
    - Concentration risk
    - Underperforming positions
    - Diversification opportunities
    
    Returns:
    - Specific actions (close, reduce, open positions)
    - Expected portfolio improvements (APR, risk, Sharpe)
    """
    try:
        return await strategy_service.rebalance_portfolio(request)
    except Exception as e:
        logger.error(f"Error rebalancing portfolio: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "REBALANCE_ERROR",
                    "message": "Failed to rebalance portfolio",
                    "details": {"error": str(e)}
                }
            }
        )


@router.post(
    "/slippage/calculate",
    response_model=SlippageCalculationResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Bad request"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def calculate_slippage(request: SlippageCalculationRequest) -> SlippageCalculationResponse:
    """
    Calculate dynamic slippage for a specific trade.
    
    Factors:
    - Pair classification (stable, semi-volatile, volatile, memecoin)
    - Position size impact on TVL
    - Current volatility
    - Entry vs exit action
    
    Returns breakdown of slippage components and total estimate.
    """
    try:
        return await strategy_service.calculate_slippage(request)
    except Exception as e:
        logger.error(f"Error calculating slippage: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "SLIPPAGE_CALCULATION_ERROR",
                    "message": "Failed to calculate slippage",
                    "details": {"error": str(e)}
                }
            }
        )


@router.get(
    "/risk/assessment",
    response_model=RiskAssessmentResponse,
    responses={
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def get_risk_assessment() -> RiskAssessmentResponse:
    """
    Get current portfolio risk metrics and warnings.
    
    Provides:
    - Portfolio VaR (1-day and 7-day at 95% confidence)
    - Concentration risk metrics
    - Range break risk assessment
    - Overall risk score (0-100)
    - Actionable warnings
    """
    try:
        return await strategy_service.assess_risk()
    except Exception as e:
        logger.error(f"Error assessing risk: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "RISK_ASSESSMENT_ERROR",
                    "message": "Failed to assess risk",
                    "details": {"error": str(e)}
                }
            }
        )


@router.get(
    "/performance",
    response_model=PerformanceAnalyticsResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid period"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def get_performance_analytics(
    period: str = Query(
        default="24h",
        description="Time period for analytics",
        regex="^(24h|7d|30d|all)$"
    ),
    executor_address: Optional[str] = Query(
        default=None,
        description="Executor address to filter by"
    )
) -> PerformanceAnalyticsResponse:
    """
    Get detailed performance metrics for strategy evaluation.
    
    Metrics include:
    - Returns (PnL, ROI, APR)
    - Fee breakdown (trading fees, rewards, costs)
    - Risk metrics (Sharpe ratio, max drawdown, win rate)
    - Execution quality (avg slippage, success rates)
    
    Supports filtering by time period and executor address.
    """
    try:
        return await strategy_service.get_performance_analytics(period, executor_address)
    except Exception as e:
        logger.error(f"Error getting performance analytics: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "PERFORMANCE_ANALYTICS_ERROR",
                    "message": "Failed to get performance analytics",
                    "details": {"error": str(e)}
                }
            }
        )