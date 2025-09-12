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


@router.get(
    "/pools",
    response_model=PoolsListResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Bad Request"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def get_pools(
    request: Request,
    type: str = Query("all", pattern="^(stable|volatile|all)$", description="Pool type filter"),
    min_tvl: float = Query(1000, ge=0, description="Minimum TVL in USD"),
    min_volume_24h: float = Query(1000, ge=0, description="Minimum 24h volume in USD"),
    min_apr: float = Query(0, ge=0, description="Minimum APR percentage"),
    blacklist: Optional[str] = Query(None, description="Comma-separated token addresses to exclude"),
    limit: int = Query(100, ge=1, le=500, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    sort_by: str = Query("apr", pattern="^(apr|tvl|volume)$", description="Sort field"),
    sort_order: str = Query("desc", pattern="^(desc|asc)$", description="Sort order"),
    full_data: bool = Query(False, description="Fetch full data including prices and APR (slower)"),
    include_effective_apr: bool = Query(False, description="Calculate and include effective APR for different range widths")
):
    """
    Get pools with filters and pagination.
    
    Returns a list of concentrated liquidity pools matching the specified criteria.
    """
    logger.info(f"GET /pools - IP: {request.client.host} - Params: type={type}, min_tvl={min_tvl}, full_data={full_data}")
    try:
        # Parse blacklist
        blacklist_tokens = []
        if blacklist:
            blacklist_tokens = [addr.strip() for addr in blacklist.split(",")]
        
        # Get pools from service - use fast or full method
        if full_data:
            result = await pools_service.get_pools_full(
                pool_type=type,
                min_tvl=min_tvl,
                min_volume_24h=min_volume_24h,
                min_apr=min_apr,
                blacklist=blacklist_tokens,
                limit=limit,
                offset=offset,
                sort_by=sort_by,
                sort_order=sort_order,
                include_effective_apr=include_effective_apr
            )
        else:
            result = await pools_service.get_pools(
                pool_type=type,
                min_tvl=min_tvl,
                min_volume_24h=min_volume_24h,
                min_apr=min_apr,
                blacklist=blacklist_tokens,
                limit=limit,
                offset=offset,
                sort_by=sort_by,
                sort_order=sort_order
            )
        
        logger.info(f"Successfully fetched {result.get('pagination', {}).get('total', 0)} pools")
        return result
        
    except ValueError as e:
        logger.warning(f"Invalid parameters for /pools: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_PARAMETERS",
                    "message": str(e),
                    "details": {}
                }
            }
        )
    except Exception as e:
        logger.error(f"Error fetching pools: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to fetch pools",
                    "details": {"error": str(e)}
                }
            }
        )


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
