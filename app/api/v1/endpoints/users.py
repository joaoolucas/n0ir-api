from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from decimal import Decimal
from loguru import logger
from app.database.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.user_service import UserService
from app.services.agent_management_service import get_agent_service
from app.core.pools_service import pools_service
from app.schemas.users import (
    CreateUserRequest, UpdateUserRequest, DepositRequest, WithdrawRequest,
    UserResponse, TransactionResponse, TransactionListResponse,
    PositionResponse, PositionListResponse, CreatePositionRequest,
    BalanceResponse, PnLResponse, PerformanceResponse,
    ProtocolFeeListResponse, ProtocolFeeResponse,
    UserStatus, TransactionType, TransactionStatus, PositionStatus
)
from app.database.models.transaction import TransactionType as DBTransactionType, TransactionStatus as DBTransactionStatus
from app.database.models.position import PositionStatus as DBPositionStatus
from app.core.logger import logger

router = APIRouter(prefix="/users")


async def enrich_position_with_pool_data(position) -> dict:
    """Enrich position with pool information and calculated values."""
    position_dict = PositionResponse.model_validate(position).model_dump()
    
    try:
        # Get token info for pool name
        token0_info = await pools_service.get_token_info(position.token0_address)
        token1_info = await pools_service.get_token_info(position.token1_address)
        
        # Create pool name from token symbols  
        token0_symbol = token0_info.get('symbol', '???')
        token1_symbol = token1_info.get('symbol', '???')
        position_dict['pool_name'] = f"{token0_symbol}/{token1_symbol}"
        
        # Calculate current_total_value (position value + emissions)
        # For staked positions, we need to add estimated rewards/emissions value
        current_total_value = position.current_value_usdc or Decimal(0)
        
        if position.staked and position.current_value_usdc:
            # Add accumulated rewards and fees to get total value
            current_total_value += (position.rewards_earned_usdc or Decimal(0))
            current_total_value += (position.fees_earned_usdc or Decimal(0))
        
        position_dict['current_total_value'] = current_total_value
        
    except Exception as e:
        logger.warning(f"Failed to enrich position {position.nft_token_id}: {e}")
        # Set fallback values if pool service fails
        position_dict['pool_name'] = "???/???"
        position_dict['current_total_value'] = position.current_value_usdc
    
    return position_dict


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
            cdp_wallet_address=f"pending_{request.user_id}",  # Unique placeholder for CDP smart wallet
            cdp_wallet_name=f"n0ir-agent-{request.user_id[:8]}"  # Shortened for readability
        )
        
        # Start agent if requested
        if request.start_agent:
            agent_service = get_agent_service()
            logger.info(f"Starting agent for user {request.user_id}")
            agent_result = await agent_service.start_agent(request.user_id, wait_for_wallet=True)
            
            if agent_result.get('success'):
                wallet_address = agent_result.get('wallet_address')
                if wallet_address:
                    logger.info(f"CDP wallet created for user {request.user_id}: {wallet_address}")
                    # Update user with actual wallet information
                    user.cdp_wallet_address = wallet_address
                    # Commit the wallet address update to database
                    await db.commit()
                    await db.refresh(user)
                else:
                    logger.warning(f"Agent started but no CDP wallet address returned for {request.user_id}")
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


