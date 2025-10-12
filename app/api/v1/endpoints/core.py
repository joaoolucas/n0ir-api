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

        # Store selected strategy in active_strategies with allocation
        # Use deep copy to ensure JSONB mutation tracking works
        import copy
        from app.schemas.strategy import STRATEGY_SHORT_CODES

        current_strategies = copy.deepcopy(user.active_strategies) if user.active_strategies else {}

        strategy_key = final_strategy_type if final_strategy_type in STRATEGY_SHORT_CODES else strategy_enum.value.split("_")[1] if "_" in strategy_enum.value else strategy_enum.value

        current_strategies[strategy_key] = {
            "strategy_type": strategy_enum.value,
            "status": "active",
            "allocated_capital_usd": float(final_allocation_usd),
            "deployed_capital_usd": 0.0,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        # Reassign to trigger SQLAlchemy change detection
        user.active_strategies = current_strategies
        attributes.flag_modified(user, 'active_strategies')

        # Flush to database before commit
        await db.flush()

        # Commit active_strategies to database BEFORE sending command to agent
        # This ensures the executor sees the updated strategies when it calls get_active_strategies
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

            # Check if strategy exists and is active
            if not user.active_strategies or strategy_key not in user.active_strategies:
                return DeactivateResponse(
                    user_id=user_id,
                    status="error",
                    message=f"Strategy {strategy_type} is not active for this user"
                )

            # Create a new dict with deep copies to ensure SQLAlchemy detects the change (JSONB mutation tracking issue)
            import copy
            new_strategies = copy.deepcopy(user.active_strategies) if user.active_strategies else {}

            # Reset capital allocation to 0 before removing
            if strategy_key in new_strategies and isinstance(new_strategies[strategy_key], dict):
                new_strategies[strategy_key]['allocated_capital_usd'] = 0
                new_strategies[strategy_key]['deployed_capital_usd'] = 0

            # Remove strategy from the new dict
            new_strategies.pop(strategy_key, None)

            # Reassign to trigger SQLAlchemy change detection
            user.active_strategies = new_strategies
            attributes.flag_modified(user, 'active_strategies')

            # Force flush to database before commit
            await db.flush()

            # Send command to agent manager to stop executing this strategy
            agent_service = get_agent_service()
            strategy_result = await agent_service.deactivate_strategy(
                user_id=user_id,
                strategy_type=strategy_key
            )
            logger.info(f"Deactivate strategy command sent for {user_id}/{strategy_key}: {strategy_result}")

            # If no more active strategies, also stop the agent completely
            if not user.active_strategies or len(user.active_strategies) == 0:
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

            # Force expire and refresh to ensure changes persist
            db.expire(user, ['active_strategies'])
            await db.refresh(user)

            logger.info(f"Single strategy deactivation complete for {user_id}/{strategy_key}")
            logger.info(f"Active_strategies after refresh: {user.active_strategies}")

            return DeactivateResponse(
                user_id=user_id,
                status="deactivated",
                message=f"Strategy {strategy_type} deactivated successfully"
            )

        # Case 2: Deactivate all strategies and stop agent
        else:
            logger.info(f"Deactivating all strategies for {user_id}")
            logger.info(f"Current active_strategies before clear: {user.active_strategies}")

            # Always clear strategies and update status first (even if agent service fails)
            user.status = 'SUSPENDED'
            user.agent_status = 'stopped'
            user.agent_stopped_at = datetime.utcnow()
            user.active_strategies = {}  # Assign empty dict to clear all strategies
            attributes.flag_modified(user, 'active_strategies')
            attributes.flag_modified(user, 'user_metadata')

            logger.info(f"Active_strategies after clear (before flush): {user.active_strategies}")

            # Force flush to database before commit
            await db.flush()

            logger.info(f"Active_strategies after flush (before commit): {user.active_strategies}")

            # Commit DB changes first to ensure state is updated
            await db.commit()

            # Force expire the attribute before refresh to ensure we get fresh data
            db.expire(user, ['active_strategies'])
            await db.refresh(user)

            logger.info(f"Deactivate commit completed for {user_id}")
            logger.info(f"Active_strategies after refresh: {user.active_strategies}")

            # Verify the clear was successful
            if user.active_strategies:
                logger.error(f"ERROR: active_strategies not cleared! Still contains: {user.active_strategies}")
            else:
                logger.info(f"SUCCESS: active_strategies cleared successfully")

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

