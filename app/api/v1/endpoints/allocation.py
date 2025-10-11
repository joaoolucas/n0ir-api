"""
API endpoints for managing per-strategy capital allocation.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.database.session import get_db
from app.core.auth import get_authenticated_wallet
from app.services.capital_allocation_service import get_capital_allocation_service
from app.schemas.capital import (
    PositionEventRequest,
    PositionEventResponse,
    AllocationUpdateRequest,
    AllocationUpdateResponse
)

router = APIRouter(prefix="/users")


@router.post(
    "/{user_id}/strategies/{strategy_code}/positions/events",
    response_model=PositionEventResponse
)
async def report_position_event(
    user_id: str,
    strategy_code: str,
    event: PositionEventRequest,
    request: Request,
    authenticated_wallet: str = Depends(get_authenticated_wallet),
    db: AsyncSession = Depends(get_db)
) -> PositionEventResponse:
    """
    Report a position lifecycle event to update deployed capital tracking.

    This endpoint should be called by the agent manager whenever:
    - A position is opened (`type: "opened"`)
    - A position is closed (`type: "closed"`)
    - A position is rebalanced (`type: "rebalanced"`)

    The API will update the `deployed_capital_usd` field in real-time to ensure
    accurate capital allocation tracking.

    **Event Types:**

    - **opened**: Reports a new position was created
        - Required: `capital_deployed_usd`
        - Effect: Increases deployed capital by `capital_deployed_usd`

    - **closed**: Reports a position was closed
        - Required: `capital_returned_usd`, `pnl_usd`
        - Effect: Decreases deployed capital by *original deployed amount*
        - Note: PnL does not affect allocation tracking

    - **rebalanced**: Reports a position's capital changed
        - Required: `capital_change_usd` (positive = added, negative = removed)
        - Effect: Adjusts deployed capital by `capital_change_usd`

    **Idempotency:**
    Events are idempotent based on `tx_hash`. Duplicate events will be ignored
    and return the current state without modification.

    Args:
        user_id: User wallet address
        strategy_code: Strategy short code (e.g., 'h3', 's1')
        event: Position event details

    Returns:
        Updated deployed and available capital for the strategy

    Raises:
        403: If user attempts to report events for another wallet
        404: If user or strategy not found
        400: If event data is invalid
    """
    # Verify user can only report events for their own positions
    if authenticated_wallet.lower() != user_id.lower():
        raise HTTPException(
            status_code=403,
            detail="Cannot report events for another user"
        )

    try:
        capital_service = get_capital_allocation_service(db)

        # Record event and update deployed capital
        new_deployed, new_available = await capital_service.record_position_event(
            user_id=user_id,
            strategy_code=strategy_code,
            event=event
        )

        logger.info(
            f"Processed {event.type} event for {user_id}/{strategy_code}, "
            f"token_id={event.token_id}, deployed={new_deployed}, available={new_available}"
        )

        return PositionEventResponse(
            success=True,
            strategy_code=strategy_code,
            deployed_capital_usd=new_deployed,
            available_capital_usd=new_available,
            message=f"Position {event.type} event processed successfully"
        )

    except ValueError as e:
        logger.error(f"Invalid event data: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing position event: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process position event: {str(e)}"
        )


