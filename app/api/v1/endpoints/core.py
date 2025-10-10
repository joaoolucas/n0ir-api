"""
Core API endpoints for essential user operations.
Handles user creation, activation, and strategy generation.
"""
from typing import Optional
from decimal import Decimal
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
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
    request: Request,
    strategy_type: Optional[str] = "h3",
    authenticated_wallet: str = Depends(get_authenticated_wallet),
    db: AsyncSession = Depends(get_db)
) -> ActivateResponse:
    """
    Activate trading agent for user with strategy selection.

    This will:
    1. Validate and store selected strategy type in user.active_strategies
    2. Start the agent process
    3. Enable automated trading based on strategy

    Args:
        user_id: User wallet address
        strategy_type: Strategy short code or full name (h1-h3, n1-n3, s1-s2). Default: h3 (hedged_blueprint)

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
        # Validate strategy type
        try:
            strategy_enum = parse_strategy_type(strategy_type)
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

        # Store selected strategy in active_strategies
        if not user.active_strategies:
            user.active_strategies = {}

        strategy_key = strategy_type if strategy_type in ["h1", "h2", "h3", "n1", "n2", "n3", "s1", "s2"] else strategy_enum.value.split("_")[1] if "_" in strategy_enum.value else strategy_enum.value

        user.active_strategies[strategy_key] = {
            "strategy_type": strategy_enum.value,
            "status": "active",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        attributes.flag_modified(user, 'active_strategies')

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
    authenticated_wallet: str = Depends(get_authenticated_wallet),
    db: AsyncSession = Depends(get_db)
) -> DeactivateResponse:
    """
    Deactivate trading agent for user.

    This will:
    1. Stop the agent process
    2. Close all open positions
    3. Withdraw all funds to user's wallet
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

        # Send deactivate command to agent manager (always withdraws funds)
        agent_service = get_agent_service()
        result = await agent_service.deactivate_agent(
            user_id=user_id,
            withdraw_funds=True  # Always withdraw all funds
        )

        if result.get('success'):
            # Update user status to SUSPENDED and set agent_status to stopped
            user.status = 'SUSPENDED'
            user.agent_status = 'stopped'
            user.agent_stopped_at = datetime.utcnow()
            # Mark JSONB field as modified so SQLAlchemy commits the changes
            attributes.flag_modified(user, 'user_metadata')
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


@router.get("/{user_id}/active-strategies")
async def get_active_strategies(
    user_id: str,
    authenticated_wallet: str = Depends(get_authenticated_wallet),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user's active strategies configuration.

    Returns the user's active_strategies JSONB field containing
    all strategies the user has activated.

    Example response:
    {
        "user_id": "0x123...",
        "active_strategies": {
            "h3": {
                "strategy_type": "hedged_blueprint",
                "status": "active",
                "created_at": "2025-10-10T12:00:00Z",
                "updated_at": "2025-10-10T12:00:00Z"
            }
        }
    }
    """
    # Verify user can only access their own strategies
    if authenticated_wallet.lower() != user_id.lower():
        raise HTTPException(
            status_code=403,
            detail="Cannot access strategies for another wallet"
        )

    try:
        service = UserService(db)
        user = await service.get_user(user_id)

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Return active strategies, default to empty dict if None
        active_strategies = user.active_strategies or {}

        logger.info(f"Retrieved active strategies for {user_id}: {len(active_strategies)} active")

        return {
            "user_id": user_id,
            "active_strategies": active_strategies
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching active strategies for {user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch active strategies: {str(e)}"
        )

