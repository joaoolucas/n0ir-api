from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
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
    PositionResponse, PositionListResponse, CreatePositionRequest, ClosePositionRequest,
    BalanceResponse, PnLResponse, PerformanceResponse,
    ProtocolFeeListResponse, ProtocolFeeResponse,
    UserStatus, TransactionType, TransactionStatus, PositionStatus
)
# Enums are already imported from schemas above
DBTransactionType = TransactionType
DBTransactionStatus = TransactionStatus
DBPositionStatus = PositionStatus
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
@router.get("", response_model=List[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db)
):
    """List all users with their current balances.
    
    This endpoint is used by the balance monitor to track which agents should be running.
    """
    service = UserService(db)
    users = await service.list_all_users()
    
    # Get balance for each user
    users_with_balance = []
    for user in users:
        balance = await service.get_user_balance(user.user_id)
        user_dict = UserResponse.model_validate(user).model_dump()
        user_dict['usdc_balance'] = float(balance)
        users_with_balance.append(user_dict)
    
    return users_with_balance


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
        
        # Immediately request CDP wallet creation from agent manager
        from app.services.agent_management_service import get_agent_service
        agent_service = get_agent_service()
        
        logger.info(f"Requesting CDP wallet creation for user {request.user_id}")
        wallet_result = await agent_service.create_wallet_for_user(request.user_id)
        
        if wallet_result.get('success') and wallet_result.get('wallet_address'):
            # Update user with real wallet address
            await user_service.update_user_wallet(request.user_id, wallet_result['wallet_address'])
            user.cdp_wallet_address = wallet_result['wallet_address']
            logger.info(f"CDP wallet created immediately for {request.user_id}: {wallet_result['wallet_address']}")
        elif wallet_result.get('error') == 'timeout':
            logger.info(f"CDP wallet creation timed out for {request.user_id}, will update asynchronously")
            # Continue with pending address - will be updated via event listener
        else:
            logger.warning(f"Failed to create CDP wallet for {request.user_id}: {wallet_result.get('error')}")
            # Continue with pending address
        
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
# NOTE: Deposit and withdrawal endpoints removed - these are now tracked automatically by the watcher from blockchain events

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
            max_slippage_percent=request.max_slippage_percent,
            withdraw_all=request.withdraw_all
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
        transaction_type=DBTransactionType.WITHDRAWAL,
        status=DBTransactionStatus.CONFIRMED
    )
    total_withdrawn = sum(t.amount_usdc for t in all_withdrawals)
    
    # Calculate net deposited (deposits minus withdrawals)
    net_deposited = total_deposited - total_withdrawn
    
    # Get active positions to calculate current value and invested amount
    positions = await service.get_user_positions(user_id, status='ACTIVE')
    
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
        transaction_type=DBTransactionType.WITHDRAWAL,
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
    sort_order: str = "desc",  # "asc" for oldest first, "desc" for newest first
    db: AsyncSession = Depends(get_db)
):
    """Get user transactions with AERO swaps linked to position closures."""
    service = UserService(db)
    transactions = await service.get_user_transactions(
        user_id=user_id,
        limit=limit,
        offset=offset,
        transaction_type=transaction_type,
        sort_order=sort_order
    )
    
    # Since the database has the old schema where pool_name is a direct column in transactions,
    # and transactions don't have event_data or tx_type columns, we don't need to do any
    # additional processing. The pool_name is already available in the transaction objects.
    
    return TransactionListResponse(
        transactions=[TransactionResponse.model_validate(t) for t in transactions],
        total=len(transactions),
        offset=offset,
        limit=limit
    )


# Position Management
# NOTE: Position intent endpoint removed - positions are now tracked automatically by the watcher from blockchain events

