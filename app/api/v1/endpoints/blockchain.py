"""Unified Blockchain endpoints for pools, positions, and tokens."""

from typing import List, Optional, Union
from fastapi import APIRouter, HTTPException, Query, Path, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from decimal import Decimal

# Import schemas
from app.schemas.pools import (
    PoolData,
    PoolsListResponse,
    PoolBatchRequest,
    PoolStatsResponse
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
from app.core.auth import get_authenticated_wallet, verify_bearer_token
from app.database.session import get_db
from app.database.models import Position, APRSnapshot

# Whitelisted pools (moved from strategy_service)
WHITELISTED_POOLS = {
    "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59",  # WETH/USDC
    "0x4e962bb3889bf030368f56810a9c96b83cb3e778",  # cbBTC/USDC
    "0xe846373c1a92b167b4e9cd5d8e4d6b1db9e90ec7",  # New pool 1
    "0xd43decd5df4bdffd5a4cf35ca1f9557e33b7246c",  # New pool 2
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
    address: str = Path(..., description="Pool contract address", pattern="^0x[a-fA-F0-9]{40}$"),
    _: bool = Depends(verify_bearer_token)
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
    _: bool = Depends(verify_bearer_token),
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
            except Exception as e:
                logger.warning(f"Could not fetch pool info for {position.pool_address}: {e}")

            # Add pool_name and APR to position data
            position_dict['pool_name'] = pool_name
            position_dict['apr'] = pool_apr

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
    address: str = Path(..., description="Token contract address", pattern="^0x[a-fA-F0-9]{40}$"),
    _: bool = Depends(verify_bearer_token)
):
    """
    Get information about a specific token.

    Returns token metadata including symbol, decimals, name, and current price.
    """
    try:
        token_info = await pools_service.get_token_info(address)
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
    "/hedge",
    response_model=HedgePositionResponse,
    responses={
        404: {"model": ErrorResponse, "description": "No positions found"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def get_hedge_position(
    request: Request,
    token_id: Optional[int] = Query(None, description="Get hedge info for specific position by NFT token ID", ge=1),
    wallet: Optional[str] = Query(None, description="Get all hedge positions for wallet address", pattern="^0x[a-fA-F0-9]{40}$"),
    _: bool = Depends(verify_bearer_token)
):
    """
    Get vault hedge positions and account health.

    **Unified endpoint for hedge queries:**
    - Use `token_id` to get hedge info for a single position
    - Use `wallet` to get all hedged positions for a wallet

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

    At least one parameter (token_id or wallet) must be provided.
    """
    # Validate that at least one parameter is provided
    if token_id is None and wallet is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "MISSING_PARAMETER",
                    "message": "Either token_id or wallet parameter is required",
                    "details": {}
                }
            }
        )

    # Validate that only one parameter is provided
    if token_id is not None and wallet is not None:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_PARAMETERS",
                    "message": "Only one of token_id or wallet can be provided",
                    "details": {}
                }
            }
        )

    try:
        if token_id is not None:
            # Get hedge position data by token ID
            position = await hedge_service.get_hedge_position_by_token_id(token_id)
        else:
            # Get hedge position data from vault by wallet
            position = await hedge_service.get_hedge_position(wallet)

        # Check if wallet has any positions
        if not position.positions:
            # Still return the response with empty positions
            return position

        return position

    except Exception as e:
        logger.error(f"Error fetching hedge position for token_id={token_id}, wallet={wallet}: {str(e)}", exc_info=True)
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


# ============================================================================
# DISPLAY ENDPOINT
# ============================================================================

@router.get(
    "/display",
    responses={
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def get_display_data(
    request: Request,
    pool_address: Optional[str] = Query(None, description="Filter by pool address", pattern="^0x[a-fA-F0-9]{40}$"),
    authenticated_wallet: str = Depends(get_authenticated_wallet),
    db: AsyncSession = Depends(get_db)
):
    """
    Get mean APR metrics from snapshots for pools with current TVL and 24h volume.

    Returns aggregated APR data from historical snapshots combined with
    current pool metrics (TVL and 24h volume).

    **Authentication:**
    Supports both JWT session tokens and API_BEARER_TOKEN.

    **Query Parameters:**
    - pool_address (optional): Filter results for a specific pool

    **Returns:**
    For each pool:
    - pool_address: Pool contract address
    - pool_symbol: Pool token pair symbol
    - mean_apr: Average base APR across all snapshots
    - mean_effective_apr_narrow: Average effective APR for narrow range positions
    - mean_effective_apr_standard: Average effective APR for standard range positions
    - mean_effective_apr_wide: Average effective APR for wide range positions
    - mean_effective_apr_stable: Average effective APR for stable pools
    - mean_effective_apr_hedged: 65% of mean_effective_apr_standard (hedged position APR)
    - tvl_usd: Current total value locked (from pools service)
    - volume_24h: Current 24h trading volume (from pools service)
    """
    try:
        # Build query to calculate mean for all APR types per pool
        query = select(
            APRSnapshot.pool_address,
            APRSnapshot.pool_symbol,
            func.avg(APRSnapshot.apr).label("mean_apr"),
            func.avg(APRSnapshot.effective_apr_narrow).label("mean_effective_apr_narrow"),
            func.avg(APRSnapshot.effective_apr_standard).label("mean_effective_apr_standard"),
            func.avg(APRSnapshot.effective_apr_wide).label("mean_effective_apr_wide"),
            func.avg(APRSnapshot.effective_apr_stable).label("mean_effective_apr_stable")
        ).group_by(
            APRSnapshot.pool_address,
            APRSnapshot.pool_symbol
        )

        # Apply pool filter if provided
        if pool_address:
            query = query.where(APRSnapshot.pool_address == pool_address.lower())

        result = await db.execute(query)
        snapshot_data = result.all()

        if not snapshot_data:
            return {
                "pools": [],
                "total": 0,
                "message": "No APR snapshots found" if not pool_address else f"No snapshots found for pool {pool_address}"
            }

        # Enrich with TVL and volume from pools service
        pools = []
        for row in snapshot_data:
            mean_standard = float(row.mean_effective_apr_standard) if row.mean_effective_apr_standard else None

            pool_info = {
                "pool_address": row.pool_address,
                "pool_symbol": row.pool_symbol,
                "mean_apr": float(row.mean_apr) if row.mean_apr else 0.0,
                "mean_effective_apr_narrow": float(row.mean_effective_apr_narrow) if row.mean_effective_apr_narrow else None,
                "mean_effective_apr_standard": mean_standard,
                "mean_effective_apr_wide": float(row.mean_effective_apr_wide) if row.mean_effective_apr_wide else None,
                "mean_effective_apr_stable": float(row.mean_effective_apr_stable) if row.mean_effective_apr_stable else None,
                "mean_effective_apr_hedged": mean_standard * 0.65 if mean_standard else None,
                "tvl_usd": None,
                "volume_24h": None
            }

            # Fetch current pool data for TVL and volume
            try:
                pool_data = await pools_service.get_pool(row.pool_address)
                pool_info["tvl_usd"] = float(pool_data.get("tvl_usd", 0)) if pool_data.get("tvl_usd") else None
                pool_info["volume_24h"] = float(pool_data.get("volume_24h", 0)) if pool_data.get("volume_24h") else None
            except Exception as e:
                logger.warning(f"Could not fetch pool data for {row.pool_address}: {e}")

            pools.append(pool_info)

        return {
            "pools": pools,
            "total": len(pools)
        }

    except Exception as e:
        logger.error(f"Error fetching display data: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to fetch display data",
                    "details": {"error": str(e)}
                }
            }
        )

