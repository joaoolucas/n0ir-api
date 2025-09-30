"""Unified Blockchain endpoints for pools, positions, and tokens."""

from typing import List, Optional, Union
from fastapi import APIRouter, HTTPException, Query, Path, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from statistics import median

# Import schemas
from app.schemas.pools import (
    PoolData,
    PoolsListResponse,
    PoolBatchRequest,
    PoolStatsResponse,
    MedianAPRResponse
)
from app.schemas.tokens import (
    TokenInfoResponse,
    TokenPricesResponse
)
from app.schemas.positions import (
    PositionInfo,
    PositionListResponse,
    PositionDetailResponse,
    HedgedPositionCreate,
    HedgedPositionResponse
)
from app.schemas.common import ErrorResponse
from app.schemas.hedge import HedgePositionResponse

# Import services
from app.core.pools_service import pools_service
from app.core.positions_service import positions_service
from app.core.hedge_service import hedge_service
from app.core.logger import logger
from app.database.session import get_db
from app.database.models import Position

# Whitelisted pools (moved from strategy_service)
WHITELISTED_POOLS = {
    "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59",  # WETH/USDC
    "0x4e962bb3889bf030368f56810a9c96b83cb3e778",  # cbBTC/USDC
}

router = APIRouter()


# ============================================================================
# POOLS ENDPOINTS
# ============================================================================

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


# ============================================================================
# POSITIONS ENDPOINTS
# ============================================================================

