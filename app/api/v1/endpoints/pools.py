from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Path, Request
from app.schemas.pools import (
    PoolData,
    PoolsListResponse,
    PoolBatchRequest,
    PoolStatsResponse
)
from app.schemas.common import ErrorResponse
from app.core.pools_service import pools_service
from app.core.logger import logger

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


@router.post(
    "/pools/batch",
    response_model=List[PoolData],
    responses={
        400: {"model": ErrorResponse, "description": "Bad Request"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def get_pools_batch(request: Request, batch_request: PoolBatchRequest):
    """
    Fetch multiple pools by their addresses.
    
    Returns data for multiple pools in a single request. Non-existent pools are omitted from the response.
    """
    logger.info(f"POST /pools/batch - IP: {request.client.host} - Count: {len(batch_request.addresses)}")
    try:
        pools = await pools_service.get_pools_batch(batch_request.addresses)
        logger.info(f"Successfully fetched {len(pools)} pools from batch of {len(batch_request.addresses)}")
        return pools
        
    except Exception as e:
        logger.error(f"Error fetching batch pools: {str(e)}", exc_info=True)
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
    "/pools/{address}/stats",
    response_model=PoolStatsResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Pool not found"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def get_pool_stats(
    request: Request,
    address: str = Path(..., description="Pool contract address", pattern="^0x[a-fA-F0-9]{40}$"),
    period: str = Query("24h", pattern="^(1h|24h|7d|30d)$", description="Time period for statistics")
):
    """
    Get statistics for a specific pool.
    
    Returns volume, fees, and other statistics for the specified time period.
    """
    logger.info(f"GET /pools/{address}/stats - IP: {request.client.host} - Period: {period}")
    try:
        stats = await pools_service.get_pool_stats(address, period)
        logger.info(f"Successfully fetched stats for pool {address}")
        return stats
        
    except Exception as e:
        if "not found" in str(e).lower():
            logger.warning(f"Pool not found for stats: {address}")
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
        logger.error(f"Error fetching pool stats for {address}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to fetch pool statistics",
                    "details": {"error": str(e)}
                }
            }
        )