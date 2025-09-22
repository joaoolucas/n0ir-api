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
    1. Check user exists and has CDP wallet
    2. Send withdrawal command to agent manager
    3. Agent manager will close positions and execute withdrawal
    4. Return transaction details
    """
    from app.services.agent_management_service import get_agent_service
    from app.core.blockchain_service import blockchain_service
    from sqlalchemy import select
    import uuid
    from datetime import datetime

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

        # Get current balance to show in response
        wallet_balance = await blockchain_service.get_usdc_balance(user.cdp_wallet_address)

        # Get total portfolio value including positions
        from app.services.user_service import UserService
        user_service = UserService(db)
        positions = await user_service.get_user_positions(user_id, status='ACTIVE')

        # Calculate total portfolio value (wallet + positions)
        total_portfolio_value = float(wallet_balance)
        position_ids = []
        for position in positions:
            if position.current_value_usdc:
                total_portfolio_value += float(position.current_value_usdc)
            # Collect position NFT IDs to close
            if position.nft_token_id:
                position_ids.append(position.nft_token_id)

        logger.info(f"User {user_id} withdrawal - Wallet: ${wallet_balance}, Positions: {len(positions)} (IDs: {position_ids}), Total: ${total_portfolio_value}")

        # Send withdrawal command to agent manager
        # The agent manager will handle closing positions and withdrawing all funds
        agent_service = get_agent_service()

        # Request withdrawal with explicit positions to close
        result = await agent_service.withdraw_usdc(
            user_id=user_id,
            amount=total_portfolio_value,  # Request total portfolio value
            positions_to_close=position_ids,  # Explicitly tell agent which positions to close
            withdraw_all=True  # Withdraw everything
        )

        if not result.get('success'):
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"Agent manager withdrawal failed for {user_id}: {error_msg}")
            raise HTTPException(status_code=500, detail=f"Withdrawal failed: {error_msg}")

        # Generate unique tx_hash with timestamp/UUID to avoid duplicates
        tx_hash = result.get('tx_hash') or f"withdraw_{user_id}_{uuid.uuid4().hex[:8]}_{datetime.utcnow().timestamp():.0f}"

        # Record transaction in database
        from app.database.models import Transaction

        # Determine status based on agent manager result
        tx_status = "CONFIRMED" if result.get('success') else "PENDING"

        transaction = Transaction(
            user_id=user_id,
            tx_hash=tx_hash,
            tx_type="WITHDRAW",
            status=tx_status,
            created_at=datetime.utcnow(),  # Explicitly set created_at
            processed_at=datetime.utcnow() if tx_status == "CONFIRMED" else None,
            event_data={
                "amount_usdc": total_portfolio_value,
                "to_address": user_id,  # Main wallet
                "withdraw_all": True,
                "wallet_balance": float(wallet_balance),
                "positions_value": total_portfolio_value - float(wallet_balance),
                "positions_count": len(positions)
            }
        )
        db.add(transaction)
        await db.commit()
        await db.refresh(transaction)  # Refresh to get the generated ID and timestamps

        return WithdrawResponse(
            requested_amount=Decimal(str(total_portfolio_value)),
            withdrawn_amount=Decimal(str(total_portfolio_value)),
            remaining_balance=Decimal(0),  # Withdrawing all
            positions_closed=len(positions),  # Number of positions to be closed
            status="pending",  # Transaction is being processed
            transaction_id=transaction.id,
            tx_hash=tx_hash,  # Use tx_hash field from schema
            message=f"Withdrawal of ${total_portfolio_value:.2f} initiated. Closing {len(positions)} positions and processing..."
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