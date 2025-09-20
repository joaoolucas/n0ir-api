"""Positions API endpoints."""

from typing import List, Optional, Union
from fastapi import APIRouter, HTTPException, Query, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.schemas.positions import (
    PositionInfo,
    PositionListResponse,
    PositionDetailResponse,
    HedgedPositionCreate,
    HedgedPositionResponse
)
from app.schemas.common import ErrorResponse
from app.core.positions_service import positions_service
from app.core.pools_service import pools_service
from app.core.logger import logger
from app.database.session import get_db
from app.database.models import Position  # Import from __init__ to get compat version
from app.services.hedge_service import HedgeService
from app.core.exceptions import HedgeNotFoundError, HedgeError

router = APIRouter()


# NOTE: GET /positions/{position_id} endpoint removed - use GET /positions?position_id={id} instead

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

            # Query database to get user_id for this NFT token ID
            user_id = None
            try:
                stmt = select(Position.user_id).where(Position.token_id == position_id)
                result = await db.execute(stmt)
                db_user_id = result.scalar_one_or_none()
                if db_user_id:
                    user_id = db_user_id
                    logger.info(f"Found user_id {user_id} for position {position_id}")
            except Exception as e:
                logger.warning(f"Could not fetch user_id for position {position_id}: {e}")

            # Add user_id to position data if found
            position_dict = position.dict()
            position_dict['user_id'] = user_id

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

            # Fetch hedge information if it exists
            hedge_info = None
            try:
                hedge_service = HedgeService(db)
                hedge = await hedge_service.get_hedge_status(position_id)

                if hedge:
                    from app.schemas.positions import HedgeInfo
                    hedge_info = HedgeInfo(
                        hedge_id=hedge.hedge_id,
                        enabled=hedge.hedge_enabled,
                        market=hedge.market,
                        size_usdc=hedge.hedge_size_usdc,
                        collateral_usdc=hedge.collateral_usdc,
                        leverage=hedge.leverage,
                        entry_price=hedge.entry_price,
                        current_price=hedge.current_price,
                        pnl_usdc=hedge.pnl_usdc,
                        funding_paid_usdc=hedge.funding_paid_usdc,
                        health_ratio=hedge.health_ratio,
                        status=hedge.status
                    )
                    logger.info(f"Found hedge for position {position_id}: hedge_id={hedge.hedge_id}")
            except Exception as e:
                logger.debug(f"No hedge found for position {position_id}: {e}")

            # Add hedge to position data
            position_dict['hedge'] = hedge_info

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
            from sqlalchemy import select
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
                    pool_name=pos.pool_name,
                    user_id=pos.user_id,  # Add user_id for agent-manager compatibility
                    wallet_address=pos.user_id  # Add wallet_address for agent-manager
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