@router.post("/{user_id}/retry-wallet", response_model=UserResponse)
async def retry_wallet_creation(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Retry CDP wallet creation for an existing user.
    
    Use this endpoint when:
    - User was created but wallet creation timed out
    - Agent-manager was down during initial user creation
    - CDP wallet is still 'pending'
    """
    service = UserService(db)
    user = await service.get_user(user_id)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if wallet already exists
    if user.cdp_wallet_address and not user.cdp_wallet_address.startswith("pending_"):
        raise HTTPException(
            status_code=400, 
            detail=f"User already has CDP wallet: {user.cdp_wallet_address}"
        )
    
    # Try to create wallet via agent
    agent_service = get_agent_service()
    logger.info(f"Retrying CDP wallet creation for user {user_id}")
    
    agent_result = await agent_service.start_agent(user_id, wait_for_wallet=True)
    
    if agent_result.get('success'):
        wallet_address = agent_result.get('wallet_address')
        if wallet_address:
            logger.info(f"CDP wallet created for user {user_id}: {wallet_address}")
            
            # Update user with wallet address
            user.cdp_wallet_address = wallet_address
            await db.commit()
            await db.refresh(user)
            
            return UserResponse.model_validate(user)
        else:
            raise HTTPException(
                status_code=500,
                detail="Agent started but no wallet address returned"
            )
    else:
        raise HTTPException(
            status_code=500,
            detail=f"Wallet creation failed: {agent_result.get('error', 'Unknown error')}"
        )


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
    """Withdraw USDC from user account.
    
    If tx_hash is provided, the withdrawal is recorded as already executed.
    Otherwise, the withdrawal is executed through the agent manager service.
    """
    try:
        service = UserService(db)
        transaction = await service.withdraw_usdc(
            user_id=user_id,
            amount=request.amount_usdc,
            tx_hash=request.tx_hash,
            to_address=request.destination_address
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
    
    # Verify user exists
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get confirmed balance
    balance = await service.get_user_balance(user_id)
    
    # Get active positions to calculate locked amount
    positions = await service.get_user_positions(user_id, status=DBPositionStatus.ACTIVE)
    locked_in_positions = sum(p.entry_amount_usdc for p in positions)
    
    # Get pending transactions
    pending_deposits = await service.get_user_transactions(
        user_id=user_id,
        transaction_type=DBTransactionType.DEPOSIT,
        status=DBTransactionStatus.PENDING
    )
    pending_deposits_amount = sum(t.amount_usdc for t in pending_deposits)
    
    pending_withdrawals = await service.get_user_transactions(
        user_id=user_id,
        transaction_type=DBTransactionType.WITHDRAW,
        status=DBTransactionStatus.PENDING
    )
    pending_withdrawals_amount = sum(t.amount_usdc for t in pending_withdrawals)
    
    # Calculate available balance (balance not locked in positions)
    available_balance = balance - locked_in_positions
    
    return BalanceResponse(
        user_id=user_id,
        balance_usdc=balance,
        available_balance_usdc=available_balance,
        locked_in_positions_usdc=locked_in_positions,
        pending_deposits_usdc=pending_deposits_amount,
        pending_withdrawals_usdc=pending_withdrawals_amount
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
        total=len(transactions),
        offset=offset,
        limit=limit
    )


# Position Management
@router.post("/{user_id}/positions", response_model=PositionResponse, status_code=201)
async def create_position(
    user_id: str,
    request: CreatePositionRequest,
    db: AsyncSession = Depends(get_db)
):
    """Create a new position."""
    try:
        service = UserService(db)
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
        # Enrich the newly created position with pool data
        enriched_position = await enrich_position_with_pool_data(position)
        return PositionResponse.model_validate(enriched_position)
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
    """Get user positions with enriched pool data."""
    service = UserService(db)
    positions = await service.get_user_positions(user_id, status)
    
    # Enrich positions with pool data
    enriched_positions = []
    for position in positions:
        enriched_position = await enrich_position_with_pool_data(position)
        enriched_positions.append(PositionResponse.model_validate(enriched_position))
    
    return PositionListResponse(
        positions=enriched_positions,
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
        # Enrich the closed position with pool data
        enriched_position = await enrich_position_with_pool_data(position)
        return PositionResponse.model_validate(enriched_position)
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
    
    # Verify user exists
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    pnl = await service.calculate_user_pnl(user_id)
    
    # Get protocol fees
    positions = await service.get_user_positions(user_id)
    protocol_fees_pending = sum(
        p.protocol_fee_amount for p in positions 
        if p.protocol_fee_amount and not p.protocol_fee_collected
    )
    
    net_pnl = pnl['total'] - protocol_fees_pending
    
    return PnLResponse(
        realized_pnl_usdc=pnl['realized'],
        unrealized_pnl_usdc=pnl['unrealized'],
        fees_earned_usdc=pnl['fees'],
        rewards_earned_usdc=pnl['rewards'],
        total_pnl_usdc=pnl['total'],
        protocol_fees_pending_usdc=protocol_fees_pending,
        net_pnl_usdc=net_pnl
    )


@router.get("/{user_id}/performance", response_model=PerformanceResponse)
async def get_performance(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get user performance metrics."""
    service = UserService(db)
    
    # Verify user exists
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    metrics = await service.get_performance_metrics(user_id)
    
    return PerformanceResponse.from_service_data(metrics)


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