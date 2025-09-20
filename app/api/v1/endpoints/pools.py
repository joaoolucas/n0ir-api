from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Path, Request
from app.schemas.pools import (
    PoolData,
    PoolsListResponse,
    PoolBatchRequest,
    PoolStatsResponse,
    MedianAPRResponse
)
from app.schemas.common import ErrorResponse
from app.core.pools_service import pools_service
from app.core.logger import logger
from statistics import median
from app.core.strategy_service import WHITELISTED_POOLS

router = APIRouter()


# GET /pools endpoint removed - use specific pool lookup instead

@router.get(
    "/pools/{address}",
    response_model=PoolData,
    responses={
        404: {"model": ErrorResponse, "description": "Pool not found"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def get_pool(
    request: Request,
    address: str = Path(..., description="Pool contract address", pattern="^0x[a-fA-F0-9]{40}$")
):
    """
    Get detailed information for a specific pool.
    
    Returns comprehensive data about a single concentrated liquidity pool.
    """
    logger.info(f"GET /pools/{address} - IP: {request.client.host}")
    try:
        pool = await pools_service.get_pool(address)
        logger.info(f"Successfully fetched pool {address}")
        return pool
        
    except Exception as e:
        if "not found" in str(e).lower():
            logger.warning(f"Pool not found: {address}")
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "POOL_NOT_FOUND",
                        "message": f"Pool with address {address} not found",
                        "details": {}
                    }
                }
            )
        logger.error(f"Error fetching pool {address}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to fetch pool",
                    "details": {"error": str(e)}
                }
            }
        )




@router.get(
    "/pools/whitelist/median-apr",
    response_model=MedianAPRResponse,
    responses={
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def get_whitelist_median_apr(request: Request) -> MedianAPRResponse:
    """
    Median APR for whitelisted pools.

    Computes the median of APRs across pools listed in the global whitelist.
    """
    logger.info(f"GET /pools/whitelist/median-apr - IP: {request.client.host}")
    try:
        addresses = list(WHITELISTED_POOLS)
        if not addresses:
            return MedianAPRResponse(median_apr=0.0)

        pools = await pools_service.get_pools_batch(addresses)
        aprs = [float(p.get('apr', 0) or 0) for p in pools if p]

        if not aprs:
            return MedianAPRResponse(median_apr=0.0)

        med = float(median(aprs))
        return MedianAPRResponse(median_apr=med)
    except Exception as e:
        logger.error(f"Error computing whitelist median APR: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to compute median APR",
                    "details": {"error": str(e)}
                }
            }
        )
