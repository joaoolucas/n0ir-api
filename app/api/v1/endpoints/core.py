"""
Core API endpoints for essential user operations.
Handles user creation, activation, and strategy generation.
"""
from typing import Optional
from decimal import Decimal
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.database.session import get_db
from app.services.user_service import UserService
from app.core.vault_strategy_service import vault_strategy_service
from app.schemas.users import (
    CreateResponse,
    ActivateResponse,
    DeactivateResponse,
    MoonwellStrategyResponse
)
from app.database.models import User

router = APIRouter(prefix="/users")


@router.post("/{user_id}/create", response_model=CreateResponse)
async def create_user(
    user_id: str,
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
            # Create user with placeholder CDP wallet info (will be updated after wallet creation)
            user = await service.create_user(
                user_id=user_id,
                cdp_wallet_address=None,  # Will be set after wallet creation
                cdp_wallet_name=f"wallet_{user_id}"  # Default wallet name
            )

        # Create CDP wallet through agent manager
        agent_service = get_agent_service()
        wallet_result = await agent_service.create_wallet_for_user(user_id)

        if wallet_result.get('success'):
            wallet_address = wallet_result.get('wallet_address')

            # Update user with wallet address
            if wallet_address:
                user.cdp_wallet_address = wallet_address
                await db.commit()

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

        # Send activate command to agent manager (always use delta_neutral strategy)
        agent_service = get_agent_service()
        result = await agent_service.activate_agent(
            user_id=user_id,
            strategy_type="delta_neutral"
        )

        if result.get('success'):
            # Update user status to ACTIVE and set agent_status to running
            user.status = 'ACTIVE'
            user.agent_status = 'running'
            user.agent_started_at = datetime.utcnow()
            await db.commit()

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
            # Update user status to INACTIVE and set agent_status to stopped
            user.status = 'INACTIVE'
            user.agent_status = 'stopped'
            user.agent_stopped_at = datetime.utcnow()
            await db.commit()

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


@router.post("/{user_id}/strategy", response_model=MoonwellStrategyResponse)
async def get_vault_strategy(
    user_id: str,
    db: AsyncSession = Depends(get_db)
) -> MoonwellStrategyResponse:
    """
    Generate vault-based delta-neutral strategy for a user.

    This endpoint generates a strategy and returns all parameters needed
    to call the vault contract's createPosition function:

    Returns:
    - contract_params: Ready-to-use parameters for vault.createPosition()
      - pool: Aerodrome pool address
      - rangePercentage: Position range (e.g., 10 = ±5%)
      - deadline: Transaction deadline timestamp
      - usdcAmount: USDC amount to deploy
      - slippageBps: Slippage tolerance (default 50 = 0.5%)
      - hedgeRatio: Hedge ratio in bps (e.g., 9200 = 92%)
      - collateralRatioBps: Collateral ratio in bps (e.g., 6500 = 65%)

    - simulation: Expected results from the strategy
      - Health factor, liquidation price, delta-neutral score
      - Collateral, borrow, and LP amounts

    - aerodrome_pool: Pool details and expected APR
    - monitoring: Range break alerts if applicable
    """
    try:
        # Default to WETH/USDC pool
        pool_address = "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59"  # WETH/USDC pool

        strategy = await vault_strategy_service.generate_strategy(
            user_id=user_id,
            db=db,
            pool_address=pool_address
        )

        # Log strategy details
        logger.info(f"Vault strategy for user {user_id}:")
        logger.info(f"  Action: {strategy.action}")
        logger.info(f"  Total capital: ${strategy.capital.total_usd}")
        logger.info(f"  Collateral: ${strategy.simulation.collateral_amount}")
        logger.info(f"  Borrow: ${strategy.simulation.borrow_amount_usd}")
        logger.info(f"  Delta-neutral score: {strategy.simulation.delta_neutral_score:.4f}")
        logger.info(f"  Health factor: {strategy.simulation.expected_health_factor:.2f}")
        logger.info(f"  Aerodrome LP: ${strategy.aerodrome_pool.amount_usdc}")

        if strategy.monitoring and strategy.monitoring.alerts:
            logger.warning(f"  ⚠️ {len(strategy.monitoring.alerts)} position(s) need attention")
            for alert in strategy.monitoring.alerts:
                logger.warning(f"    Position {alert.position_id}: {alert.reason}")

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

