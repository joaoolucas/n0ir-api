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
    DeltaNeutralStrategyRequest,
    DeltaNeutralStrategyResponse,
    CreateRequest,
    CreateResponse,
    ActivateRequest,
    ActivateResponse,
    DeactivateRequest,
    DeactivateResponse
)
from app.database.models import User

router = APIRouter(prefix="/users")


@router.post("/{user_id}/create", response_model=CreateResponse)
async def create_user(
    user_id: str,
    request: CreateRequest = CreateRequest(),
    db: AsyncSession = Depends(get_db)
) -> CreateResponse:
    """
    Create user and CDP wallet.

    This will:
    1. Create user in database if not exists
    2. Create CDP wallet through agent manager
    3. Return wallet address

    Does NOT activate the agent.
    """
    from app.services.agent_management_service import get_agent_service

    try:
        # Check if user exists
        service = UserService(db)
        user = await service.get_user(user_id)

        if user and user.cdp_wallet_address:
            # User already exists with wallet
            return CreateResponse(
                user_id=user_id,
                cdp_wallet_address=user.cdp_wallet_address,
                status="already_exists",
                message="User already exists with CDP wallet"
            )

        # Create user if not exists
        if not user:
            user = await service.create_user(user_id)

        # Create CDP wallet through agent manager
        agent_service = get_agent_service()
        wallet_result = await agent_service.create_wallet_for_user(user_id)

        if wallet_result.get('success'):
            wallet_address = wallet_result.get('wallet_address')

            # Update user with wallet address
            if wallet_address:
                user.cdp_wallet_address = wallet_address
                await db.commit()

                # Sync blockchain data for new wallet
                await service.sync_blockchain_data(user_id)

                return CreateResponse(
                    user_id=user_id,
                    cdp_wallet_address=wallet_address,
                    status="created",
                    message="User and CDP wallet created successfully"
                )
            else:
                return CreateResponse(
                    user_id=user_id,
                    cdp_wallet_address="",
                    status="error",
                    message="Wallet creation in progress, try again later"
                )
        else:
            return CreateResponse(
                user_id=user_id,
                cdp_wallet_address="",
                status="error",
                message=wallet_result.get('error', 'Failed to create wallet')
            )

    except Exception as e:
        logger.error(f"Error creating user {user_id}: {e}")
        return CreateResponse(
            user_id=user_id,
            cdp_wallet_address="",
            status="error",
            message=str(e)
        )


@router.post("/{user_id}/activate", response_model=ActivateResponse)
async def activate_agent(
    user_id: str,
    request: ActivateRequest = ActivateRequest(),
    db: AsyncSession = Depends(get_db)
) -> ActivateResponse:
    """
    Activate trading agent for user.

    This will:
    1. Start the agent process
    2. Enable automated trading based on strategy

    Requires user to exist with CDP wallet (use /create first).
    """
    from app.services.agent_management_service import get_agent_service

    try:
        # Check user exists with wallet
        service = UserService(db)
        user = await service.get_user(user_id)

        if not user:
            return ActivateResponse(
                user_id=user_id,
                status="error",
                message="User not found. Please create user first with /create endpoint"
            )

        if not user.cdp_wallet_address:
            return ActivateResponse(
                user_id=user_id,
                status="error",
                message="User has no CDP wallet. Please create wallet first with /create endpoint"
            )

        # Sync blockchain data before activation
        await service.sync_blockchain_data(user_id)

        # Send activate command to agent manager
        agent_service = get_agent_service()
        result = await agent_service.activate_agent(
            user_id=user_id,
            strategy_type=request.strategy_type
        )

        if result.get('success'):
            return ActivateResponse(
                user_id=user_id,
                status="activated" if result.get('newly_activated') else "already_active",
                cdp_wallet_address=user.cdp_wallet_address,
                message=result.get('message', 'Agent activated successfully')
            )
        else:
            return ActivateResponse(
                user_id=user_id,
                status="error",
                cdp_wallet_address=user.cdp_wallet_address,
                message=result.get('error', 'Failed to activate agent')
            )

    except Exception as e:
        logger.error(f"Error activating agent for {user_id}: {e}")
        return ActivateResponse(
            user_id=user_id,
            status="error",
            message=str(e)
        )


