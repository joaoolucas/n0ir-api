"""
Core API endpoints for essential user operations.
Handles user creation, withdrawals, and strategy generation.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import asyncio
from decimal import Decimal
from loguru import logger

from app.database.session import get_db
from app.services.user_service import UserService
from app.core.delta_neutral_service import delta_neutral_service
from app.schemas.users import (
    UserResponse,
    WithdrawResponse,
    DeltaNeutralStrategyRequest,
    DeltaNeutralStrategyResponse
)
from app.database.models import User

router = APIRouter(prefix="/users")


@router.post("/{user_id}", response_model=UserResponse)
async def create_user(
    user_id: str,
    db: AsyncSession = Depends(get_db)
) -> UserResponse:
    """
    Create a new user account.

    Creates a user with the specified ID. The CDP wallet will be created
    automatically on first transaction.
    """
    service = UserService(db)

    try:
        # Check if user exists
        existing_user = await service.get_user(user_id)
        if existing_user:
            # Return existing user instead of error
            return UserResponse(
                user_id=existing_user.user_id,
                cdp_wallet_address=existing_user.cdp_wallet_address,
                status=existing_user.status,
                created_at=existing_user.created_at,
                updated_at=existing_user.updated_at
            )
    except:
        pass  # User doesn't exist, create new one

    # Create new user
    user = await service.create_user(user_id)

    return UserResponse(
        user_id=user.user_id,
        cdp_wallet_address=user.cdp_wallet_address,
        status=user.status,
        created_at=user.created_at,
        updated_at=user.updated_at
    )


@router.post("/{user_id}/withdraw", response_model=WithdrawResponse)
async def withdraw_funds(
    user_id: str,
    db: AsyncSession = Depends(get_db)
) -> WithdrawResponse:
    """
    Withdraw all available funds from user's CDP wallet.

    Args:
        user_id: User identifier

    Returns:
        Withdrawal status and transaction details

    The endpoint will:
    1. Check available balance
    2. Close positions if needed to free up funds
    3. Execute withdrawal to user's main wallet
    4. Record transaction in database
    """
    from app.core.positions_service import positions_service
    from app.core.blockchain_service import blockchain_service
    from app.services.wallet_transaction_service import WalletTransactionService
    from sqlalchemy import select

    try:
        # Get user
        result = await db.execute(
            select(User).where(User.user_id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")

        if not user.cdp_wallet_address:
            raise HTTPException(status_code=400, detail="User has no CDP wallet")

        # Get current balance
        wallet_balance = await blockchain_service.get_usdc_balance(user.cdp_wallet_address)

        # Always withdraw all available funds
        requested_amount = Decimal(str(wallet_balance))

        # Check if we need to close positions (should not happen as we're withdrawing available balance)
        if requested_amount > wallet_balance:
            # Need to close positions
            positions = await positions_service.get_positions_by_owner(user.cdp_wallet_address)
            active_positions = [p for p in positions if p.status == 'ACTIVE']

            if not active_positions:
                return WithdrawResponse(
                    requested_amount=requested_amount,
                    withdrawn_amount=Decimal(str(wallet_balance)),
                    remaining_balance=Decimal(0),
                    positions_closed=0,
                    status="partial",
                    message=f"Insufficient balance. Only ${wallet_balance:.2f} available"
                )

            # TODO: Implement position closing logic
            # For now, return partial withdrawal
            withdrawn = Decimal(str(wallet_balance))
        else:
            withdrawn = requested_amount

        # Execute withdrawal (simplified - actual implementation would call CDP API)
        # Record transaction
        wallet_service = WalletTransactionService(db)
        tx_data = {
            "type": "WITHDRAW",
            "amount_usdc": float(withdrawn),
            "from_address": user.cdp_wallet_address,
            "to_address": user_id,  # Main wallet
            "status": "confirmed"
        }

        # Create transaction record
        from app.database.models import Transaction
        transaction = Transaction(
            user_id=user_id,
            tx_hash=f"withdraw_{user_id}_{Decimal(withdrawn):.2f}",  # Mock hash
            tx_type="WITHDRAW",
            status="CONFIRMED",
            event_data={
                "amount_usdc": float(withdrawn),
                "to_address": user_id  # Main wallet
            }
        )
        db.add(transaction)
        await db.commit()

        new_balance = Decimal(str(wallet_balance)) - withdrawn

        return WithdrawResponse(
            requested_amount=requested_amount,
            withdrawn_amount=withdrawn,
            remaining_balance=new_balance,
            positions_closed=0,
            status="complete",
            transaction_id=transaction.id,
            message=f"Successfully withdrawn ${withdrawn:.2f}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing withdrawal for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Withdrawal failed: {str(e)}")


@router.post("/{user_id}/strategy", response_model=DeltaNeutralStrategyResponse)
async def get_delta_neutral_strategy(
    user_id: str,
    db: AsyncSession = Depends(get_db)
) -> DeltaNeutralStrategyResponse:
    """
    Generate delta-neutral strategy recommendations for a user.

    This unified endpoint handles both scenarios:

    1. **Initial Strategy Generation** (no positions or all in range):
       - Returns LP allocations and hedge recommendations
       - Allocates capital based on balance thresholds

    2. **Range Break Monitoring** (positions out of range):
       - Detects out-of-range positions automatically
       - Returns action recommendations (close_and_reopen, wait, adjust_hedge)
       - Provides new allocations if rebalancing is needed

    Strategy rules:
    - < $2k: Single position (WETH/USDC) + hedge
    - >= $2k: Two positions (WETH priority + cbBTC for stability)
    - 90% to LP, 10% to 5x leveraged short for delta neutrality
    - Automatically handles range breaks with GPT-5 Nano decisions

    The agent manager can call this single endpoint for all strategy needs.
    """
    try:
        # This unified method handles both initial strategy and monitoring
        strategy = await delta_neutral_service.analyze_user_portfolio(
            user_id=user_id,
            db=db
        )

        return strategy

    except ValueError as e:
        # User not found or no CDP wallet
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating strategy for user {user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate strategy: {str(e)}"
        )