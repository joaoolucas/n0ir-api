"""
Core API endpoints for essential user operations.
Handles user creation, activation, and strategy generation.
"""
from typing import Optional
from decimal import Decimal
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes
from sqlalchemy import text
from loguru import logger

from app.database.session import get_db
from app.services.user_service import UserService
from app.core.vault_strategy_service import vault_strategy_service
from app.schemas.users import (
    CreateResponse,
    ActivateResponse,
    DeactivateResponse,
    VaultStrategyResponse
)
from app.database.models import User
from app.core.auth import get_authenticated_wallet, create_session_token
from app.core.signature_verification import verify_wallet_signature
from pydantic import BaseModel

router = APIRouter(prefix="/users")


class LoginRequest(BaseModel):
    wallet: str
    signature: str
    message: str


class ActivateRequest(BaseModel):
    strategy_type: Optional[str] = "n1"
    allocation_usd: Optional[float] = 100.0


@router.post("/auth/login")
async def login(request: LoginRequest):
    """
    Authenticate user with wallet signature and receive session token.

    Args:
        request: Login request with wallet, signature, and message

    Returns:
        session_token: JWT token valid for 24 hours
        wallet: Authenticated wallet address
    """
    # Verify wallet signature
    if not verify_wallet_signature(request.wallet, request.signature, request.message):
        raise HTTPException(
            status_code=401,
            detail="Invalid signature"
        )

    # Create session token
    session_token = create_session_token(request.wallet)

    logger.info(f"User {request.wallet[:10]}... authenticated successfully")

    return {
        "session_token": session_token,
        "wallet": request.wallet.lower()
    }


