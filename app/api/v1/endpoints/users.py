from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from decimal import Decimal
from loguru import logger
from app.database.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.user_service import UserService
from app.core.pools_service import pools_service
from app.core.positions_service import positions_service
from app.schemas.users import (
    CreateUserRequest, UpdateUserRequest, DepositRequest, WithdrawRequest, WithdrawPreviewResponse,
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
    """Enrich position with pool information, PNL, APR, and calculated values from blockchain."""
    position_dict = PositionResponse.model_validate(position).model_dump()
    
    # Skip blockchain fetch for closed positions - they don't exist on-chain anymore
    if position.status == DBPositionStatus.CLOSED:
        # For closed positions, use database values and calculate final PNL
        try:
            # Get token info for pool name
            token0_info = await pools_service.get_token_info(position.token0_address)
            token1_info = await pools_service.get_token_info(position.token1_address)
            
            # Create pool name from token symbols  
            token0_symbol = token0_info.get('symbol', '???')
            token1_symbol = token1_info.get('symbol', '???')
            position_dict['pool_name'] = f"{token0_symbol}/{token1_symbol}"
        except:
            position_dict['pool_name'] = "Unknown/Unknown"
        
        # Use stored values for closed positions
        position_dict['current_value_usdc'] = position.current_value_usdc or Decimal(0)
        position_dict['current_total_value'] = position.current_value_usdc or Decimal(0)
        position_dict['total_pnl_usdc'] = position.realized_pnl_usdc + position.fees_earned_usdc + position.rewards_earned_usdc
        
        if position.entry_amount_usdc and position.entry_amount_usdc > 0:
            position_dict['pnl_percentage'] = (position_dict['total_pnl_usdc'] / position.entry_amount_usdc) * Decimal(100)
        else:
            position_dict['pnl_percentage'] = Decimal(0)
        
        position_dict['pool_base_apr'] = Decimal(0)
        position_dict['effective_apr'] = Decimal(0)
        
        return position_dict
    
    try:
        # Get real-time position data from blockchain using the singleton service (only for ACTIVE positions)
        try:
            position_info = await positions_service.get_position_by_id(position.nft_token_id)
        except Exception as e:
            # If position doesn't exist on-chain, it was likely closed externally
            if "execution reverted: ID" in str(e) or "ContractLogicError" in str(e):
                logger.error(f"Position {position.nft_token_id} no longer exists on-chain but still marked as {position.status} in database!")
                logger.error("Agent manager should call /users/{user_id}/positions/{nft_token_id}/close when closing positions")
                
                # Return data showing position is likely closed
                position_dict['current_value_usdc'] = Decimal(0)
                position_dict['current_total_value'] = Decimal(0)
                position_dict['pool_name'] = "CLOSED/ERROR"
                position_dict['total_pnl_usdc'] = Decimal(0) - (position.entry_amount_usdc or Decimal(0))
                position_dict['pnl_percentage'] = Decimal(-100)
                position_dict['pool_base_apr'] = Decimal(0)
                position_dict['effective_apr'] = Decimal(0)
                # Add error flag to help frontend handle this case
                position_dict['error'] = "Position not found on-chain - likely closed externally"
                position_dict['needs_sync'] = True
                return position_dict
            else:
                raise  # Re-raise if it's a different error
        
        # Get token info for pool name
        token0_info = await pools_service.get_token_info(position.token0_address)
        token1_info = await pools_service.get_token_info(position.token1_address)
        
        # Create pool name from token symbols  
        token0_symbol = token0_info.get('symbol', '???')
        token1_symbol = token1_info.get('symbol', '???')
        position_dict['pool_name'] = f"{token0_symbol}/{token1_symbol}"
        
        # Use correct values from the positions service
        current_value_usd = Decimal(str(position_info.current_value_usd or 0))
        unclaimed_fees_usd = Decimal(str(position_info.unclaimed_fees_usd or 0))
        
        # Debug logging
        logger.info(f"Position {position.nft_token_id} enrichment: current_value_usd={current_value_usd}, unclaimed_fees_usd={unclaimed_fees_usd}")
        
        # Calculate current_total_value: position value + unclaimed fees + database rewards/fees
        current_total_value = current_value_usd + unclaimed_fees_usd
        
        # Add any accumulated rewards/fees tracked in database (if different from blockchain)
        current_total_value += (position.rewards_earned_usdc or Decimal(0))
        current_total_value += (position.fees_earned_usdc or Decimal(0))
        
        position_dict['current_total_value'] = current_total_value
        
        # Update current_value_usdc with the real-time value for consistency
        position_dict['current_value_usdc'] = current_value_usd
        
        # Calculate PNL
        entry_amount = position.entry_amount_usdc or Decimal(0)
        if entry_amount > 0:
            # Total PNL = current_total_value - entry_amount
            total_pnl = current_total_value - entry_amount
            position_dict['total_pnl_usdc'] = total_pnl
            
            # PNL percentage
            pnl_percentage = (total_pnl / entry_amount) * Decimal(100)
            position_dict['pnl_percentage'] = pnl_percentage
        else:
            position_dict['total_pnl_usdc'] = Decimal(0)
            position_dict['pnl_percentage'] = Decimal(0)
        
        # Get pool info for APR
        try:
            pool = await pools_service.get_pool(position.pool_address)
            if pool:
                base_apr = Decimal(str(pool.get('apr', 0)))
                position_dict['pool_base_apr'] = base_apr
                
                # Calculate effective APR based on position range
                if position.tick_spacing and position_info.in_range:
                    # Import the APR calculator
                    from app.core.effective_apr_calculator import EffectiveAPRCalculator
                    apr_calc = EffectiveAPRCalculator()
                    
                    # Calculate range width in ticks
                    tick_range = position.tick_upper - position.tick_lower
                    
                    # Convert tick range to percentage (approximate)
                    # For a rough approximation: each tick represents ~0.01% price change
                    # This is simplified and could be made more accurate
                    range_percentage = tick_range / 10000  
                    
                    effective_apr = apr_calc.calculate_effective_apr(
                        float(base_apr),
                        position.tick_spacing,
                        range_percentage
                    )
                    position_dict['effective_apr'] = Decimal(str(effective_apr))
                else:
                    # Out of range positions get 0 effective APR
                    position_dict['effective_apr'] = Decimal(0) if not position_info.in_range else base_apr
            else:
                position_dict['pool_base_apr'] = Decimal(0)
                position_dict['effective_apr'] = Decimal(0)
        except Exception as e:
            logger.warning(f"Failed to get APR for pool {position.pool_address}: {e}")
            position_dict['pool_base_apr'] = Decimal(0)
            position_dict['effective_apr'] = Decimal(0)
        
    except Exception as e:
        logger.warning(f"Failed to enrich position {position.nft_token_id}: {e}")
        # Set fallback values if blockchain services fail
        position_dict['pool_name'] = "???/???"
        position_dict['current_total_value'] = position.current_value_usdc or Decimal(0)
        position_dict['total_pnl_usdc'] = Decimal(0)
        position_dict['pnl_percentage'] = Decimal(0)
        position_dict['pool_base_apr'] = Decimal(0)
        position_dict['effective_apr'] = Decimal(0)
    
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
        
        # Agents are now automatically started based on balance
        # No manual agent start needed
        logger.info(f"User {request.user_id} created successfully. Agent will auto-start when balance > {10} USDC")
        
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
    """Withdraw USDC from user account.
    
    This endpoint will automatically close positions if needed to fulfill the withdrawal.
    If tx_hash is provided, the withdrawal is recorded as already executed.
    Otherwise, the withdrawal is executed through the agent manager service.
    
    Args:
        user_id: User's wallet address
        request: Withdrawal request with amount and options
    """
    try:
        service = UserService(db)
        transaction = await service.withdraw_usdc(
            user_id=user_id,
            amount=request.amount_usdc,
            tx_hash=request.tx_hash,
            to_address=request.destination_address,
            force_close_positions=request.force_close_positions,
            max_slippage_percent=request.max_slippage_percent
        )
        return TransactionResponse.model_validate(transaction)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing withdrawal: {e}")
        raise HTTPException(status_code=500, detail="Failed to process withdrawal")


@router.get("/{user_id}/withdraw/preview", response_model=WithdrawPreviewResponse)
async def preview_withdrawal(
    user_id: str,
    amount: Decimal = Query(..., gt=0, description="Amount to withdraw in USDC"),
    db: AsyncSession = Depends(get_db)
):
    """Preview a withdrawal to see what would happen.
    
    Shows whether positions need to be closed, estimated fees, and if withdrawal is possible.
    """
    try:
        service = UserService(db)
        preview = await service.preview_withdrawal(user_id, amount)
        return WithdrawPreviewResponse(**preview)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error previewing withdrawal: {e}")
        raise HTTPException(status_code=500, detail="Failed to preview withdrawal")


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
    
    # Get confirmed balance from database (transaction-based)
    wallet_balance = await service.get_user_balance(user_id)
    
    # Get all confirmed deposits to calculate total deposited to platform
    all_deposits = await service.get_user_transactions(
        user_id=user_id,
        transaction_type=DBTransactionType.DEPOSIT,
        status=DBTransactionStatus.CONFIRMED
    )
    total_deposited = sum(t.amount_usdc for t in all_deposits)
    
    # Get all confirmed withdrawals to calculate net deposits
    all_withdrawals = await service.get_user_transactions(
        user_id=user_id,
        transaction_type=DBTransactionType.WITHDRAW,
        status=DBTransactionStatus.CONFIRMED
    )
    total_withdrawn = sum(t.amount_usdc for t in all_withdrawals)
    
    # Calculate net deposited (deposits minus withdrawals)
    net_deposited = total_deposited - total_withdrawn
    
    # Get active positions to calculate current value and invested amount
    positions = await service.get_user_positions(user_id, status=DBPositionStatus.ACTIVE)
    
    # Calculate invested amount from ACTIVE positions only (entry amounts)
    invested_in_pools = sum(p.entry_amount_usdc or Decimal(0) for p in positions)
    
    # Calculate total positions value using real-time blockchain data
    current_positions_value = Decimal(0)
    
    for position in positions:
        try:
            # Use the same enrichment logic to get real-time values
            position_info = await positions_service.get_position_by_id(position.nft_token_id)
            
            current_value_usd = Decimal(str(position_info.current_value_usd or 0))
            unclaimed_fees_usd = Decimal(str(position_info.unclaimed_fees_usd or 0))
            
            # Calculate total position value: blockchain value + unclaimed fees + database rewards/fees
            position_total = current_value_usd + unclaimed_fees_usd
            position_total += (position.rewards_earned_usdc or Decimal(0))
            position_total += (position.fees_earned_usdc or Decimal(0))
            
            current_positions_value += position_total
            
        except Exception as e:
            # Check if position was closed externally
            if "execution reverted: ID" in str(e) or "ContractLogicError" in str(e):
                logger.error(f"Position {position.nft_token_id} not found on-chain during balance calculation - assuming closed with 0 value")
                # Don't add any value for positions that don't exist on-chain
                # This prevents inflating the balance with phantom positions
            else:
                logger.warning(f"Failed to get value for position {position.nft_token_id}: {e}")
                # For other errors, use a conservative fallback
                fallback_value = position.current_value_usdc or Decimal(0)
                current_positions_value += fallback_value
    
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
    
    # Calculate available balance (wallet balance is all available since position funds are tracked separately)
    available_balance = wallet_balance - pending_withdrawals_amount
    
    # Calculate total portfolio value (wallet + positions)
    total_portfolio_value = wallet_balance + current_positions_value
    
    # Balance endpoint now only returns portfolio balances without PnL calculations
    # PnL calculations are available through the dedicated /pnl endpoint
    
    return BalanceResponse(
        user_id=user_id,
        wallet_balance_usdc=wallet_balance,
        available_balance_usdc=available_balance,
        invested_amount_usdc=invested_in_pools,  # Amount actually invested in pools
        current_positions_value_usdc=current_positions_value,
        total_portfolio_value_usdc=total_portfolio_value,
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
            pool_name=request.pool_name,
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


@router.delete("/{user_id}/positions/{nft_token_id}", response_model=PositionResponse)
async def close_position(
    user_id: str,
    nft_token_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Close a position and return funds to user balance."""
    try:
        service = UserService(db)
        position = await service.close_position(
            user_id=user_id,
            nft_token_id=nft_token_id
        )
        if not position:
            raise HTTPException(status_code=404, detail="Position not found or already closed")
        
        # Enrich the closed position with pool data
        enriched_position = await enrich_position_with_pool_data(position)
        return PositionResponse.model_validate(enriched_position)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{user_id}/positions/sync", status_code=200)
async def sync_positions(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Sync positions with blockchain state and update values.
    
    Checks all active positions and marks any that don't exist on-chain as closed.
    This helps recover from situations where positions were closed externally.
    """
    service = UserService(db)
    positions = await service.get_user_positions(user_id, status=DBPositionStatus.ACTIVE)
    
    # Sync position values with blockchain
    await service.sync_position_values(user_id)
    
    # Also check for positions closed externally
    closed_positions = []
    for position in positions:
        try:
            # Try to fetch position from blockchain
            await positions_service.get_position_by_id(position.nft_token_id)
            # Position exists, values already synced above
        except Exception as e:
            if "execution reverted: ID" in str(e) or "ContractLogicError" in str(e):
                # Position doesn't exist on-chain, mark as closed
                logger.warning(f"Syncing position {position.nft_token_id} - marking as closed")
                await service.update_position_status(position.nft_token_id, DBPositionStatus.CLOSED)
                closed_positions.append(position.nft_token_id)
    
    # Recalculate user PnL after syncing
    await service.recalculate_user_pnl(user_id)
    
    return {
        "positions_updated": len(positions) - len(closed_positions),
        "positions_closed": closed_positions,
        "message": f"Synced {len(positions)} positions, {len(closed_positions)} were closed externally"
    }


# Analytics
@router.get("/{user_id}/pnl", response_model=PnLResponse)
async def get_pnl(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get user P&L summary with real-time position values.
    
    This endpoint recalculates PnL using current blockchain position values
    to ensure accurate unrealized PnL based on market conditions.
    """
    service = UserService(db)
    
    # Verify user exists
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Recalculate PnL with real-time position values from blockchain
    await service.recalculate_user_pnl(user_id)
    
    # Refresh user to get updated values
    await db.refresh(user)
    
    # Get fees and rewards from positions for additional metrics
    positions = await service.get_user_positions(user_id)
    
    # Calculate total fees and rewards from all positions
    total_fees_earned = sum(p.fees_earned_usdc or Decimal(0) for p in positions)
    total_rewards_earned = sum(p.rewards_earned_usdc or Decimal(0) for p in positions)
    
    # Get protocol fees pending
    protocol_fees_pending = sum(
        p.protocol_fee_amount for p in positions 
        if p.protocol_fee_amount and not p.protocol_fee_collected
    )
    
    # Calculate total PnL (realized + unrealized)
    total_pnl = user.realized_pnl_usdc + user.unrealized_pnl_usdc
    
    # Net PnL after protocol fees
    net_pnl = total_pnl - protocol_fees_pending
    
    return PnLResponse(
        realized_pnl_usdc=user.realized_pnl_usdc,
        unrealized_pnl_usdc=user.unrealized_pnl_usdc,
        unrealized_pnl_percentage=user.unrealized_pnl_percentage,
        realized_pnl_percentage=user.realized_pnl_percentage,
        fees_earned_usdc=total_fees_earned,
        rewards_earned_usdc=total_rewards_earned,
        total_pnl_usdc=total_pnl,
        protocol_fees_pending_usdc=protocol_fees_pending,
        net_pnl_usdc=net_pnl
    )


@router.get("/{user_id}/pnl-details", response_model=Dict[str, Decimal])
async def get_pnl_details(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get detailed PnL values with real-time position values.
    
    Returns all PnL metrics including percentages, recalculated with
    current blockchain position values.
    """
    service = UserService(db)
    user = await service.get_user(user_id)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Recalculate PnL with real-time position values
    await service.recalculate_user_pnl(user_id)
    
    # Refresh user to get updated values
    await db.refresh(user)
    
    return {
        "unrealized_pnl_usdc": user.unrealized_pnl_usdc,
        "realized_pnl_usdc": user.realized_pnl_usdc,
        "unrealized_pnl_percentage": user.unrealized_pnl_percentage,
        "realized_pnl_percentage": user.realized_pnl_percentage,
        "last_updated": user.updated_at
    }


@router.post("/{user_id}/sync-pnl", status_code=200)
async def sync_user_pnl(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Manually trigger PnL recalculation for a user.
    
    This will fetch current balances, positions, and transactions to recalculate
    and update the stored PnL values. Normally this happens automatically on
    deposits, withdrawals, and position changes.
    """
    service = UserService(db)
    
    # Verify user exists
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Recalculate and update PnL
    await service.recalculate_user_pnl(user_id)
    
    # Return updated values
    await db.refresh(user)
    
    return {
        "message": "PnL values synced successfully",
        "unrealized_pnl_usdc": user.unrealized_pnl_usdc,
        "realized_pnl_usdc": user.realized_pnl_usdc,
        "unrealized_pnl_percentage": user.unrealized_pnl_percentage,
        "realized_pnl_percentage": user.realized_pnl_percentage,
        "last_updated": user.updated_at
    }


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