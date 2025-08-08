from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Path
from app.schemas.pools import (
    PoolData,
    PoolsListResponse,
    PoolBatchRequest,
    PoolStatsResponse
)
from app.schemas.common import ErrorResponse
from app.core.pools_service import pools_service

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
    type: str = Query("all", pattern="^(stable|volatile|all)$", description="Pool type filter"),
    min_tvl: float = Query(1000, ge=0, description="Minimum TVL in USD"),
    min_volume_24h: float = Query(10000, ge=0, description="Minimum 24h volume in USD"),
    min_apr: float = Query(0, ge=0, description="Minimum APR percentage"),
    blacklist: Optional[str] = Query(None, description="Comma-separated token addresses to exclude"),
    limit: int = Query(100, ge=1, le=500, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    sort_by: str = Query("apr", pattern="^(apr|tvl|volume)$", description="Sort field"),
    sort_order: str = Query("desc", pattern="^(desc|asc)$", description="Sort order")
):
    """
    Get pools with filters and pagination.
    
    Returns a list of concentrated liquidity pools matching the specified criteria.
    """
    try:
        # Parse blacklist
        blacklist_tokens = []
        if blacklist:
            blacklist_tokens = [addr.strip() for addr in blacklist.split(",")]
        
        # Get pools from service
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
        
        return result
        
    except ValueError as e:
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
    address: str = Path(..., description="Pool contract address", pattern="^0x[a-fA-F0-9]{40}$")
):
    """
    Get detailed information for a specific pool.
    
    Returns comprehensive data about a single concentrated liquidity pool.
    """
    try:
        pool = await pools_service.get_pool(address)
        return pool
        
    except Exception as e:
        if "not found" in str(e).lower():
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
async def get_pools_batch(request: PoolBatchRequest):
    """
    Fetch multiple pools by their addresses.
    
    Returns data for multiple pools in a single request. Non-existent pools are omitted from the response.
    """
    try:
        pools = await pools_service.get_pools_batch(request.addresses)
        return pools
        
    except Exception as e:
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
    address: str = Path(..., description="Pool contract address", pattern="^0x[a-fA-F0-9]{40}$"),
    period: str = Query("24h", pattern="^(1h|24h|7d|30d)$", description="Time period for statistics")
):
    """
    Get statistics for a specific pool.
    
    Returns volume, fees, and other statistics for the specified time period.
    """
    try:
        stats = await pools_service.get_pool_stats(address, period)
        return stats
        
    except Exception as e:
        if "not found" in str(e).lower():
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