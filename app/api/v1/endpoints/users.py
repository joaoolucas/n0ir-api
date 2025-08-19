from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from decimal import Decimal
from loguru import logger
from app.database.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.user_service import UserService
from app.services.agent_management_service import AgentManagementService
from app.schemas.users import (
    CreateUserRequest, UpdateUserRequest, DepositRequest, WithdrawRequest,
    UserResponse, TransactionResponse, TransactionListResponse,
    PositionResponse, PositionListResponse, PositionCreateRequest,
    BalanceResponse, PnLResponse, PerformanceResponse,
    ProtocolFeeListResponse, ProtocolFeeResponse,
    UserStatus, TransactionType, TransactionStatus, PositionStatus
)
from app.database.models.transaction import TransactionType as DBTransactionType
from app.database.models.position import PositionStatus as DBPositionStatus
from app.core.logger import logger

router = APIRouter(prefix="/users")


# User Management Endpoints
@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    request: CreateUserRequest,
    db: AsyncSession = Depends(get_db)
):
    """Create a new user and optionally start their agent.
    
    This endpoint intelligently handles user creation:
    - Creates user record with wallet address as ID
    - Optionally starts agent and creates CDP wallet
    - Returns user info with CDP wallet if created
    
    Args:
        user_id: User's wallet address (EOA)
        start_agent: Whether to start agent and create CDP wallet (default: true)
        signature: Optional signature to prove wallet ownership
    """
    
    # Validate wallet address format
    if not request.user_id.startswith("0x") or len(request.user_id) != 42:
        raise HTTPException(status_code=400, detail="Invalid wallet address format")
    
    # TODO: Verify signature to prove wallet ownership (optional but recommended)
    # if request.signature:
    #     verify_wallet_signature(request.user_id, request.signature)
    
    user_service = UserService(db)
    
    # Check if user already exists
    existing_user = await user_service.get_user(request.user_id)
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")
    
    try:
        # Create user with wallet address as ID
        # user_id IS the owner's wallet address
        user = await user_service.create_user(
            user_id=request.user_id,  # This is the user's EOA address
            wallet_address="pending",  # CDP smart wallet (will be created if start_agent=true)
            cdp_wallet_name=f"n0ir-cdp-{request.user_id[:8]}",  # Shortened for readability
            cdp_owner_wallet_address=request.user_id,  # Same as user_id (owner's EOA)
            cdp_owner_wallet_name=f"user-wallet-{request.user_id[:8]}"  # Shortened
        )
        
        # Start agent if requested
        if request.start_agent:
            agent_service = AgentManagementService()
            logger.info(f"Starting agent for user {request.user_id}")
            agent_result = await agent_service.start_agent(request.user_id, wait_for_wallet=True)
            
            if agent_result.get('success'):
                wallet_address = agent_result.get('wallet_address')
                if wallet_address:
                    logger.info(f"CDP wallet created for user {request.user_id}: {wallet_address}")
                    # Update user with actual wallet information
                    user.wallet_address = wallet_address
                else:
                    logger.warning(f"Agent started but no wallet address returned for {request.user_id}")
            else:
                # Log warning but don't fail user creation
                logger.warning(f"Agent start failed for user {request.user_id}: {agent_result.get('error', 'Unknown error')}")
                # User is still created, they can start agent later
        
        return UserResponse.model_validate(user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get user details."""
    service = UserService(db)
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse.model_validate(user)


# Financial Operations
@router.post("/{user_id}/deposit", response_model=TransactionResponse, status_code=201)
async def deposit(
    user_id: str,
    request: DepositRequest,
    db: AsyncSession = Depends(get_db)
):
    """Deposit USDC to user account."""
    try:
        service = UserService(db)
        transaction = await service.deposit_usdc(
            user_id=user_id,
            amount=request.amount_usdc,
            tx_hash=request.tx_hash
        )
        return TransactionResponse.model_validate(transaction)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing deposit: {e}")
        raise HTTPException(status_code=500, detail="Failed to process deposit")


@router.post("/{user_id}/withdraw", response_model=TransactionResponse, status_code=201)
async def withdraw(
    user_id: str,
    request: WithdrawRequest,
    db: AsyncSession = Depends(get_db)
):
    """Withdraw USDC from user account."""
    try:
        service = UserService(db)
        transaction = await service.withdraw_usdc(
            user_id=user_id,
            amount=request.amount_usdc,
            tx_hash=request.tx_hash
        )
        return TransactionResponse.model_validate(transaction)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing withdrawal: {e}")
        raise HTTPException(status_code=500, detail="Failed to process withdrawal")


@router.get("/{user_id}/balance", response_model=BalanceResponse)
async def get_balance(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get user balance."""
    service = UserService(db)
    balance = await service.get_user_balance(user_id)
    if balance is None:
        raise HTTPException(status_code=404, detail="User not found")
    
    return BalanceResponse(
        user_id=user_id,
        balance_usdc=balance,
        available_balance_usdc=balance  # TODO: Calculate available (not in positions)
    )


@router.get("/{user_id}/transactions", response_model=TransactionListResponse)
async def get_transactions(
    user_id: str,
    limit: int = 100,
    offset: int = 0,
    transaction_type: Optional[DBTransactionType] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get user transactions."""
    service = UserService(db)
    transactions = await service.get_user_transactions(
        user_id=user_id,
        limit=limit,
        offset=offset,
        transaction_type=transaction_type
    )
    
    return TransactionListResponse(
        transactions=[TransactionResponse.model_validate(t) for t in transactions],
        total=len(transactions)
    )


# Position Management
@router.post("/{user_id}/positions", response_model=PositionResponse, status_code=201)
async def create_position(
    user_id: str,
    request: PositionCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Create a new position."""
    try:
        service = UserService(db)
        position = await service.create_position(
            user_id=user_id,
            pool_address=request.pool_address,
            entry_amount_usdc=request.entry_amount_usdc,
            leverage=request.leverage,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit
        )
        return PositionResponse.model_validate(position)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating position: {e}")
        raise HTTPException(status_code=500, detail="Failed to create position")


@router.get("/{user_id}/positions", response_model=PositionListResponse)
async def get_positions(
    user_id: str,
    status: Optional[DBPositionStatus] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get user positions."""
    service = UserService(db)
    positions = await service.get_user_positions(user_id, status)
    
    return PositionListResponse(
        positions=[PositionResponse.model_validate(p) for p in positions],
        total=len(positions)
    )


@router.delete("/{user_id}/positions/{position_id}", response_model=PositionResponse)
async def close_position(
    user_id: str,
    position_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Close a position."""
    try:
        service = UserService(db)
        position = await service.close_position(user_id, position_id)
        return PositionResponse.model_validate(position)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error closing position: {e}")
        raise HTTPException(status_code=500, detail="Failed to close position")


# Analytics
@router.get("/{user_id}/pnl", response_model=PnLResponse)
async def get_pnl(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get user P&L summary."""
    service = UserService(db)
    pnl = await service.calculate_user_pnl(user_id)
    
    if pnl is None:
        raise HTTPException(status_code=404, detail="User not found")
    
    return PnLResponse(
        user_id=user_id,
        total_realized_pnl=pnl['realized'],
        total_unrealized_pnl=pnl['unrealized'],
        total_pnl=pnl['total']
    )


@router.get("/{user_id}/performance", response_model=PerformanceResponse)
async def get_performance(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get user performance metrics."""
    service = UserService(db)
    metrics = await service.get_performance_metrics(user_id)
    
    if metrics is None:
        raise HTTPException(status_code=404, detail="User not found")
    
    return PerformanceResponse(
        user_id=user_id,
        total_positions=metrics.get('total_positions', 0),
        winning_positions=metrics.get('winning_positions', 0),
        losing_positions=metrics.get('losing_positions', 0),
        win_rate=metrics.get('win_rate', 0.0),
        average_return=metrics.get('average_return', 0.0),
        best_position_pnl=metrics.get('best_position_pnl', 0.0),
        worst_position_pnl=metrics.get('worst_position_pnl', 0.0),
        total_volume_traded=metrics.get('total_volume', 0.0)
    )


# Protocol Fees
@router.get("/{user_id}/fees", response_model=ProtocolFeeListResponse)
async def get_protocol_fees(
    user_id: str,
    collected: Optional[bool] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get protocol fees for user."""
    service = UserService(db)
    
    # Get fees from positions
    positions = await service.get_user_positions(user_id)
    
    fees = []
    for position in positions:
        if position.protocol_fee_amount and position.protocol_fee_amount > 0:
            if collected is None or position.protocol_fee_collected == collected:
                fees.append(ProtocolFeeResponse(
                    position_id=str(position.position_id or position.nft_token_id),
                    fee_amount_usdc=position.protocol_fee_amount,
                    collected=position.protocol_fee_collected,
                    collection_tx_hash=position.protocol_fee_tx_hash
                ))
    
    total_collected = sum(f.fee_amount_usdc for f in fees if f.collected)
    total_pending = sum(f.fee_amount_usdc for f in fees if not f.collected)
    
    return ProtocolFeeListResponse(
        fees=fees,
        total_collected_usdc=total_collected,
        total_pending_usdc=total_pending
    )