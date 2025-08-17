"""
Consolidated strategy endpoints.
Reduces 8 endpoints to 4 logical groups for better API design.
"""
from typing import Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse

from app.schemas.strategy_v2 import (
    ScreenRequest,
    MonitorRequest,
    MonitorResponse,
    RangeBreakAlert,
    WhipsawAlert,
    ErrorResponse,
    ErrorDetail
)

from app.schemas.strategy import (
    OpportunitiesRequest,
    MonitorPositionsRequest,
    RangeBreakRequest,
    WhipsawDetectionRequest
)

from app.core.strategy_service import strategy_service
from app.core.logger import logger
from app.core.cooldown_manager import cooldown_manager

# Initialize orchestrator after imports to avoid circular import
from app.core.strategy_orchestrator import StrategyOrchestrator
if not strategy_service.orchestrator:
    strategy_service.orchestrator = StrategyOrchestrator(strategy_service)

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
    summary="Enhanced pool screening with comprehensive analysis",
    description="Find and rank pool opportunities with full entry/exit/switch analysis"
)
async def screen_opportunities(request: ScreenRequest):
    """
    Enhanced screening endpoint with comprehensive analysis.
    
    This endpoint now provides:
    - Pool opportunities filtered by cooldowns
    - Pre-computed entry analyses for top opportunities
    - Exit recommendations for current positions
    - Switch recommendations for portfolio optimization
    - Decision matrix with prioritized actions
    - Risk alerts for portfolio health
    
    Always respects cooldowns and includes full analysis automatically.
    """
    try:
        # Use comprehensive analysis through strategy service
        result = await strategy_service.comprehensive_analysis(
            executor_address=request.executor_address,
            available_capital=request.available_capital
        )
        
        # Import enhanced response model
        from app.schemas.strategy_v2_enhanced import (
            EnhancedScreenResponse,
            UserContext,
            EntryAnalysis,
            ExitRecommendation,
            SwitchRecommendation as EnhancedSwitchRecommendation,
            DecisionMatrix,
            ImmediateAction,
            ScheduledAction,
            CapitalAllocation,
            RiskAlert
        )
        
        # Build user context
        user_context = UserContext(
            executor_address=result.get('user_context', {}).get('executor_address', request.executor_address),
            available_capital=result.get('user_context', {}).get('available_capital', request.available_capital),
            positions_value=result.get('user_context', {}).get('positions_value', 0),
            total_portfolio_value=result.get('user_context', {}).get('total_portfolio_value', request.available_capital),
            active_positions=result.get('user_context', {}).get('active_positions', 0),
            pools_on_cooldown=result.get('user_context', {}).get('pools_on_cooldown', [])
        )
        
        # Convert entry analyses
        entry_analyses = []
        for entry in result.get('entry_analyses', []):
            entry_analyses.append(EntryAnalysis(
                pool_address=entry['pool_address'],
                pool_name=entry.get('pool_name', 'Unknown'),
                confidence_score=entry['confidence_score'],
                optimal_allocation=entry['optimal_allocation'],
                expected_apr=entry['expected_apr'],
                risk_metrics=entry.get('risk_metrics', {}),
                optimal_range=entry.get('optimal_range', {})
            ))
        
        # Convert exit recommendations
        exit_recommendations = []
        for exit in result.get('exit_recommendations', []):
            exit_recommendations.append(ExitRecommendation(
                token_id=exit['token_id'],
                pool_address=exit['pool_address'],
                urgency=exit['urgency'],
                reason=exit['reason'],
                expected_proceeds=exit['expected_proceeds'],
                roi_percentage=exit['roi_percentage'],
                slippage_estimate=exit['slippage_estimate']
            ))
        
        # Convert switch recommendations
        switch_recommendations = []
        for switch in result.get('switch_recommendations', []):
            switch_recommendations.append(EnhancedSwitchRecommendation(
                from_token_id=switch['from_token_id'],
                from_pool=switch['from_pool'],
                to_pool_address=switch['to_pool_address'],
                to_pool_name=switch.get('to_pool_name', 'Unknown'),
                apr_improvement=switch['apr_improvement'],
                net_benefit_after_costs=switch['net_benefit_after_costs'],
                confidence=switch.get('confidence', 0)
            ))
        
        # Convert decision matrix if present
        decision_matrix = None
        if result.get('decision_matrix'):
            dm = result['decision_matrix']
            
            # Convert immediate actions
            immediate_actions = []
            for action in dm.get('immediate_actions', []):
                immediate_actions.append(ImmediateAction(
                    type=action['type'],
                    priority=action['priority'],
                    details=action
                ))
            
            # Convert scheduled actions
            scheduled_actions = []
            for action in dm.get('scheduled_actions', []):
                scheduled_actions.append(ScheduledAction(
                    type=action['type'],
                    schedule=action['schedule'],
                    details=action
                ))
            
            # Build capital allocation
            ca = dm.get('capital_allocation', {})
            capital_allocation = CapitalAllocation(
                recommended_positions=ca.get('recommended_positions', 0),
                allocation_per_position=ca.get('allocation_per_position', 0),
                reserve_capital=ca.get('reserve_capital', 0),
                active_positions=ca.get('active_positions', 0)
            )
            
            decision_matrix = DecisionMatrix(
                immediate_actions=immediate_actions,
                scheduled_actions=scheduled_actions,
                capital_allocation=capital_allocation
            )
        
        # Convert risk alerts
        risk_alerts = []
        for alert in result.get('risk_alerts', []):
            risk_alerts.append(RiskAlert(
                type=alert['type'],
                message=alert['message'],
                severity=alert['severity']
            ))
        
        # Build enhanced response
        return EnhancedScreenResponse(
            user_context=user_context,
            opportunities=result.get('opportunities', []),
            entry_analyses=entry_analyses,
            exit_recommendations=exit_recommendations,
            switch_recommendations=switch_recommendations,
            decision_matrix=decision_matrix,
            risk_alerts=risk_alerts,
            optimal_position_count=result.get('optimal_position_count', 0),
            minimum_position_size=result.get('minimum_position_size', 10),
            timestamp=result.get('timestamp', datetime.utcnow()),
            analysis_timestamp=result.get('analysis_timestamp'),
            cache_hit=result.get('cache_hit', False),
            analysis_time_ms=result.get('analysis_time_ms')
        )
        
    except Exception as e:
        logger.error(f"Error in enhanced screening: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


# DEPRECATED: /analyze endpoint has been removed
# All analysis functionality is now integrated into the /screen endpoint
# which provides comprehensive analysis in a single call


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


@router.get(
    "/cooldowns/{user_address}",
    summary="Get active cooldowns for a user",
    description="Returns all active range break cooldowns preventing re-entry to pools"
)
async def get_cooldowns(user_address: str):
    """
    Get all active cooldowns for a user.
    
    Returns information about pools that are temporarily restricted
    due to recent range break exits.
    """
    try:
        cooldowns = await cooldown_manager.get_user_cooldowns(user_address)
        
        return {
            "user_address": user_address,
            "active_cooldowns": cooldowns,
            "total_cooldowns": len(cooldowns),
            "pools_restricted": [c['pool_address'] for c in cooldowns]
        }
        
    except Exception as e:
        logger.error(f"Error fetching cooldowns: {e}")
        raise HTTPException(status_code=500, detail=str(e))