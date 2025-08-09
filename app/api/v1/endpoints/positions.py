"""Positions API endpoints."""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Path, Query
from app.schemas.positions import (
    PositionInfo,
    PositionListResponse,
    PositionDetailResponse
)
from app.schemas.common import ErrorResponse
from app.core.positions_service import positions_service

router = APIRouter()


@router.get(
    "/positions/{position_id}",
    response_model=PositionDetailResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Position not found"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def get_position(
    position_id: int = Path(..., description="NFT token ID of the position", ge=1)
):
    """
    Get detailed information about a specific position by its NFT token ID.
    
    Returns position details including:
    - Owner address
    - Pool information
    - Tick range
    - Liquidity
    - Uncollected fees
    - Whether the position is in range
    - Staking status
    """
    try:
        position = await positions_service.get_position_by_id(position_id)
        return PositionDetailResponse(position=position)
        
    except ValueError as e:
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


@router.get(
    "/positions",
    response_model=PositionListResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid parameters"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def get_positions(
    owner: Optional[str] = Query(None, description="Filter by owner wallet address", pattern="^0x[a-fA-F0-9]{40}$"),
    pool: Optional[str] = Query(None, description="Filter by pool address", pattern="^0x[a-fA-F0-9]{40}$"),
    in_range: Optional[bool] = Query(None, description="Filter by in-range status")
):
    """
    Get positions with optional filters.
    
    Returns both staked and unstaked positions.
    
    Supports filtering by:
    - owner: Wallet address that owns the positions (includes both staked and unstaked)
    - pool: Pool address (future implementation)
    - in_range: Whether positions are in range (future implementation)
    
    At least one filter must be provided.
    """
    # Require at least one filter
    if not any([owner, pool, in_range is not None]):
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "MISSING_PARAMETERS",
                    "message": "At least one filter parameter is required",
                    "details": {"available_filters": ["owner", "pool", "in_range"]}
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