@router.get("/{user_id}/positions", response_model=PositionListResponse)
async def get_positions(
    user_id: str,
    status: Optional[DBPositionStatus] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get user positions.
    
    During transition: Uses existing positions from public schema.
    Eventually: Will read from blockchain schema once watcher populates it.
    """
    service = UserService(db)
    
    # For now, use the existing service method which reads from public.positions
    # Once the watcher has backfilled blockchain.positions, we can switch
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


# NOTE: Close position endpoint removed - position closes are detected automatically by the watcher from blockchain events

# Position sync endpoint removed - positions are now synced automatically via blockchain events
# The watcher continuously monitors the blockchain and updates position state


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
        unrealized_pnl_pct=user.unrealized_pnl_percentage,  # Same value with different name
        realized_pnl_percentage=user.realized_pnl_percentage,
        fees_earned_usdc=total_fees_earned,
        rewards_earned_usdc=total_rewards_earned,
        total_pnl_usdc=total_pnl,
        protocol_fees_pending_usdc=protocol_fees_pending,
        net_pnl_usdc=net_pnl
    )


# NOTE: pnl-details endpoint removed - use /pnl endpoint instead which provides all the same data plus more

# NOTE: Sync PnL endpoint removed - PnL is calculated automatically by the watcher on every transaction

@router.get("/{user_id}/performance", response_model=PerformanceResponse)
async def get_performance(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get simplified user performance metrics.
    
    Returns key metrics aggregated from other endpoints:
    - balance from /balance endpoint (total_portfolio_value_usdc)
    - pnl from /pnl endpoint (unrealized values)
    - apr and active positions count
    """
    service = UserService(db)
    
    # Verify user exists
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get balance info (same logic as /balance endpoint)
    wallet_balance = await service.get_user_balance(user_id)
    positions = await service.get_user_positions(user_id, status='ACTIVE')
    
    # Calculate total portfolio value (same as balance endpoint)
    current_positions_value = Decimal(0)
    for position in positions:
        try:
            # Try to get real-time value from blockchain
            position_info = await positions_service.get_position_by_id(position.nft_token_id)
            current_value_usd = Decimal(str(position_info.current_value_usd or 0))
            unclaimed_fees_usd = Decimal(str(position_info.unclaimed_fees_usd or 0))
            position_total = current_value_usd + unclaimed_fees_usd
            position_total += (position.rewards_earned_usdc or Decimal(0))
            position_total += (position.fees_earned_usdc or Decimal(0))
            current_positions_value += position_total
        except Exception:
            # Fall back to database value if blockchain fetch fails
            current_positions_value += (position.current_value_usdc or Decimal(0))
    
    total_portfolio_value = wallet_balance + current_positions_value
    
    # Get PnL info (same logic as /pnl endpoint)
    await service.recalculate_user_pnl(user_id)
    await db.refresh(user)
    
    # Calculate APR - simple average of active positions
    apr = 0.0
    if positions:
        try:
            # Get APR from strategy monitor for accurate calculation
            from app.schemas.strategy import MonitorPositionsRequest
            from app.core.strategy_service import strategy_service
            
            if user.cdp_wallet_address:
                monitor_request = MonitorPositionsRequest(user_address=user.cdp_wallet_address)
                monitor_response = await strategy_service.monitor_positions(monitor_request)
                
                # Check different possible APR fields in the response
                if monitor_response:
                    if hasattr(monitor_response, 'average_apr') and monitor_response.average_apr:
                        apr = float(monitor_response.average_apr)
                    elif hasattr(monitor_response, 'portfolio_metrics') and monitor_response.portfolio_metrics:
                        # portfolio_metrics is an object, not a dict
                        if hasattr(monitor_response.portfolio_metrics, 'current_apr'):
                            apr = float(monitor_response.portfolio_metrics.current_apr or 0)
                    elif monitor_response.portfolio_summary:
                        apr = float(monitor_response.portfolio_summary.weighted_apr or 0)
        except Exception as e:
            logger.warning(f"Failed to get APR from strategy service: {e}")
            # Fallback to 0 if strategy service fails
            apr = 0.0
    
    return PerformanceResponse(
        apr=apr,
        balance=total_portfolio_value,
        pnl_usdc=user.unrealized_pnl_usdc,
        pnl_pct=user.unrealized_pnl_percentage,
        active_positions=len(positions)
    )

# NOTE: Protocol fees endpoint removed - fees are included in other endpoints like /pnl

