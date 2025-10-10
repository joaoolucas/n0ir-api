"""
API endpoints for managing user strategies.
"""
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.database.session import get_db
from app.services.strategy_service import StrategyService
from app.schemas.strategy import (
    CreateStrategyRequest,
    UpdateStrategyStatusRequest,
    UpdateStrategyCapitalRequest,
    StrategyResponse,
    StrategyListResponse,
    StrategyWithPositionsResponse,
    StrategyTypeEnum,
    StrategyStatusEnum
)
from app.core.auth import get_authenticated_wallet

router = APIRouter(prefix="/users/{user_id}/strategies", tags=["Strategies"])


@router.post("", response_model=StrategyResponse, status_code=201)
async def create_strategy(
    user_id: str = Path(..., description="User wallet address"),
    request: CreateStrategyRequest = ...,
    authenticated_wallet: str = Depends(get_authenticated_wallet),
    db: AsyncSession = Depends(get_db)
) -> StrategyResponse:
    """
    Create a new strategy for a user.

    Requires JWT authentication. Users can only create strategies for themselves.

    **Strategy Types:**
    - `hedged_weth_only`: Hedged WETH/USDC only
    - `hedged_cbbtc_only`: Hedged cbBTC/USDC only
    - `hedged_blueprint`: Hedged split between WETH and cbBTC (50/50)
    - `nonhedged_weth_only`: Non-hedged WETH/USDC only
    - `nonhedged_cbbtc_only`: Non-hedged cbBTC/USDC only
    - `nonhedged_blueprint`: Non-hedged split between WETH and cbBTC (50/50)
    - `stable_usdc_eurc`: USDC/EURC stable pair
    - `stable_usdc_brz`: USDC/BRZ stable pair
    """
    # Verify user can only create for themselves
    if authenticated_wallet.lower() != user_id.lower():
        raise HTTPException(
            status_code=403,
            detail="Cannot create strategy for another user"
        )

    try:
        service = StrategyService(db)
        strategy = await service.create_strategy(
            user_id=user_id,
            strategy_type=request.strategy_type,
            capital_usdc=request.capital_usdc
        )

        return StrategyResponse(
            strategy_id=strategy.strategy_id,
            user_id=strategy.user_id,
            strategy_type=StrategyTypeEnum(strategy.strategy_type.value),
            status=StrategyStatusEnum(strategy.status.value),
            capital_allocated_usdc=strategy.capital_allocated_usdc,
            created_at=strategy.created_at,
            updated_at=strategy.updated_at
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating strategy: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("", response_model=StrategyListResponse)
async def list_user_strategies(
    user_id: str = Path(..., description="User wallet address"),
    status: Optional[StrategyStatusEnum] = Query(None, description="Filter by status"),
    authenticated_wallet: str = Depends(get_authenticated_wallet),
    db: AsyncSession = Depends(get_db)
) -> StrategyListResponse:
    """
    Get all strategies for a user.

    Requires JWT authentication. Users can only view their own strategies.

    **Query Parameters:**
    - `status`: Optional filter by strategy status (active, paused, closed)
    """
    # Verify user can only view their own strategies
    if authenticated_wallet.lower() != user_id.lower():
        raise HTTPException(
            status_code=403,
            detail="Cannot view strategies for another user"
        )

    try:
        service = StrategyService(db)
        strategies = await service.get_user_strategies(user_id, status=status)

        strategy_responses = [
            StrategyResponse(
                strategy_id=s.strategy_id,
                user_id=s.user_id,
                strategy_type=StrategyTypeEnum(s.strategy_type.value),
                status=StrategyStatusEnum(s.status.value),
                capital_allocated_usdc=s.capital_allocated_usdc,
                created_at=s.created_at,
                updated_at=s.updated_at
            )
            for s in strategies
        ]

        return StrategyListResponse(
            strategies=strategy_responses,
            total_count=len(strategy_responses)
        )

    except Exception as e:
        logger.error(f"Error listing strategies: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{strategy_id}", response_model=StrategyWithPositionsResponse)
async def get_strategy_details(
    user_id: str = Path(..., description="User wallet address"),
    strategy_id: UUID = Path(..., description="Strategy UUID"),
    authenticated_wallet: str = Depends(get_authenticated_wallet),
    db: AsyncSession = Depends(get_db)
) -> StrategyWithPositionsResponse:
    """
    Get detailed information about a specific strategy.

    Returns strategy details along with all positions and performance metrics.

    Requires JWT authentication. Users can only view their own strategies.
    """
    # Verify user can only view their own strategies
    if authenticated_wallet.lower() != user_id.lower():
        raise HTTPException(
            status_code=403,
            detail="Cannot view strategies for another user"
        )

    try:
        service = StrategyService(db)
        strategy_details = await service.get_strategy_details(strategy_id)

        if not strategy_details:
            raise HTTPException(status_code=404, detail="Strategy not found")

        # Verify strategy belongs to user
        if strategy_details.user_id.lower() != user_id.lower():
            raise HTTPException(status_code=403, detail="Strategy does not belong to user")

        return strategy_details

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting strategy details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/{strategy_id}/status", response_model=StrategyResponse)
async def update_strategy_status(
    user_id: str = Path(..., description="User wallet address"),
    strategy_id: UUID = Path(..., description="Strategy UUID"),
    request: UpdateStrategyStatusRequest = ...,
    authenticated_wallet: str = Depends(get_authenticated_wallet),
    db: AsyncSession = Depends(get_db)
) -> StrategyResponse:
    """
    Update strategy status (active/paused/closed).

    **Status Transitions:**
    - `active`: Strategy is running and can execute trades
    - `paused`: Strategy is temporarily stopped (positions remain open)
    - `closed`: Strategy is permanently closed (cannot be reopened)

    Requires JWT authentication. Users can only update their own strategies.
    """
    # Verify user can only update their own strategies
    if authenticated_wallet.lower() != user_id.lower():
        raise HTTPException(
            status_code=403,
            detail="Cannot update strategy for another user"
        )

    try:
        service = StrategyService(db)

        # Verify strategy belongs to user
        strategy = await service.get_strategy_by_id(strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")

        if strategy.user_id.lower() != user_id.lower():
            raise HTTPException(status_code=403, detail="Strategy does not belong to user")

        # Update status
        updated_strategy = await service.update_strategy_status(
            strategy_id=strategy_id,
            status=request.status
        )

        return StrategyResponse(
            strategy_id=updated_strategy.strategy_id,
            user_id=updated_strategy.user_id,
            strategy_type=StrategyTypeEnum(updated_strategy.strategy_type.value),
            status=StrategyStatusEnum(updated_strategy.status.value),
            capital_allocated_usdc=updated_strategy.capital_allocated_usdc,
            created_at=updated_strategy.created_at,
            updated_at=updated_strategy.updated_at
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating strategy status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/{strategy_id}/capital", response_model=StrategyResponse)
async def update_strategy_capital(
    user_id: str = Path(..., description="User wallet address"),
    strategy_id: UUID = Path(..., description="Strategy UUID"),
    request: UpdateStrategyCapitalRequest = ...,
    authenticated_wallet: str = Depends(get_authenticated_wallet),
    db: AsyncSession = Depends(get_db)
) -> StrategyResponse:
    """
    Update strategy capital allocation.

    This updates the target capital allocation for the strategy.
    Does not automatically create or close positions.

    Requires JWT authentication. Users can only update their own strategies.
    """
    # Verify user can only update their own strategies
    if authenticated_wallet.lower() != user_id.lower():
        raise HTTPException(
            status_code=403,
            detail="Cannot update strategy for another user"
        )

    try:
        service = StrategyService(db)

        # Verify strategy belongs to user
        strategy = await service.get_strategy_by_id(strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")

        if strategy.user_id.lower() != user_id.lower():
            raise HTTPException(status_code=403, detail="Strategy does not belong to user")

        # Update capital
        updated_strategy = await service.update_strategy_capital(
            strategy_id=strategy_id,
            capital_usdc=request.capital_usdc
        )

        return StrategyResponse(
            strategy_id=updated_strategy.strategy_id,
            user_id=updated_strategy.user_id,
            strategy_type=StrategyTypeEnum(updated_strategy.strategy_type.value),
            status=StrategyStatusEnum(updated_strategy.status.value),
            capital_allocated_usdc=updated_strategy.capital_allocated_usdc,
            created_at=updated_strategy.created_at,
            updated_at=updated_strategy.updated_at
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating strategy capital: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{strategy_id}", status_code=204)
async def delete_strategy(
    user_id: str = Path(..., description="User wallet address"),
    strategy_id: UUID = Path(..., description="Strategy UUID"),
    authenticated_wallet: str = Depends(get_authenticated_wallet),
    db: AsyncSession = Depends(get_db)
):
    """
    Close a strategy permanently.

    This sets the strategy status to 'closed'. Cannot be undone.

    **Requirements:**
    - Strategy must have no active positions
    - All positions must be closed first

    Requires JWT authentication. Users can only delete their own strategies.
    """
    # Verify user can only delete their own strategies
    if authenticated_wallet.lower() != user_id.lower():
        raise HTTPException(
            status_code=403,
            detail="Cannot delete strategy for another user"
        )

    try:
        service = StrategyService(db)

        # Verify strategy belongs to user
        strategy = await service.get_strategy_by_id(strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")

        if strategy.user_id.lower() != user_id.lower():
            raise HTTPException(status_code=403, detail="Strategy does not belong to user")

        # Delete strategy
        success = await service.delete_strategy(strategy_id)

        if not success:
            raise HTTPException(status_code=404, detail="Strategy not found")

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting strategy: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
