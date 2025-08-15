from typing import Optional, List
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.services.user_service import UserService
from app.schemas.users import (
    CreateUserRequest, UserResponse,
    DepositRequest, WithdrawRequest, BalanceResponse,
    CreatePositionRequest, ClosePositionRequest,
    PositionResponse, PositionListResponse,
    TransactionResponse, TransactionListResponse,
    PnLResponse, PerformanceResponse,
    ProtocolFeeResponse, ProtocolFeeListResponse,
    TransactionType, TransactionStatus, PositionStatus
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
    """Create a new user with CDP wallet."""
    try:
        service = UserService(db)
        user = await service.create_user(
            user_id=request.user_id,
            wallet_address=request.wallet_address,
            cdp_wallet_name=request.cdp_wallet_name,
            cdp_owner_wallet_address=request.cdp_owner_wallet_address,
            cdp_owner_wallet_name=request.cdp_owner_wallet_name
        )
        return UserResponse.model_validate(user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        raise HTTPException(status_code=500, detail="Failed to create user")


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str = Path(..., description="User ID"),
    db: AsyncSession = Depends(get_db)
):
    """Get user profile by ID."""
    service = UserService(db)
    user = await service.get_user(user_id)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserResponse.model_validate(user)




# Wallet Operations
@router.post("/{user_id}/deposit", response_model=TransactionResponse, status_code=201)
async def deposit_usdc(
    user_id: str = Path(..., description="User ID"),
    request: DepositRequest = ...,
    db: AsyncSession = Depends(get_db)
):
    """Deposit USDC to user wallet."""
    service = UserService(db)
    
    # Verify user exists
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Create deposit transaction
    transaction = await service.create_transaction(
        user_id=user_id,
        transaction_type=DBTransactionType.DEPOSIT,
        amount_usdc=request.amount_usdc,
        tx_hash=request.tx_hash
    )
    
    return TransactionResponse.model_validate(transaction)


@router.post("/{user_id}/withdraw", response_model=TransactionResponse, status_code=201)
async def withdraw_usdc(
    user_id: str = Path(..., description="User ID"),
    request: WithdrawRequest = ...,
    db: AsyncSession = Depends(get_db)
):
    """Withdraw USDC from user wallet."""
    service = UserService(db)
    
    # Verify user exists
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check balance
    balance = await service.get_user_balance(user_id)
    if balance < request.amount_usdc:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    
    # Create withdrawal transaction
    metadata = {"destination": request.destination_address} if request.destination_address else None
    transaction = await service.create_transaction(
        user_id=user_id,
        transaction_type=DBTransactionType.WITHDRAW,
        amount_usdc=request.amount_usdc,
        metadata=metadata
    )
    
    return TransactionResponse.model_validate(transaction)


@router.get("/{user_id}/balance", response_model=BalanceResponse)
async def get_user_balance(
    user_id: str = Path(..., description="User ID"),
    db: AsyncSession = Depends(get_db)
):
    """Get user's current balance."""
    service = UserService(db)
    
    # Verify user exists
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get balance and positions
    balance = await service.get_user_balance(user_id)
    positions = await service.get_user_positions(user_id, status=DBPositionStatus.ACTIVE)
    
    # Calculate locked and pending amounts
    locked_in_positions = sum(p.entry_amount_usdc for p in positions)
    
    # Get pending transactions
    from app.database.models.transaction import TransactionStatus as DBTransactionStatus
    pending_deposits = await service.get_user_transactions(
        user_id, 
        transaction_type=DBTransactionType.DEPOSIT,
        status=DBTransactionStatus.PENDING
    )
    pending_withdrawals = await service.get_user_transactions(
        user_id,
        transaction_type=DBTransactionType.WITHDRAW,
        status=DBTransactionStatus.PENDING
    )
    
    pending_deposits_amount = sum(t.amount_usdc for t in pending_deposits)
    pending_withdrawals_amount = sum(t.amount_usdc for t in pending_withdrawals)
    
    return BalanceResponse(
        user_id=user_id,
        balance_usdc=balance,
        available_balance_usdc=balance - locked_in_positions,
        locked_in_positions_usdc=locked_in_positions,
        pending_deposits_usdc=pending_deposits_amount,
        pending_withdrawals_usdc=pending_withdrawals_amount
    )


# Transaction History
@router.get("/{user_id}/transactions", response_model=TransactionListResponse)
async def get_user_transactions(
    user_id: str = Path(..., description="User ID"),
    transaction_type: Optional[TransactionType] = Query(None, description="Filter by transaction type"),
    status: Optional[TransactionStatus] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000, description="Number of results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: AsyncSession = Depends(get_db)
):
    """Get user's transaction history."""
    service = UserService(db)
    
    # Verify user exists
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Convert enums if provided
    db_transaction_type = DBTransactionType(transaction_type.value) if transaction_type else None
    from app.database.models.transaction import TransactionStatus as DBTransactionStatus
    db_status = DBTransactionStatus(status.value) if status else None
    
    # Get transactions
    transactions = await service.get_user_transactions(
        user_id=user_id,
        transaction_type=db_transaction_type,
        status=db_status,
        limit=limit,
        offset=offset
    )
    
    return TransactionListResponse(
        transactions=[TransactionResponse.model_validate(t) for t in transactions],
        total=len(transactions),
        offset=offset,
        limit=limit
    )




# Position Management
@router.post("/{user_id}/positions", response_model=PositionResponse, status_code=201)
async def create_position(
    user_id: str = Path(..., description="User ID"),
    request: CreatePositionRequest = ...,
    db: AsyncSession = Depends(get_db)
):
    """Create a new position."""
    service = UserService(db)
    
    # Verify user exists
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check balance
    balance = await service.get_user_balance(user_id)
    if balance < request.entry_amount_usdc:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    
    # Create position
    position = await service.create_position(
        user_id=user_id,
        nft_token_id=request.nft_token_id,
        pool_address=request.pool_address,
        token0_address=request.token0_address,
        token1_address=request.token1_address,
        tick_lower=request.tick_lower,
        tick_upper=request.tick_upper,
        tick_spacing=request.tick_spacing,
        liquidity=request.liquidity,
        entry_amount_usdc=request.entry_amount_usdc,
        entry_tx_hash=request.entry_tx_hash,
        staked=request.staked,
        gauge_address=request.gauge_address
    )
    
    # Create position entry transaction
    await service.create_transaction(
        user_id=user_id,
        transaction_type=DBTransactionType.POSITION_ENTRY,
        amount_usdc=request.entry_amount_usdc,
        tx_hash=request.entry_tx_hash,
        metadata={"position_id": str(position.position_id)}
    )
    
    return PositionResponse.model_validate(position)


@router.get("/{user_id}/positions", response_model=PositionListResponse)
async def get_user_positions(
    user_id: str = Path(..., description="User ID"),
    status: Optional[PositionStatus] = Query(None, description="Filter by position status"),
    pool_address: Optional[str] = Query(None, description="Filter by pool address"),
    staked: Optional[bool] = Query(None, description="Filter by staking status"),
    db: AsyncSession = Depends(get_db)
):
    """Get user's positions."""
    service = UserService(db)
    
    # Verify user exists
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Convert status enum if provided
    db_status = DBPositionStatus(status.value) if status else None
    
    # Get positions
    positions = await service.get_user_positions(
        user_id=user_id,
        status=db_status,
        pool_address=pool_address,
        staked=staked
    )
    
    return PositionListResponse(
        positions=[PositionResponse.model_validate(p) for p in positions],
        total=len(positions)
    )






@router.delete("/{user_id}/positions/{position_id}", response_model=PositionResponse)
async def close_position(
    user_id: str = Path(..., description="User ID"),
    position_id: UUID = Path(..., description="Position ID"),
    request: ClosePositionRequest = ...,
    db: AsyncSession = Depends(get_db)
):
    """Exit/close a position."""
    service = UserService(db)
    
    # Verify position belongs to user
    positions = await service.get_user_positions(user_id)
    if not any(p.position_id == position_id for p in positions):
        raise HTTPException(status_code=404, detail="Position not found")
    
    # Close position
    position = await service.close_position(
        position_id=position_id,
        exit_tx_hash=request.exit_tx_hash,
        realized_pnl_usdc=request.realized_pnl_usdc,
        final_value_usdc=request.final_value_usdc
    )
    
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    
    # Create position exit transaction
    await service.create_transaction(
        user_id=user_id,
        transaction_type=DBTransactionType.POSITION_EXIT,
        amount_usdc=request.final_value_usdc,
        tx_hash=request.exit_tx_hash,
        metadata={"position_id": str(position_id)}
    )
    
    return PositionResponse.model_validate(position)


# Performance and Analytics
@router.get("/{user_id}/pnl", response_model=PnLResponse)
async def get_user_pnl(
    user_id: str = Path(..., description="User ID"),
    db: AsyncSession = Depends(get_db)
):
    """Get user's PnL breakdown."""
    service = UserService(db)
    
    # Verify user exists
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get performance data
    performance = await service.calculate_user_performance(user_id)
    
    total_pnl = Decimal(str(performance["total_pnl"]))
    protocol_fees = Decimal(str(performance["total_protocol_fees_pending"]))
    
    return PnLResponse(
        realized_pnl_usdc=Decimal(str(performance["total_realized_pnl"])),
        unrealized_pnl_usdc=Decimal(str(performance["total_unrealized_pnl"])),
        fees_earned_usdc=Decimal(str(performance["total_fees_earned"])),
        rewards_earned_usdc=Decimal(str(performance["total_rewards_earned"])),
        total_pnl_usdc=total_pnl,
        protocol_fees_pending_usdc=protocol_fees,
        net_pnl_usdc=total_pnl - protocol_fees
    )


@router.get("/{user_id}/performance", response_model=PerformanceResponse)
async def get_user_performance(
    user_id: str = Path(..., description="User ID"),
    db: AsyncSession = Depends(get_db)
):
    """Get complete performance metrics."""
    service = UserService(db)
    
    # Verify user exists
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get performance data
    performance = await service.calculate_user_performance(user_id)
    
    return PerformanceResponse.from_service_data(performance)


# Protocol Fees
@router.get("/{user_id}/fees", response_model=ProtocolFeeListResponse)
async def get_user_fees(
    user_id: str = Path(..., description="User ID"),
    collected: Optional[bool] = Query(None, description="Filter by collection status"),
    db: AsyncSession = Depends(get_db)
):
    """Get user's protocol fees."""
    service = UserService(db)
    
    # Verify user exists
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get fees based on filter
    if collected is False:
        fees = await service.get_uncollected_fees(user_id)
    else:
        # Get all fees (implementation would need to be added to service)
        fees = await service.get_uncollected_fees(user_id)  # Simplified for now
    
    total_pending = sum(f.fee_amount_usdc for f in fees if not f.collected)
    total_collected = sum(f.fee_amount_usdc for f in fees if f.collected)
    
    return ProtocolFeeListResponse(
        fees=[ProtocolFeeResponse.model_validate(f) for f in fees],
        total_pending=total_pending,
        total_collected=total_collected
    )