@router.post("/{user_id}/create", response_model=CreateResponse)
async def create_user(
    user_id: str,
    request: Request,
    authenticated_wallet: str = Depends(get_authenticated_wallet),
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

    # Verify user can only create their own account
    if authenticated_wallet.lower() != user_id.lower():
        raise HTTPException(
            status_code=403,
            detail="Cannot create account for another wallet"
        )

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
    activate_request: Optional[ActivateRequest] = None,
    strategy_type: Optional[str] = Query(None, description="Strategy code (h1-h2, n1-n6, s1-s2)"),
    allocation_usd: Optional[float] = Query(None, description="Capital allocated to this strategy in USD"),
    authenticated_wallet: str = Depends(get_authenticated_wallet),
    db: AsyncSession = Depends(get_db)
) -> ActivateResponse:
    """
    Activate trading agent for user with strategy selection and capital allocation.

    This will:
    1. Validate and store selected strategy type in user.active_strategies
    2. Set the allocated capital for this strategy
    3. Start the agent process
    4. Enable automated trading based on strategy

    Args:
        user_id: User wallet address
        strategy_type: Strategy short code or full name (h1-h2, n1-n6, s1-s2). Default: n1 (nonhedged_weth_only)
        allocation_usd: Capital allocated to this strategy in USD. Default: 100.0

    Requires user to exist with CDP wallet (use /create first).
    """
    from app.services.agent_management_service import get_agent_service
    from app.schemas.strategy import parse_strategy_type

    # Verify user can only activate their own agent
    if authenticated_wallet.lower() != user_id.lower():
        raise HTTPException(
            status_code=403,
            detail="Cannot activate agent for another wallet"
        )

    try:
        # Support both query params and request body
        # Priority: query params > request body > defaults
        final_strategy_type = strategy_type
        final_allocation_usd = allocation_usd

        if activate_request:
            if not final_strategy_type:
                final_strategy_type = activate_request.strategy_type
            if not final_allocation_usd:
                final_allocation_usd = activate_request.allocation_usd

        # Apply defaults if still not set
        if not final_strategy_type:
            final_strategy_type = "n1"
        if not final_allocation_usd:
            final_allocation_usd = 100.0

        # Validate strategy type
        try:
            strategy_enum = parse_strategy_type(final_strategy_type)
        except ValueError as e:
            return ActivateResponse(
                user_id=user_id,
                status="error",
                message=str(e)
            )

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

        # Activate strategy in relational table (new source of truth)
        from app.services.strategy_service import StrategyService
        strategy_service = StrategyService(db)

        try:
            strategy = await strategy_service.activate_strategy(
                user_id=user_id,
                strategy_type=strategy_enum.value,
                allocated_capital_usd=final_allocation_usd
            )
            logger.info(f"Activated strategy in user_strategies table: {strategy}")
        except ValueError as e:
            logger.error(f"Failed to activate strategy: {e}")
            return ActivateResponse(
                user_id=user_id,
                status="error",
                message=str(e)
            )

        # Sync to JSONB for backward compatibility during migration
        await strategy_service.sync_to_jsonb(user_id)

        # Commit to database BEFORE sending command to agent
        await db.commit()

        # Sync blockchain data before activation
        await service.sync_blockchain_data(user_id)

        # Send activate command to agent manager with selected strategy
        agent_service = get_agent_service()
        result = await agent_service.activate_agent(
            user_id=user_id,
            strategy_type=strategy_enum.value
        )

        if result.get('success'):
            # Update user status to ACTIVE and set agent_status to running
            user.status = 'ACTIVE'
            user.agent_status = 'running'
            user.agent_started_at = datetime.utcnow()
            # Mark JSONB field as modified so SQLAlchemy commits the changes
            attributes.flag_modified(user, 'user_metadata')
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
    request: Request,
    strategy_type: Optional[str] = Query(None, description="Strategy code to deactivate (e.g., h1, h2). If not provided, deactivates all strategies."),
    authenticated_wallet: str = Depends(get_authenticated_wallet),
    db: AsyncSession = Depends(get_db)
) -> DeactivateResponse:
    """
    Deactivate trading agent for user.

    Args:
        user_id: User wallet address
        strategy_type: Optional strategy short code (h1-h3, n1-n3, s1-s2)
                      If provided, only deactivates that specific strategy
                      If None, deactivates all strategies and stops agent

    This will:
    1. If strategy_type provided: Remove that strategy from active_strategies
    2. If no strategy_type: Stop agent process, close all positions, withdraw funds
    """
    # Verify user can only deactivate their own agent
    if authenticated_wallet.lower() != user_id.lower():
        raise HTTPException(
            status_code=403,
            detail="Cannot deactivate agent for another wallet"
        )
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

        # Case 1: Deactivate specific strategy
        if strategy_type:
            from app.schemas.strategy import parse_strategy_type, STRATEGY_SHORT_CODES

            # Validate strategy type
            try:
                strategy_enum = parse_strategy_type(strategy_type)
            except ValueError as e:
                return DeactivateResponse(
                    user_id=user_id,
                    status="error",
                    message=str(e)
                )

            # Get strategy key (short code)
            strategy_key = strategy_type if strategy_type in STRATEGY_SHORT_CODES else strategy_enum.value.split("_")[1] if "_" in strategy_enum.value else strategy_enum.value

            # Deactivate strategy in relational table (new source of truth)
            from app.services.strategy_service import StrategyService
            strategy_service = StrategyService(db)

            try:
                success = await strategy_service.deactivate_strategy(
                    user_id=user_id,
                    strategy_code=strategy_key
                )
                logger.info(f"Deactivated strategy {strategy_key} in user_strategies table: {success}")
            except ValueError as e:
                logger.error(f"Failed to deactivate strategy: {e}")
                return DeactivateResponse(
                    user_id=user_id,
                    status="error",
                    message=str(e)
                )

            # Sync to JSONB for backward compatibility
            await strategy_service.sync_to_jsonb(user_id)

            # Send command to agent manager to stop executing this strategy
            agent_service = get_agent_service()
            strategy_result = await agent_service.deactivate_strategy(
                user_id=user_id,
                strategy_type=strategy_key
            )
            logger.info(f"Deactivate strategy command sent for {user_id}/{strategy_key}: {strategy_result}")

            # Check if there are any remaining active strategies
            remaining_strategies = await strategy_service.get_active_strategies(user_id)

            # If no more active strategies, also stop the agent completely
            if not remaining_strategies or len(remaining_strategies) == 0:
                agent_service = get_agent_service()
                agent_result = await agent_service.deactivate_agent(
                    user_id=user_id,
                    withdraw_funds=True
                )

                user.status = 'SUSPENDED'
                user.agent_status = 'stopped'
                user.agent_stopped_at = datetime.utcnow()
                attributes.flag_modified(user, 'user_metadata')

            await db.commit()

            logger.info(f"Single strategy deactivation complete for {user_id}/{strategy_key}")

            return DeactivateResponse(
                user_id=user_id,
                status="deactivated",
                message=f"Strategy {strategy_type} deactivated successfully"
            )

        # Case 2: Deactivate all strategies and stop agent
        else:
            logger.info(f"Deactivating all strategies for {user_id}")

            # Deactivate all strategies in relational table (new source of truth)
            from app.services.strategy_service import StrategyService
            strategy_service = StrategyService(db)

            active_strategies = await strategy_service.get_active_strategies(user_id)
            logger.info(f"Found {len(active_strategies)} active strategies to deactivate")

            for strategy in active_strategies:
                try:
                    await strategy_service.deactivate_strategy(
                        user_id=user_id,
                        strategy_code=strategy.strategy_code
                    )
                    logger.info(f"Deactivated strategy {strategy.strategy_code}")
                except ValueError as e:
                    logger.error(f"Failed to deactivate strategy {strategy.strategy_code}: {e}")

            # Always update status (even if agent service fails)
            user.status = 'SUSPENDED'
            user.agent_status = 'stopped'
            user.agent_stopped_at = datetime.utcnow()
            attributes.flag_modified(user, 'user_metadata')

            # Sync to JSONB for backward compatibility
            await strategy_service.sync_to_jsonb(user_id)

            logger.info(f"All strategies deactivated for {user_id}")

            logger.info(f"Active_strategies after flush (before commit): {user.active_strategies}")
            logger.info(f"Active_strategies object id after flush: {id(user.active_strategies)}")

            # Verify the update will happen
            from sqlalchemy import inspect
            state = inspect(user)
            logger.info(f"User state after flush: pending={state.pending}, persistent={state.persistent}, detached={state.detached}")
            logger.info(f"Modified attributes: {state.attrs.active_strategies.history}")

            # Commit DB changes first to ensure state is updated
            await db.commit()

            logger.info(f"Commit completed - active_strategies should now be empty in DB")

            logger.info(f"Deactivate commit completed for {user_id}")
            logger.info(f"Active_strategies after commit (should be empty): {user.active_strategies}")

            # Don't refresh - we just committed what we want, refreshing could load stale data from race conditions
            # Verify the clear was successful in memory
            if user.active_strategies:
                logger.error(f"ERROR: active_strategies not empty in memory after commit! Contains: {user.active_strategies}")
            else:
                logger.info(f"SUCCESS: active_strategies cleared successfully in memory")

            # Then send deactivate command to agent manager (always withdraws funds)
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
                # Even if agent service fails, DB state was updated
                logger.warning(f"Agent service deactivation failed for {user_id}, but DB state updated")
                return DeactivateResponse(
                    user_id=user_id,
                    status="deactivated",
                    message=f"Strategies cleared. Agent service: {result.get('error', 'Failed to contact agent')}"
                )

    except Exception as e:
        logger.error(f"Error deactivating agent for {user_id}: {e}")
        return DeactivateResponse(
            user_id=user_id,
            status="error",
            message=str(e)
        )