@router.get(
    "/positions",
    response_model=Union[PositionDetailResponse, PositionListResponse],
    responses={
        400: {"model": ErrorResponse, "description": "Invalid parameters"},
        404: {"model": ErrorResponse, "description": "Position not found"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def get_positions(
    request: Request,
    position_id: Optional[int] = Query(None, description="Get specific position by NFT token ID", ge=1),
    owner: Optional[str] = Query(None, description="Filter by owner wallet address", pattern="^0x[a-fA-F0-9]{40}$"),
    pool: Optional[str] = Query(None, description="Filter by pool address", pattern="^0x[a-fA-F0-9]{40}$"),
    in_range: Optional[bool] = Query(None, description="Filter by in-range status"),
    all_active: bool = Query(False, description="Get all active positions (requires authorization)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get positions with optional filters or a specific position by ID.

    **Unified endpoint for position queries:**
    - Use `position_id` to get a single position with detailed enrichment
    - Use other filters to get multiple positions

    Returns:
    - `PositionDetailResponse` when querying by position_id
    - `PositionListResponse` when using other filters

    Supports filtering by:
    - position_id: Get a specific position by its NFT token ID (returns single position)
    - owner: Wallet address that owns the positions
    - pool: Pool address (future implementation)
    - in_range: Whether positions are in range (future implementation)
    - all_active: Get all active positions across all users (requires authorization)

    At least one parameter must be provided.
    """
    logger.info(f"GET /positions - IP: {request.client.host} - position_id={position_id}, owner={owner}, pool={pool}, in_range={in_range}, all_active={all_active}")

    # Handle single position request by ID
    if position_id is not None:
        try:
            position = await positions_service.get_position_by_id(position_id)

            position_dict = position.dict()

            # Fetch pool information to get pool_name and APR
            pool_name = None
            pool_apr = None
            try:
                pool_data = await pools_service.get_pool(position.pool_address, include_effective_apr=False)
                symbol = pool_data.get('symbol', '')
                # Extract just the token pair (remove fee percentage)
                if symbol and '-' in symbol:
                    pool_name = symbol.split('-')[0]  # Get everything before the dash
                else:
                    pool_name = symbol
                pool_apr = pool_data.get('apr', 0)  # Get APR from pool data
                logger.info(f"Found pool name {pool_name} with APR {pool_apr}% for pool {position.pool_address}")
            except Exception as e:
                logger.warning(f"Could not fetch pool info for {position.pool_address}: {e}")

            # Add pool_name and APR to position data
            position_dict['pool_name'] = pool_name
            position_dict['apr'] = pool_apr

            logger.info(f"Successfully fetched position {position_id} via unified endpoint")
            return PositionDetailResponse(position=PositionInfo(**position_dict))

        except ValueError as e:
            logger.warning(f"Position not found: {position_id}")
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "POSITION_NOT_FOUND",
                        "message": str(e),
                        "details": {"position_id": position_id}
                    }
                }
            )
        except Exception as e:
            logger.error(f"Error fetching position {position_id}: {e!r}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail={
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": f"Failed to fetch position {position_id}",
                        "details": {"error": str(e)}
                    }
                }
            )

    # Check if requesting all active positions
    if all_active:
        # Check authorization (Bearer token should be present for agent-manager)
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            logger.warning("Unauthorized attempt to get all active positions")
            raise HTTPException(
                status_code=401,
                detail={
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Authorization required to fetch all positions"
                    }
                }
            )

        # Get all active positions from database
        try:
            from app.database.models import Position

            stmt = select(Position).where(Position.status == "ACTIVE")
            result = await db.execute(stmt)
            positions_db = result.scalars().all()

            # Convert to response format matching PositionInfo schema
            positions = []
            for pos in positions_db:
                position_info = PositionInfo(
                    id=pos.token_id,
                    owner=pos.user_id,  # user_id is the wallet address
                    pool_address=pos.pool_address,
                    tick_lower=pos.tick_lower or 0,
                    tick_upper=pos.tick_upper or 0,
                    current_tick=0,  # Would need to fetch from blockchain
                    liquidity=pos.liquidity or "0",
                    in_range=True,  # Would need to check from blockchain
                    staked=pos.staked,
                    current_value_usd=float(pos.current_value_usdc) if pos.current_value_usdc else None,
                    gauge_address=pos.gauge_address,
                    pool_name=pos.pool_name
                )
                positions.append(position_info)

            logger.info(f"Successfully fetched {len(positions)} active positions for agent-manager")
            return PositionListResponse(
                positions=positions,
                total=len(positions)
            )
        except Exception as e:
            logger.error(f"Error fetching all active positions: {e}")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "Failed to fetch positions",
                        "details": {"error": str(e)}
                    }
                }
            )

    # Require at least one filter for normal queries
    if not any([owner, pool, in_range is not None, position_id is not None]):
        logger.warning("Missing filter parameters for /positions")
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "MISSING_PARAMETERS",
                    "message": "At least one filter parameter is required",
                    "details": {"available_filters": ["position_id", "owner", "pool", "in_range", "all_active"]}
                }
            }
        )

    try:
        # Currently only owner filter is implemented
        if owner:
            positions = await positions_service.get_positions_by_owner(owner)
            logger.info(f"Successfully fetched {len(positions)} positions for owner {owner}")

            # Apply additional filters if provided (future enhancement)
            # if pool:
            #     positions = [p for p in positions if p.pool_address.lower() == pool.lower()]
            # if in_range is not None:
            #     positions = [p for p in positions if p.in_range == in_range]

            return PositionListResponse(
                positions=positions,
                total=len(positions)
            )
        else:
            # Future: implement pool-based or in_range filters
            logger.warning(f"Unsupported filter combination requested")
            raise HTTPException(
                status_code=501,
                detail={
                    "error": {
                        "code": "NOT_IMPLEMENTED",
                        "message": "Only owner filter is currently supported",
                        "details": {"requested_filters": {"pool": pool, "in_range": in_range}}
                    }
                }
            )

    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid parameters for /positions: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_PARAMETERS",
                    "message": str(e),
                    "details": {"filters": {"owner": owner, "pool": pool, "in_range": in_range}}
                }
            }
        )
    except Exception as e:
        logger.error(f"Error fetching positions: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to fetch positions",
                    "details": {"error": str(e)}
                }
            }
        )


# ============================================================================
# TOKENS ENDPOINTS
# ============================================================================

@router.get(
    "/tokens/{address}",
    response_model=TokenInfoResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Token not found"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def get_token_info(
    request: Request,
    address: str = Path(..., description="Token contract address", pattern="^0x[a-fA-F0-9]{40}$")
):
    """
    Get information about a specific token.

    Returns token metadata including symbol, decimals, name, and current price.
    """
    logger.info(f"GET /tokens/{address} - IP: {request.client.host}")
    try:
        token_info = await pools_service.get_token_info(address)
        logger.info(f"Successfully fetched token info for {address}")
        return token_info

    except Exception as e:
        if "not found" in str(e).lower():
            logger.warning(f"Token not found: {address}")
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "TOKEN_NOT_FOUND",
                        "message": f"Token with address {address} not found",
                        "details": {}
                    }
                }
            )
        logger.error(f"Error fetching token info for {address}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to fetch token information",
                    "details": {"error": str(e)}
                }
            }
        )




# ============================================================================
# HEDGE ENDPOINTS
# ============================================================================

@router.get(
    "/hedge/{wallet}",
    response_model=HedgePositionResponse,
    responses={
        404: {"model": ErrorResponse, "description": "No positions found"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def get_hedge_position(
    request: Request,
    wallet: str = Path(..., description="Wallet address", pattern="^0x[a-fA-F0-9]{40}$")
):
    """
    Get vault hedge positions and account health for a wallet.

    Returns comprehensive information about:
    - All hedged positions (token IDs) with collateral and debt
    - Global protocol health metrics
    - Per-position hedge information (asset, collateral, debt)
    - Protocol-wide health factor and risk status

    The health factor indicates the safety of the protocol:
    - Health Factor > 1.5: Safe position
    - Health Factor < 1.5: At risk
    - Health Factor = 1.0: At liquidation threshold

    Each position shows:
    - Collateral amount in USDC
    - Debt amount in the hedged asset (WETH or cbBTC)
    - Whether position is actively hedged
    """
    logger.info(f"GET /hedge/{wallet} - IP: {request.client.host}")
    try:
        # Get hedge position data from vault
        position = await hedge_service.get_hedge_position(wallet)

        # Check if wallet has any positions
        if not position.positions:
            logger.info(f"No hedge positions found for wallet {wallet}")
            # Still return the response with empty positions
            return position

        logger.info(f"Successfully fetched hedge position for {wallet}")
        logger.info(f"  Total positions: {len(position.positions)}")
        logger.info(f"  Total collateral: ${position.total_collateral_usd}")
        logger.info(f"  Total debt: ${position.total_debt_usd}")
        logger.info(f"  Global health factor: {position.global_health.health_factor}")
        logger.info(f"  Protocol at risk: {position.global_health.is_at_risk}")

        return position

    except Exception as e:
        logger.error(f"Error fetching hedge position for {wallet}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to fetch hedge position",
                    "details": {"error": str(e)}
                }
            }
        )