@router.post("/{user_id}/deactivate", response_model=DeactivateResponse)
async def deactivate_agent(
    user_id: str,
    request: DeactivateRequest = DeactivateRequest(),
    db: AsyncSession = Depends(get_db)
) -> DeactivateResponse:
    """
    Deactivate trading agent for user.

    This will:
    1. Stop the agent process
    2. Close all open positions
    3. Withdraw all funds to user's wallet
    """
    from app.services.agent_management_service import get_agent_service
    from sqlalchemy import select

    try:
        # Check user exists
        result = await db.execute(
            select(User).where(User.user_id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            return DeactivateResponse(
                user_id=user_id,
                status="error",
                message="User not found"
            )

        # Sync blockchain data before deactivation to get latest state
        service = UserService(db)
        await service.sync_blockchain_data(user_id)

        # Send deactivate command to agent manager (always withdraws funds)
        agent_service = get_agent_service()
        result = await agent_service.deactivate_agent(
            user_id=user_id,
            withdraw_funds=True  # Always withdraw all funds
        )

        if result.get('success'):
            return DeactivateResponse(
                user_id=user_id,
                status="deactivated" if result.get('was_active') else "already_inactive",
                withdrawn_amount=Decimal(str(result.get('withdrawn_amount', 0))) if result.get('withdrawn_amount') else None,
                tx_hash=result.get('tx_hash'),
                message=result.get('message', 'Agent deactivated successfully')
            )
        else:
            return DeactivateResponse(
                user_id=user_id,
                status="error",
                message=result.get('error', 'Failed to deactivate agent')
            )

    except Exception as e:
        logger.error(f"Error deactivating agent for {user_id}: {e}")
        return DeactivateResponse(
            user_id=user_id,
            status="error",
            message=str(e)
        )


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
        # Sync blockchain data to get latest positions and transactions
        service = UserService(db)
        await service.sync_blockchain_data(user_id)

        # This unified method handles both initial strategy and monitoring
        strategy = await delta_neutral_service.analyze_user_portfolio(
            user_id=user_id,
            db=db
        )

        # Log the complete strategy response for debugging
        logger.info(f"Strategy response for {user_id}:")
        logger.info(f"  Action: {strategy.action}")
        logger.info(f"  Notes: {strategy.notes}")
        logger.info(f"  Total capital to deploy: ${strategy.total_capital_deployed}")
        logger.info(f"  Remaining balance: ${strategy.remaining_balance}")

        # Log LP allocations
        if strategy.lp_allocations:
            logger.info(f"  LP Allocations ({len(strategy.lp_allocations)}):")
            total_lp = 0
            for lp in strategy.lp_allocations:
                logger.info(f"    - {lp.pair}: ${lp.amount_usd} (range: {lp.range_pct}%)")
                total_lp += float(lp.amount_usd)
            logger.info(f"    Total LP: ${total_lp}")

        # Log hedges
        if strategy.hedges:
            logger.info(f"  Hedges ({len(strategy.hedges)}):")
            total_hedge = 0
            for hedge in strategy.hedges:
                logger.info(f"    - {hedge.asset} {hedge.side}: ${hedge.collateral_usd} (leverage: {hedge.leverage}x)")
                total_hedge += float(hedge.collateral_usd)
            logger.info(f"    Total Hedge: ${total_hedge}")
        else:
            logger.warning(f"  ⚠️ No hedges in strategy response!")

        # Log position info if present
        if strategy.current_positions:
            logger.info(f"  Current positions: {len(strategy.current_positions)}")
        if strategy.out_of_range_positions:
            logger.info(f"  Out of range positions: {strategy.out_of_range_positions}")

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