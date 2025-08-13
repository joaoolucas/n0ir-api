"""
Consolidated strategy endpoints.
Reduces 8 endpoints to 4 logical groups for better API design.
"""
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse

from app.schemas.strategy_v2 import (
    ScreenRequest,
    ScreenResponse,
    AnalyzeRequest,
    AnalyzeResponse,
    AnalyzeEntryResponse,
    AnalyzeExitResponse,
    AnalyzeSlippageResponse,
    MonitorRequest,
    MonitorResponse,
    RangeBreakAlert,
    WhipsawAlert,
    PortfolioRebalanceRequest,
    PortfolioResponse,
    ErrorResponse,
    ErrorDetail
)

from app.schemas.strategy import (
    OpportunitiesRequest,
    AnalyzeEntryRequest,
    ExitAnalysisRequest,
    SlippageCalculationRequest,
    MonitorPositionsRequest,
    RangeBreakRequest,
    WhipsawDetectionRequest,
    RebalanceRecommendation,
    PortfolioImprovement
)

from app.core.strategy_service import strategy_service
from app.core.logger import logger

router = APIRouter(
    prefix="/strategy",
    tags=["Strategy"],
    responses={
        400: {"model": ErrorResponse, "description": "Bad Request"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)


@router.post(
    "/screen",
    response_model=ScreenResponse,
    summary="Screen pool opportunities",
    description="Find and rank pool opportunities based on quantitative scoring model (formerly /opportunities)"
)
async def screen_opportunities(request: ScreenRequest) -> ScreenResponse:
    """
    Screen pools for investment opportunities.
    
    This endpoint:
    - Fetches whitelisted pools
    - Calculates safety scores and allocation weights
    - Excludes pools where user already has positions
    - Returns ranked opportunities with recommended allocations
    """
    try:
        # Convert to v1 request format
        v1_request = OpportunitiesRequest(
            executor_address=request.executor_address,
            available_capital=request.available_capital
        )
        
        # Call existing service method
        v1_response = await strategy_service.find_opportunities(v1_request)
        
        # Convert to v2 response format
        return ScreenResponse(
            opportunities=v1_response.opportunities,
            optimal_position_count=v1_response.optimal_position_count,
            minimum_position_size=v1_response.minimum_position_size,
            timestamp=v1_response.timestamp
        )
    except Exception as e:
        logger.error(f"Error screening opportunities: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    summary="Unified trade analysis",
    description="Analyze entry, exit, or slippage for trading decisions"
)
async def analyze_trade(request: AnalyzeRequest) -> AnalyzeResponse:
    """
    Unified endpoint for trade analysis.
    
    Supports three action types:
    - entry: Analyze potential position entry
    - exit: Analyze position exit strategy
    - slippage: Calculate expected slippage
    """
    try:
        if request.action == "entry":
            if not request.entry_data:
                raise HTTPException(400, "entry_data required for entry analysis")
            
            # Convert to v1 request
            v1_request = AnalyzeEntryRequest(
                pool_address=request.entry_data.pool_address,
                amount_usdc=request.entry_data.amount_usdc
            )
            
            # Call existing service
            v1_response = await strategy_service.analyze_entry(v1_request)
            
            # Build v2 response
            return AnalyzeResponse(
                action="entry",
                entry_response=AnalyzeEntryResponse(
                    should_enter=v1_response.should_enter,
                    confidence_score=v1_response.confidence_score,
                    slippage=v1_response.slippage,
                    risk_analysis=v1_response.risk_analysis,
                    optimal_range=v1_response.optimal_range,
                    effective_apr=v1_response.effective_apr,
                    apr_efficiency=v1_response.apr_efficiency,
                    warnings=v1_response.warnings
                )
            )
            
        elif request.action == "exit":
            if not request.exit_data:
                raise HTTPException(400, "exit_data required for exit analysis")
            
            # Convert to v1 request
            v1_request = ExitAnalysisRequest(
                token_id=request.exit_data.token_id,
                exit_reason=request.exit_data.exit_reason
            )
            
            # Call existing service
            v1_response = await strategy_service.analyze_exit(v1_request)
            
            # Build v2 response
            return AnalyzeResponse(
                action="exit",
                exit_response=AnalyzeExitResponse(
                    should_exit=v1_response.should_exit,
                    exit_strategy=v1_response.exit_strategy,
                    optimal_timing=v1_response.optimal_timing,
                    slippage_estimate=v1_response.slippage_estimate,
                    expected_proceeds=v1_response.expected_proceeds,
                    roi_percentage=v1_response.roi_percentage,
                    tax_implications=v1_response.tax_implications
                )
            )
            
        elif request.action == "slippage":
            if not request.slippage_data:
                raise HTTPException(400, "slippage_data required for slippage analysis")
            
            # Convert to v1 request
            v1_request = SlippageCalculationRequest(
                pool_address=request.slippage_data.pool_address,
                action=request.slippage_data.action,
                amount_usdc=request.slippage_data.amount_usdc
            )
            
            # Call existing service
            v1_response = await strategy_service.calculate_slippage(v1_request)
            
            # Build v2 response
            return AnalyzeResponse(
                action="slippage",
                slippage_response=AnalyzeSlippageResponse(
                    base_slippage=v1_response.base_slippage,
                    size_impact=v1_response.size_impact,
                    volatility_adjustment=v1_response.volatility_adjustment,
                    total_slippage=v1_response.total_slippage,
                    max_recommended=v1_response.max_recommended,
                    pair_classification=v1_response.pair_classification
                )
            )
        else:
            raise HTTPException(400, f"Invalid action: {request.action}")
            
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error analyzing trade: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/monitor",
    response_model=MonitorResponse,
    summary="Monitor positions with range break and whipsaw detection",
    description="Comprehensive position monitoring including health checks, range breaks, and whipsaw patterns"
)
async def monitor_positions(request: MonitorRequest) -> MonitorResponse:
    """
    Enhanced position monitoring endpoint.
    
    Consolidates:
    - Position health monitoring
    - Range break detection
    - Whipsaw pattern detection
    
    Returns comprehensive position health metrics in a single call.
    """
    try:
        # Get basic position monitoring
        v1_monitor_request = MonitorPositionsRequest(
            user_address=request.user_address
        )
        v1_monitor_response = await strategy_service.monitor_positions(v1_monitor_request)
        
        # Collect range break alerts if requested
        range_breaks = []
        if request.check_range_breaks:
            for position in v1_monitor_response.positions:
                if position.range_status and not position.range_status.in_range:
                    try:
                        # Check for range break
                        v1_range_request = RangeBreakRequest(
                            token_id=position.token_id
                        )
                        v1_range_response = await strategy_service.handle_range_break(v1_range_request)
                        
                        # Convert to alert
                        range_breaks.append(RangeBreakAlert(
                            token_id=position.token_id,
                            pool_address=position.pool_address,
                            severity=v1_range_response.risk_metrics.break_severity,
                            action=v1_range_response.action,
                            urgency=v1_range_response.urgency,
                            reversal_probability=v1_range_response.risk_metrics.reversal_probability,
                            expected_loss_if_reversal=v1_range_response.risk_metrics.expected_loss_if_reversal
                        ))
                    except Exception as e:
                        logger.warning(f"Could not check range break for token {position.token_id}: {e}")
        
        # Collect whipsaw alerts if requested
        whipsaw_detections = []
        if request.check_whipsaw:
            for position in v1_monitor_response.positions:
                try:
                    # Check for whipsaw
                    v1_whipsaw_request = WhipsawDetectionRequest(
                        token_id=position.token_id
                    )
                    v1_whipsaw_response = await strategy_service.detect_whipsaw(v1_whipsaw_request)
                    
                    if v1_whipsaw_response.whipsaw_detected:
                        # Convert to alert
                        whipsaw_detections.append(WhipsawAlert(
                            token_id=position.token_id,
                            pool_address=position.pool_address,
                            whipsaw_detected=v1_whipsaw_response.whipsaw_detected,
                            severity=v1_whipsaw_response.severity,
                            pattern=v1_whipsaw_response.pattern,
                            recommended_action=v1_whipsaw_response.recommended_action
                        ))
                except Exception as e:
                    logger.warning(f"Could not check whipsaw for token {position.token_id}: {e}")
        
        # Apply token ID filter if provided
        positions = v1_monitor_response.positions
        if request.token_ids:
            positions = [p for p in positions if p.token_id in request.token_ids]
            range_breaks = [r for r in range_breaks if r.token_id in request.token_ids]
            whipsaw_detections = [w for w in whipsaw_detections if w.token_id in request.token_ids]
        
        # Calculate summary metrics
        total_alerts = len(range_breaks) + len(whipsaw_detections)
        critical_alerts = len([r for r in range_breaks if r.urgency == "critical"])
        
        # Collect recommended actions
        recommended_actions = []
        for alert in range_breaks:
            if alert.urgency in ["critical", "high"]:
                recommended_actions.append(f"Token {alert.token_id}: {alert.action}")
        for alert in whipsaw_detections:
            if alert.severity > 70:
                recommended_actions.append(f"Token {alert.token_id}: {alert.recommended_action}")
        
        # Calculate weighted average APR based on position values
        # We need to fetch the actual position data to get their values
        from app.core.positions_service import positions_service
        
        try:
            # Fetch the actual position data which contains current_value_usd
            positions_data = await positions_service.get_positions_by_owner(request.user_address)
            
            # Calculate weighted average APR
            total_value = 0
            weighted_apr_sum = 0
            
            for pos_data in positions_data:
                # Find the corresponding position status with the effective APR
                pos_status = next((p for p in positions if p.token_id == pos_data.id), None)
                if pos_status and pos_data.current_value_usd:
                    position_value = pos_data.current_value_usd
                    total_value += position_value
                    weighted_apr_sum += position_value * pos_status.current_apr
            
            average_apr = weighted_apr_sum / total_value if total_value > 0 else 0
            
        except Exception as e:
            logger.warning(f"Could not calculate weighted average APR: {e}")
            # Fallback to simple average
            average_apr = sum(p.current_apr for p in positions) / len(positions) if positions else 0
        
        # Build consolidated response
        return MonitorResponse(
            positions=positions,
            portfolio_metrics=v1_monitor_response.portfolio_metrics,
            range_breaks=range_breaks,
            whipsaw_detections=whipsaw_detections,
            total_alerts=total_alerts,
            critical_alerts=critical_alerts,
            recommended_actions=recommended_actions,
            average_apr=average_apr
        )
        
    except Exception as e:
        logger.error(f"Error monitoring positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/portfolio",
    response_model=PortfolioResponse,
    summary="Portfolio management operations",
    description="Portfolio-level operations including rebalancing and optimization"
)
async def manage_portfolio(request: PortfolioRebalanceRequest) -> PortfolioResponse:
    """
    Portfolio management endpoint.
    
    Currently supports:
    - Rebalancing recommendations
    - Portfolio optimization
    """
    try:
        # Call existing rebalance service
        v1_response = await strategy_service.rebalance_portfolio(request)
        
        # Convert to v2 response format
        return PortfolioResponse(
            action="rebalance",
            recommendations=v1_response.recommendations,
            expected_improvement=v1_response.expected_portfolio_improvement,
            is_full_rebalance=v1_response.is_full_rebalance
        )
        
    except Exception as e:
        logger.error(f"Error managing portfolio: {e}")
        raise HTTPException(status_code=500, detail=str(e))