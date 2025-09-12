"""Analytics API endpoints for hedge and position performance."""

from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Query, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.hedge import HedgeSummaryResponse, HedgePerformanceResponse
from app.schemas.common import ErrorResponse
from app.services.hedge_service import HedgeService
from app.core.logger import logger
from app.database.session import get_db

router = APIRouter()


@router.get(
    "/hedges/summary",
    response_model=HedgeSummaryResponse,
    responses={
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def get_hedges_summary(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Get summary statistics for all hedged positions.
    
    Returns aggregate data including:
    - Total hedged positions count
    - Active hedges count
    - Total value locked in hedges
    - Total P&L across all hedges
    - Average leverage
    - Positions at risk
    - Market breakdown
    """
    logger.info(f"GET /analytics/hedges/summary - IP: {request.client.host}")
    
    try:
        hedge_service = HedgeService(db)
        stats = await hedge_service.get_hedge_statistics()
        
        return HedgeSummaryResponse(
            total_hedged_positions=stats["total_positions"],
            active_hedges=stats["active_hedges"],
            total_hedge_value_usdc=stats["total_value"],
            total_pnl_usdc=stats["total_pnl"],
            average_leverage=stats["avg_leverage"],
            total_funding_paid=stats["total_funding"],
            at_risk_positions=stats["at_risk_count"],
            markets={
                "ETH-USD": stats["eth_positions"],
                "BTC-USD": stats["btc_positions"]
            }
        )
        
    except Exception as e:
        logger.error(f"Error fetching hedge summary: {e!r}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to fetch hedge summary",
                    "details": {"error": str(e)}
                }
            }
        )


@router.get(
    "/hedges/performance",
    response_model=HedgePerformanceResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid parameters"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def get_hedge_performance(
    request: Request,
    timeframe: str = Query("24h", description="Timeframe for performance calculation", regex="^(1h|24h|7d|30d|all)$"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get hedge performance metrics comparing hedged vs unhedged positions.
    
    Analyzes:
    - Average returns for hedged vs unhedged positions
    - Total P&L comparison
    - Hedge effectiveness ratio
    - Volatility reduction percentage
    
    Timeframes: 1h, 24h, 7d, 30d, all
    """
    logger.info(f"GET /analytics/hedges/performance - IP: {request.client.host} - Timeframe: {timeframe}")
    
    try:
        hedge_service = HedgeService(db)
        perf = await hedge_service.calculate_hedge_performance(timeframe)
        
        return HedgePerformanceResponse(
            timeframe=timeframe,
            hedged_positions={
                "count": perf["hedged_count"],
                "avg_return": perf["hedged_avg_return"],
                "total_pnl": perf["hedged_pnl"]
            },
            unhedged_positions={
                "count": perf["unhedged_count"],
                "avg_return": perf["unhedged_avg_return"],
                "total_pnl": perf["unhedged_pnl"]
            },
            hedge_effectiveness=perf["effectiveness_ratio"],
            volatility_reduction=perf["volatility_reduction"]
        )
        
    except ValueError as e:
        logger.warning(f"Invalid timeframe parameter: {timeframe}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_TIMEFRAME",
                    "message": str(e),
                    "details": {"timeframe": timeframe}
                }
            }
        )
    except Exception as e:
        logger.error(f"Error calculating hedge performance: {e!r}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to calculate hedge performance",
                    "details": {"error": str(e)}
                }
            }
        )


@router.get(
    "/positions/performance",
    responses={
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def get_positions_performance(
    request: Request,
    user_id: str = Query(None, description="Filter by user ID"),
    pool_address: str = Query(None, description="Filter by pool address"),
    timeframe: str = Query("24h", description="Timeframe", regex="^(1h|24h|7d|30d|all)$"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get performance metrics for positions with optional filters.
    
    Returns:
    - Total positions
    - Average P&L
    - Best/worst performers
    - Performance by pool
    """
    logger.info(f"GET /analytics/positions/performance - IP: {request.client.host}")
    
    try:
        # This would be implemented with actual position performance logic
        # For now, return a placeholder response
        return {
            "timeframe": timeframe,
            "total_positions": 0,
            "filters": {
                "user_id": user_id,
                "pool_address": pool_address
            },
            "metrics": {
                "average_pnl_usd": 0,
                "total_pnl_usd": 0,
                "best_performer": None,
                "worst_performer": None
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching positions performance: {e!r}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to fetch positions performance",
                    "details": {"error": str(e)}
                }
            }
        )


@router.get(
    "/monitoring/alerts",
    responses={
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def get_monitoring_alerts(
    request: Request,
    severity: str = Query(None, description="Filter by severity", regex="^(info|warning|critical)$"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current monitoring alerts for hedged positions.
    
    Returns alerts for:
    - Liquidation risks
    - Low health positions
    - High funding costs
    - Rebalancing needs
    """
    logger.info(f"GET /analytics/monitoring/alerts - IP: {request.client.host}")
    
    try:
        hedge_service = HedgeService(db)
        alerts = await hedge_service.monitor_hedge_health()
        
        # Filter by severity if provided
        if severity:
            alerts = [a for a in alerts if a.get("severity") == severity]
        
        return {
            "alerts": alerts,
            "total": len(alerts),
            "critical_count": sum(1 for a in alerts if a.get("severity") == "critical"),
            "warning_count": sum(1 for a in alerts if a.get("severity") == "warning"),
            "info_count": sum(1 for a in alerts if a.get("severity") == "info")
        }
        
    except Exception as e:
        logger.error(f"Error fetching monitoring alerts: {e!r}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to fetch monitoring alerts",
                    "details": {"error": str(e)}
                }
            }
        )