from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from decimal import Decimal
import os
from loguru import logger
from app.database.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.user_service import UserService
from app.core.pools_service import pools_service
from app.core.positions_service import positions_service
from app.core.config import settings
from app.schemas.users import (
    CreateUserRequest, UpdateUserRequest, DepositRequest, WithdrawResponse,
    UserResponse, UserListResponse, TransactionResponse, TransactionListResponse,
    PositionResponse, PositionListResponse, CreatePositionRequest, ClosePositionRequest,
    BalanceResponse, PerformanceResponse,
    UserStatus, TransactionType, TransactionStatus, PositionStatus, TimePeriod,
    DeltaNeutralStrategyRequest, DeltaNeutralStrategyResponse, RangeBreakAction
)
# Enums are already imported from schemas above
DBTransactionType = TransactionType
DBTransactionStatus = TransactionStatus
DBPositionStatus = PositionStatus
from app.core.logger import logger

router = APIRouter(prefix="/users")


async def enrich_position_with_pool_data(position, db: Optional[AsyncSession] = None) -> dict:
    """Enrich position with pool information, PNL, APR, and calculated values from blockchain."""
    # Convert position to dict, excluding token addresses and liquidity
    position_dict = PositionResponse.model_validate(position).model_dump()
    
    # Get the net entry amount from the POSITION_CREATED transaction if db is provided
    net_entry_amount = position.entry_amount_usdc or Decimal(0)
    if db:
        from sqlalchemy import select, and_
        from app.database.models import Transaction
        
        stmt = select(Transaction).where(
            and_(
                Transaction.user_id == position.user_id,
                Transaction.tx_type == 'POSITION_CREATED',
                Transaction.event_data['tokenId'].astext == str(position.nft_token_id)
            )
        ).limit(1)
        result = await db.execute(stmt)
        position_created_tx = result.scalar_one_or_none()
        
        if position_created_tx and position_created_tx.event_data:
            # Prefer explicit amount_usdc if present, otherwise fall back to usdcIn
            amt_field = position_created_tx.event_data.get('amount_usdc')
            if amt_field is None:
                # usdcIn may be raw base units, convert when needed
                raw_in = position_created_tx.event_data.get('usdcIn', 0)
                try:
                    raw_in = Decimal(str(raw_in))
                except Exception:
                    raw_in = Decimal(0)
                # Heuristic: if very large, divide by 1e6
                amount = raw_in / Decimal(1_000_000) if raw_in > 1000 else raw_in
            else:
                amount = Decimal(str(amt_field))
            usdc_returned = Decimal(str(position_created_tx.event_data.get('usdc_returned', 0))) if position_created_tx.event_data.get('usdc_returned') else Decimal(0)
            net_entry_amount = amount - usdc_returned
    
    # Override the entry_amount_usdc with the net amount
    position_dict['entry_amount_usdc'] = net_entry_amount
    
    # Skip blockchain fetch for closed positions - they don't exist on-chain anymore
    if position.status == DBPositionStatus.CLOSED:
        # For closed positions, use database values and calculate final PNL
        try:
            # Get token info for pool name, only if addresses are available
            if position.token0_address and position.token1_address:
                token0_info = await pools_service.get_token_info(position.token0_address)
                token1_info = await pools_service.get_token_info(position.token1_address)
                
                # Create pool name from token symbols  
                token0_symbol = token0_info.get('symbol', '???')
                token1_symbol = token1_info.get('symbol', '???')
                position_dict['pool_name'] = f"{token0_symbol}/{token1_symbol}"
            else:
                position_dict['pool_name'] = position.pool_name or "Unknown/Unknown"
        except:
            position_dict['pool_name'] = "Unknown/Unknown"
        
        # Use stored values for closed positions
        position_dict['current_value_usdc'] = position.current_value_usdc or Decimal(0)
        position_dict['current_total_value'] = position.current_value_usdc or Decimal(0)
        position_dict['unrealized_pnl_usdc'] = Decimal(0)  # Closed positions have no unrealized PnL
        position_dict['total_pnl_usdc'] = position.realized_pnl_usdc + position.fees_earned_usdc + position.rewards_earned_usdc
        
        if net_entry_amount and net_entry_amount > 0:
            position_dict['pnl_percentage'] = (position_dict['total_pnl_usdc'] / net_entry_amount) * Decimal(100)
        else:
            position_dict['pnl_percentage'] = Decimal(0)
        
        position_dict['pool_base_apr'] = Decimal(0)
        position_dict['effective_apr'] = Decimal(0)
        
        return position_dict
    
    try:
        # Get real-time position data from blockchain using the singleton service (only for ACTIVE positions)
        try:
            position_info = await positions_service.get_position_by_id(position.nft_token_id)
            # Update the staked status and gauge address from blockchain
            position_dict['staked'] = position_info.staked
            if position_info.gauge_address:
                position_dict['gauge_address'] = position_info.gauge_address
            
            # Update the database if staked status or gauge address has changed
            if db:
                update_needed = False
                if position.staked != position_info.staked:
                    position.staked = position_info.staked
                    update_needed = True
                if position_info.gauge_address and position.gauge_address != position_info.gauge_address:
                    position.gauge_address = position_info.gauge_address
                    update_needed = True
                
                if update_needed:
                    await db.commit()
                    logger.info(f"Updated position {position.nft_token_id}: staked={position_info.staked}, gauge={position_info.gauge_address}")
        except Exception as e:
            # If position doesn't exist on-chain, it was likely closed externally
            if "execution reverted: ID" in str(e) or "ContractLogicError" in str(e):
                logger.error(f"Position {position.nft_token_id} no longer exists on-chain but still marked as {position.status} in database!")
                logger.error("Agent manager should call /users/{user_id}/positions/{nft_token_id}/close when closing positions")
                
                # Return data showing position is likely closed
                position_dict['current_value_usdc'] = Decimal(0)
                position_dict['current_total_value'] = Decimal(0)
                position_dict['pool_name'] = "CLOSED/ERROR"
                position_dict['total_pnl_usdc'] = Decimal(0) - net_entry_amount
                position_dict['pnl_percentage'] = Decimal(-100)
                position_dict['pool_base_apr'] = Decimal(0)
                position_dict['effective_apr'] = Decimal(0)
                # Add error flag to help frontend handle this case
                position_dict['error'] = "Position not found on-chain - likely closed externally"
                position_dict['needs_sync'] = True
                return position_dict
            else:
                raise  # Re-raise if it's a different error
        
        # Get token info for pool name, only if addresses are available
        if position.token0_address and position.token1_address:
            token0_info = await pools_service.get_token_info(position.token0_address)
            token1_info = await pools_service.get_token_info(position.token1_address)
            
            # Create pool name from token symbols  
            token0_symbol = token0_info.get('symbol', '???')
            token1_symbol = token1_info.get('symbol', '???')
            position_dict['pool_name'] = f"{token0_symbol}/{token1_symbol}"
        else:
            position_dict['pool_name'] = position.pool_name or "Unknown/Unknown"
        
        # Use correct values from the positions service
        current_value_usd = Decimal(str(position_info.current_value_usd or 0))
        unclaimed_fees_usd = Decimal(str(position_info.unclaimed_fees_usd or 0))
        
        # Debug logging
        logger.info(f"Position {position.nft_token_id} enrichment: current_value_usd={current_value_usd}, unclaimed_fees_usd={unclaimed_fees_usd}")
        
        # Calculate current_total_value: position value + unclaimed fees from blockchain
        # Note: We don't add database fees/rewards here as they are already reflected in the blockchain values
        current_total_value = current_value_usd + unclaimed_fees_usd
        
        position_dict['current_total_value'] = current_total_value
        
        # Update current_value_usdc with the real-time value for consistency
        position_dict['current_value_usdc'] = current_value_usd
        
        # Calculate unrealized PNL (current value - entry amount)
        unrealized_pnl = current_total_value - net_entry_amount
        position_dict['unrealized_pnl_usdc'] = unrealized_pnl
        
        # Calculate PNL
        if net_entry_amount > 0:
            # Total PNL = current_total_value - net_entry_amount
            total_pnl = current_total_value - net_entry_amount
            position_dict['total_pnl_usdc'] = total_pnl
            
            # PNL percentage
            pnl_percentage = (total_pnl / net_entry_amount) * Decimal(100)
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

                # Get tick_spacing from pool data
                tick_spacing = pool.get('tick_spacing')

                # Calculate effective APR based on position range
                if tick_spacing and position_info.in_range and position.tick_lower is not None and position.tick_upper is not None:
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
                        tick_spacing,
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
@router.get("", response_model=List[UserListResponse])
async def list_users(
    db: AsyncSession = Depends(get_db)
):
    """List all users with enhanced metrics including portfolio value and PnL.
    
    Returns comprehensive user data including:
    - Wallet balance and total portfolio value
    - Position counts (active/closed)
    - Total PnL metrics
    - Agent status
    """
    service = UserService(db)
    users = await service.list_all_users()
    
    # Batch fetch all positions for performance
    from sqlalchemy import select
    from app.database.models import Position
    stmt = select(Position)
    result = await db.execute(stmt)
    all_positions = result.scalars().all()
    
    # Group positions by user
    positions_by_user = {}
    for position in all_positions:
        if position.user_id not in positions_by_user:
            positions_by_user[position.user_id] = []
        positions_by_user[position.user_id].append(position)
    
    # Build enhanced response for each user
    enhanced_users = []
    for user in users:
        # Get wallet balance
        wallet_balance = await service.get_user_balance(user.user_id)
        
        # Get user's positions
        user_positions = positions_by_user.get(user.user_id, [])
        
        # Count positions by status
        active_positions = [p for p in user_positions if p.status == DBPositionStatus.ACTIVE]
        closed_positions = [p for p in user_positions if p.status == DBPositionStatus.CLOSED]
        
        # Calculate current positions value (for active positions only)
        current_positions_value = Decimal(0)
        for position in active_positions:
            try:
                # Try to get real-time value from blockchain
                position_info = await positions_service.get_position_by_id(position.nft_token_id)
                current_value_usd = Decimal(str(position_info.current_value_usd or 0))
                unclaimed_fees_usd = Decimal(str(position_info.unclaimed_fees_usd or 0))
                current_positions_value += (current_value_usd + unclaimed_fees_usd)
            except Exception:
                # Fallback to database value if blockchain query fails
                current_positions_value += (position.current_value_usdc or Decimal(0))
        
        # Calculate total portfolio value
        total_portfolio_value = Decimal(str(wallet_balance)) + current_positions_value
        
        # Calculate realized PnL from closed positions only
        total_realized_pnl = sum(p.realized_pnl_usdc or Decimal(0) for p in closed_positions)

        # Calculate unrealized PnL from active positions using real-time values
        total_unrealized_pnl = Decimal(0)
        for pos in active_positions:
            try:
                # Fetch real-time position data from blockchain
                position_info = await positions_service.get_position_by_id(pos.nft_token_id)
                if position_info and position_info.current_value_usd:
                    current_value = Decimal(str(position_info.current_value_usd))
                    entry_value = pos.entry_amount_usdc or Decimal(0)
                    pos_unrealized = current_value - entry_value
                    total_unrealized_pnl += pos_unrealized
                else:
                    # Fallback to database values
                    total_unrealized_pnl += (pos.unrealized_pnl_usdc or Decimal(0))
            except Exception:
                # Fallback to database values
                total_unrealized_pnl += (pos.unrealized_pnl_usdc or Decimal(0))

        # Total PnL is realized + unrealized
        total_pnl = total_realized_pnl + total_unrealized_pnl

        # Calculate PnL percentage based on total deposits (not net)
        total_pnl_percentage = Decimal(0)
        if len(user_positions) > 0:
            # Get total deposits for percentage calculation
            total_deposits, total_withdrawals = await service.get_deposit_withdrawal_totals(user.user_id)
            if total_deposits > 0:
                total_pnl_percentage = (total_pnl / total_deposits) * 100
        
        # Build enhanced response
        enhanced_user = UserListResponse(
            user_id=user.user_id,
            cdp_wallet_address=user.cdp_wallet_address,
            status=user.status,
            created_at=user.created_at,
            total_portfolio_value=total_portfolio_value,
            active_positions_count=len(active_positions),
            total_pnl_usdc=total_pnl,
            total_pnl_percentage=total_pnl_percentage,
            agent_active=bool(user.cdp_wallet_address and user.cdp_wallet_address != "pending")
        )
        enhanced_users.append(enhanced_user)
    
    return enhanced_users


@router.post("/{user_id}", response_model=UserResponse, status_code=201)
async def create_user(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Create a new user and start their agent.

    This endpoint handles user creation:
    - Creates user record with wallet address as ID
    - Always starts agent and creates CDP wallet
    - Returns user info with CDP wallet
    
    Args:
        user_id: User's wallet address (EOA)
        start_agent: Whether to start agent and create CDP wallet (default: true)
        signature: Optional signature to prove wallet ownership
    """
    
    # Validate wallet address format
    if not user_id.startswith("0x") or len(user_id) != 42:
        raise HTTPException(status_code=400, detail="Invalid wallet address format")

    # Signature verification removed - CDP wallet generation doesn't require it
    logger.info(f"Creating user {user_id} without signature verification")

    user_service = UserService(db)

    # Check if user already exists
    existing_user = await user_service.get_user(user_id)
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")
    
    try:
        # Create user with wallet address as ID
        # user_id IS the owner's wallet address
        user = await user_service.create_user(
            user_id=user_id,  # This is the user's EOA address
            cdp_wallet_address=None,  # Will be set when CDP wallet is created
            cdp_wallet_name=f"n0ir-agent-{user_id[:8]}"  # Shortened for readability
        )

        # Always request CDP wallet creation from agent manager (start_agent is always true now)
        from app.services.agent_management_service import get_agent_service
        agent_service = get_agent_service()

        logger.info(f"Requesting CDP wallet creation for user {user_id}")
        wallet_result = await agent_service.create_wallet_for_user(user_id)

        if wallet_result.get('success') and wallet_result.get('wallet_address'):
            # Update user with real wallet address
            await user_service.update_user_wallet(user_id, wallet_result['wallet_address'])
            user.cdp_wallet_address = wallet_result['wallet_address']
            logger.info(f"CDP wallet created immediately for {user_id}: {wallet_result['wallet_address']}")
        elif wallet_result.get('error') == 'timeout':
            logger.info(f"CDP wallet creation timed out for {user_id}, will update asynchronously")
            # Continue with pending address - will be updated via event listener
        else:
            logger.warning(f"Failed to create CDP wallet for {user_id}: {wallet_result.get('error')}")
            # Continue with pending address

        logger.info(f"User {user_id} created successfully. Agent will auto-start when balance >= 50 USDC")
        
        return UserResponse.model_validate(user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# Financial Operations
# NOTE: Deposit and withdrawal endpoints removed - these are now tracked automatically by the watcher from blockchain events

@router.post("/{user_id}/withdraw", response_model=WithdrawResponse, status_code=201)
async def withdraw(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Withdraw entire USDC balance after closing all positions and swapping all tokens.

    This endpoint will:
    - Close all active positions
    - Swap all tokens (including AERO) to USDC
    - Withdraw the entire USDC balance to the user's wallet
    - Always succeed (withdrawing 0 if nothing is available)
    - Withdrawals always go to the user_id address

    Args:
        user_id: User's wallet address (also the destination address)
    """
    try:
        logger.info(f"Processing full withdrawal for {user_id} - closing all positions and withdrawing entire balance")

        service = UserService(db)

        # Get all active positions to close
        active_positions = await service.get_user_positions(user_id, status='ACTIVE')
        positions_closed = len(active_positions)

        # Calculate total expected value from positions
        expected_from_positions = Decimal(0)
        for position in active_positions:
            expected_from_positions += (position.current_value_usdc or position.entry_amount_usdc or Decimal(0))

        # Get current wallet balance
        wallet_balance = await service.get_user_balance(user_id)

        # Calculate total expected amount (positions + wallet balance)
        # When withdraw_all=True, the agent will close all positions, swap all tokens, and withdraw everything
        withdrawal_amount = wallet_balance + expected_from_positions

        logger.info(f"User {user_id} has {positions_closed} active positions worth ~{expected_from_positions} USDC and wallet balance {wallet_balance} USDC")

        # Execute full withdrawal through service
        # This will close all positions, swap all tokens, and withdraw everything
        transaction = None
        try:
            transaction = await service.withdraw_usdc(
                user_id=user_id,
                amount=withdrawal_amount,  # Expected total amount
                withdraw_all=True  # This flag tells the agent to withdraw everything
            )

            # Get the actual withdrawn amount from the transaction or estimate
            actual_withdrawn = wallet_balance + expected_from_positions

        except Exception as e:
            # Even if there's an error, try to estimate what could be withdrawn
            actual_withdrawn = Decimal(0)
            logger.error(f"Withdrawal execution failed: {e}")

        # Get updated balance (should be close to 0 after full withdrawal)
        remaining_balance = await service.get_user_balance(user_id)

        # Create response
        return WithdrawResponse(
            requested_amount=wallet_balance + expected_from_positions,  # Total available
            withdrawn_amount=actual_withdrawn,
            remaining_balance=remaining_balance,
            positions_closed=positions_closed,
            status="complete" if actual_withdrawn > 0 else "none",
            tx_hash=transaction.tx_hash if transaction else None,
            transaction_id=transaction.id if transaction else None,
            message=f"Closed {positions_closed} positions and withdrew all USDC"
        )
    except Exception as e:
        logger.error(f"Error processing full withdrawal: {e}")
        # Even on error, return a valid response showing nothing was withdrawn
        return WithdrawResponse(
            requested_amount=Decimal(0),
            withdrawn_amount=Decimal(0),
            remaining_balance=await service.get_user_balance(user_id) if 'service' in locals() else Decimal(0),
            positions_closed=0,
            status="error",
            tx_hash=None,
            transaction_id=None,
            message=str(e)
        )


# NOTE: Balance endpoint removed - balance information is now available through the performance endpoint
# GET /api/v1/users/{user_id}/balance has been deprecated
# Use GET /api/v1/users/{user_id}/performance instead which includes:
# - wallet_balance: Current USDC balance in wallet
# - positions_value: Total value invested in positions
# - total_balance: Total portfolio value (wallet + positions)


@router.get("/{user_id}/transactions", response_model=TransactionListResponse)
async def get_transactions(
    user_id: str,
    limit: int = 100,
    offset: int = 0,
    transaction_type: Optional[DBTransactionType] = None,
    sort_order: str = "desc",  # "asc" for oldest first, "desc" for newest first
    db: AsyncSession = Depends(get_db)
):
    """Get user transactions with automatic sync from CDP.
    
    This endpoint automatically syncs fresh transactions from CDP if:
    - User has a CDP wallet address
    - CDP API key is configured in environment
    
    Transactions are categorized as:
    - DEPOSIT: USDC from owner wallet to CDP wallet
    - WITHDRAW: USDC from CDP wallet to owner wallet
    - POSITION_CREATED: Position opened via LiquidityManager
    - POSITION_CLOSED: Position closed via LiquidityManager
    - STAKING: NFT position staked to gauge
    - SWAP: Token swap transactions
    - FEE_TRANSFER: Fee transfers to 0xfD75350A7e2C4914908fF7E3082c45Af5762f5FE
    """
    # First check if user has a CDP wallet and fetch fresh data
    from sqlalchemy import select
    from app.database.models import User
    from app.services.wallet_transaction_service import WalletTransactionService
    
    stmt = select(User).where(User.user_id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    # Automatically sync if user has CDP wallet and API key is configured
    if user and user.cdp_wallet_address and settings.cdp_client_api_key:
        try:
            wallet_service = WalletTransactionService(db)
            sync_result = await wallet_service.fetch_and_sync_transactions(
                user_id=user_id,
                cdp_wallet_address=user.cdp_wallet_address,
                limit=100  # Sync more transactions to catch stake events
            )
            logger.info(f"Auto-synced {sync_result.get('transactions_synced', 0)} transactions for user {user_id}")

            # Ensure positions exist for all POSITION_CREATED transactions
            await wallet_service.ensure_positions_for_transactions(user_id)

        except Exception as e:
            logger.warning(f"Auto-sync failed for user {user_id}: {e}, using cached data")
            # Continue with local data if sync fails

    # Even if sync fails, try to ensure positions exist for existing transactions
    if user and user.cdp_wallet_address:
        try:
            wallet_service = WalletTransactionService(db)
            await wallet_service.ensure_positions_for_transactions(user_id)
        except Exception as e:
            logger.warning(f"Failed to ensure positions for user {user_id}: {e}")

    service = UserService(db)
    transactions = await service.get_user_transactions(
        user_id=user_id,
        limit=limit,
        offset=offset,
        transaction_type=transaction_type,
        sort_order=sort_order
    )
    
    # Fetch pool names for position transactions using pool address from event_data
    # Also look up AERO swaps for POSITION_CLOSED transactions
    from app.core.pools_service import pools_service
    from sqlalchemy import select, and_, or_
    from app.database.models import Transaction, Position
    
    for tx in transactions:
        # Debug log for POSITION_CREATED transactions
        if tx.tx_type == 'POSITION_CREATED':
            logger.info(f"DEBUG TX {tx.tx_hash[:10]}: Original event_data keys: {list(tx.event_data.keys()) if tx.event_data else 'None'}")
            if tx.event_data and 'usdc_returned' in tx.event_data:
                logger.info(f"DEBUG: usdc_returned present: {tx.event_data['usdc_returned']}")
        
        # Check if this is a position-related transaction
        if hasattr(tx, 'event_data') and tx.event_data:
            pool_address = None
            
            # For POSITION_CREATED, pool address is in event_data
            if tx.tx_type == 'POSITION_CREATED' and 'pool' in tx.event_data:
                pool_address = tx.event_data.get('pool')
            
            # For POSITION_CLOSED, fetch pool address from Position table using tokenId or token_id
            elif tx.tx_type == 'POSITION_CLOSED' and ('tokenId' in tx.event_data or 'token_id' in tx.event_data):
                token_id = tx.event_data.get('tokenId') or tx.event_data.get('token_id')
                if token_id:
                    # Fetch the position to get pool_address
                    stmt = select(Position).where(Position.token_id == int(token_id))
                    result = await db.execute(stmt)
                    position = result.scalar_one_or_none()
                    if position:
                        pool_address = position.pool_address
                        # Add pool_address to event_data for future reference
                        tx.event_data['pool'] = pool_address
            
            # Now fetch pool_name if we have a pool_address and pool_name is missing
            if pool_address and not tx.event_data.get('pool_name'):
                try:
                    pool_data = await pools_service.get_pool(pool_address)
                    if pool_data and 'symbol' in pool_data:
                        # Symbol format is like "WETH/USDC-5%" - extract just the pair name
                        symbol = pool_data['symbol']
                        # Remove the fee percentage part (e.g., "WETH/USDC-5%" -> "WETH/USDC")
                        pool_name = symbol.split('-')[0] if '-' in symbol else symbol
                        tx.event_data['pool_name'] = pool_name
                except Exception as e:
                    logger.debug(f"Could not fetch pool data for {pool_address}: {e}")
        
        # For POSITION_CLOSED transactions, look up matching AERO_SWAP
        if hasattr(tx, 'tx_type') and tx.tx_type == 'POSITION_CLOSED' and hasattr(tx, 'event_data') and tx.event_data:
            token_id = tx.event_data.get('tokenId') or tx.event_data.get('token_id')
            if token_id:
                # Look for AERO_SWAP with matching tokenId or position_token_id
                # Cast token_id to string for JSONB comparison
                token_id_str = str(token_id)
                stmt = select(Transaction).where(
                    and_(
                        Transaction.user_id == user_id,
                        Transaction.tx_type == 'AERO_SWAP',
                        or_(
                            Transaction.event_data['tokenId'].astext == token_id_str,
                            Transaction.event_data['position_token_id'].astext == token_id_str
                        )
                    )
                ).limit(1)
                result = await db.execute(stmt)
                aero_swap = result.scalar_one_or_none()
                
                if aero_swap and hasattr(aero_swap, 'event_data') and aero_swap.event_data:
                    # Add AERO swap amount to event_data
                    tx.event_data['aero_swap_usdc'] = aero_swap.event_data.get('amount_usdc', 0)
    
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
    # First check if user has a CDP wallet and fetch fresh liquidity events from CDP
    from sqlalchemy import select
    from app.database.models import User
    from app.services.blockchain_data_service import BlockchainDataService
    
    stmt = select(User).where(User.user_id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if user and user.cdp_wallet_address:
        try:
            # Fetch fresh liquidity events from CDP SQL API
            blockchain_service = BlockchainDataService()
            await blockchain_service.get_wallet_performance_data(
                user_id=user_id,
                cdp_wallet=user.cdp_wallet_address,
                lookback_hours=24 * 365,  # Get all historical data
                include_liquidity_events=True,  # Include liquidity events for positions
                db_session=db,
                save_to_db=True
            )
            logger.info(f"Fetched fresh CDP liquidity events for user {user_id} wallet {user.cdp_wallet_address}")
        except Exception as e:
            logger.warning(f"Failed to fetch CDP liquidity events for user {user_id}: {e}")
            # Continue with local data if CDP fetch fails
    
    service = UserService(db)
    
    # For now, use the existing service method which reads from public.positions
    # Once the watcher has backfilled blockchain.positions, we can switch
    positions = await service.get_user_positions(user_id, status)
    
    # Enrich positions with pool data
    enriched_positions = []
    for position in positions:
        enriched_position = await enrich_position_with_pool_data(position, db)
        enriched_positions.append(PositionResponse.model_validate(enriched_position))
    
    return PositionListResponse(
        positions=enriched_positions,
        total=len(positions)
    )


# NOTE: Close position endpoint removed - position closes are detected automatically by the watcher from blockchain events

# Position sync endpoint removed - positions are now synced automatically via blockchain events
# The watcher continuously monitors the blockchain and updates position state


# Analytics
# NOTE: pnl endpoint removed - use /performance endpoint instead which provides all PnL data

# NOTE: Sync PnL endpoint removed - PnL is calculated automatically by the watcher on every transaction

@router.get("/{user_id}/performance", response_model=PerformanceResponse)
async def get_performance(
    user_id: str,
    period: Optional[TimePeriod] = Query(None, description="Time period for performance calculation (24h, 7d, 30d, all)"),
    db: AsyncSession = Depends(get_db)
):
    """Get comprehensive user performance metrics including balance breakdown and PnL.

    Returns all performance metrics:
    - apr: Average APR across active positions
    - wallet_balance: Current USDC balance in wallet
    - positions_value: Total value invested in active positions
    - total_balance: Total portfolio value (wallet + positions)
    - active_positions: Number of active positions
    - realized_pnl_usdc: PnL from closed positions
    - realized_pnl_pct: Realized PnL as percentage of net deposits
    - pnl_usdc: Total PnL (realized + unrealized)
    - pnl_pct: Total PnL as percentage of net deposits

    Time periods:
    - 24h: Last 24 hours
    - 7d: Last 7 days
    - 30d: Last 30 days
    - all: All time (default)
    """
    service = UserService(db)

    # Verify user exists
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Sync user balance with on-chain state before returning performance
    # This ensures we detect deposits immediately when performance is checked
    if user.cdp_wallet_address:
        try:
            from web3 import Web3
            from app.database.models import User
            from sqlalchemy import select
            from app.services.balance_updater import publish_balance_change_event
            import time

            # Redis caching disabled - proceed with sync
            # TODO: Re-enable caching when redis_client is available
            if True:  # Always sync for now
                # Initialize Web3 and USDC contract
                # Use RPC_URL from environment
                rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')
                w3 = Web3(Web3.HTTPProvider(rpc_url))
                usdc_address = Web3.to_checksum_address("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
                usdc_abi = [{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]
                usdc_contract = w3.eth.contract(address=usdc_address, abi=usdc_abi)

                # Get on-chain balance
                checksum_address = Web3.to_checksum_address(user.cdp_wallet_address)
                balance_wei = usdc_contract.functions.balanceOf(checksum_address).call()
                onchain_balance = Decimal(balance_wei) / Decimal(10 ** 6)  # USDC has 6 decimals

                # Redis caching disabled
                # await redis_client.setex(cache_key, 60, str(time.time()))

                # Get current database balance
                db_balance = Decimal(str(user.usdc_balance or 0))

                # Check if balance changed
                if onchain_balance != db_balance:
                    # Determine event type
                    event_type = 'DEPOSIT' if onchain_balance > db_balance else 'WITHDRAWAL'

                    if onchain_balance > db_balance:
                        logger.info(f"Deposit detected for {user_id} via performance endpoint: {db_balance} -> {onchain_balance} USDC")
                    else:
                        logger.info(f"Withdrawal detected for {user_id} via performance endpoint: {db_balance} -> {onchain_balance} USDC")

                    # Update user balance in database
                    user.usdc_balance = onchain_balance

                    # Check if this is first 50+ USDC deposit
                    if not user.has_deposited_50_usdc and onchain_balance >= Decimal('50'):
                        user.has_deposited_50_usdc = True

                    await db.commit()

                    # Publish balance change event for agent manager
                    # Use BOTH pub/sub and streams for redundancy
                    try:
                        # Method 1: Pub/Sub (original)
                        await publish_balance_change_event(
                            user_id=user_id,
                            old_balance=db_balance,
                            new_balance=onchain_balance,
                            event_type=event_type,
                            has_deposited_50_usdc=user.has_deposited_50_usdc
                        )
                    except Exception as e:
                        logger.error(f"Pub/sub publish failed: {e}")

                    try:
                        # Method 2: Stream (backup)
                        from app.services.balance_stream_publisher import publish_balance_change_to_stream
                        await publish_balance_change_to_stream(
                            user_id=user_id,
                            old_balance=db_balance,
                            new_balance=onchain_balance,
                            event_type=event_type,
                            has_deposited_50_usdc=user.has_deposited_50_usdc
                        )
                    except Exception as e:
                        logger.error(f"Stream publish failed: {e}")

                    # Refresh user data after update
                    await db.refresh(user)

        except Exception as e:
            logger.warning(f"Failed to sync balance for {user_id} in performance endpoint: {e}")
            # Continue without syncing - don't fail the entire request

    # Sync transactions from blockchain (similar to transactions endpoint)
    if user.cdp_wallet_address:
        try:
            from app.services.wallet_transaction_service import WalletTransactionService

            # Initialize transaction service with database session
            tx_service = WalletTransactionService(db)

            # Use the correct method name: fetch_and_sync_transactions
            result = await tx_service.fetch_and_sync_transactions(
                user_id=user_id,
                cdp_wallet_address=user.cdp_wallet_address,
                limit=50  # Fetch last 50 transactions
            )

            if result.get("success"):
                logger.info(f"Synced {result.get('transactions_synced', 0)} new transactions for {user_id} during performance check")

        except Exception as e:
            logger.warning(f"Failed to sync transactions for {user_id} in performance endpoint: {e}")
            # Continue without syncing

    # Get PnL data based on period
    if period:
        pnl_data = await service.recalculate_user_pnl_for_period(user_id, period)
        # Extract PnL components
        realized_pnl = pnl_data.get("realized_pnl_usdc", Decimal(0))
        unrealized_pnl = pnl_data.get("unrealized_pnl_usdc", Decimal(0))
        fees_earned = pnl_data.get("fees_earned_usdc", Decimal(0))
        rewards_earned = pnl_data.get("rewards_earned_usdc", Decimal(0))
        total_pnl = pnl_data.get("total_pnl_usdc", Decimal(0))
        
        # Calculate pnl_full_pct for the period (same logic as PnL endpoint)
        from datetime import datetime, timedelta, timezone
        from app.database.models import Transaction
        from sqlalchemy import select, and_, or_
        
        time_boundary = datetime.now(timezone.utc)
        if period == TimePeriod.DAY_1:
            time_boundary = datetime.now(timezone.utc) - timedelta(days=1)
        elif period == TimePeriod.DAY_7:
            time_boundary = datetime.now(timezone.utc) - timedelta(days=7)
        elif period == TimePeriod.DAY_30:
            time_boundary = datetime.now(timezone.utc) - timedelta(days=30)
        
        # Get deposits for the period
        deposit_stmt = select(Transaction).where(
            and_(
                Transaction.user_id == user_id,
                Transaction.tx_type == 'DEPOSIT',
                Transaction.status == 'CONFIRMED'
            )
        )
        deposit_result = await db.execute(deposit_stmt)
        deposits = deposit_result.scalars().all()
        
        # Filter deposits by period
        filtered_deposits = []
        for t in deposits:
            if t.created_at:
                created_at = t.created_at
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                if created_at >= time_boundary:
                    filtered_deposits.append(t)
        # Get amount from event_data (amount_usdc column is deprecated)
        total_deposits = sum(
            Decimal(str(t.event_data.get('amount_usdc', 0))) if t.event_data and 'amount_usdc' in t.event_data
            else Decimal(0)
            for t in filtered_deposits
        )
        
        # Get withdrawals for the period
        withdrawal_stmt = select(Transaction).where(
            and_(
                Transaction.user_id == user_id,
                or_(Transaction.tx_type == 'WITHDRAWAL', Transaction.tx_type == 'WITHDRAW'),
                Transaction.status == 'CONFIRMED'
            )
        )
        withdrawal_result = await db.execute(withdrawal_stmt)
        withdrawals = withdrawal_result.scalars().all()
        
        # Filter withdrawals by period
        filtered_withdrawals = []
        for t in withdrawals:
            if t.created_at:
                created_at = t.created_at
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                if created_at >= time_boundary:
                    filtered_withdrawals.append(t)
        # Get amount from event_data (amount_usdc column is deprecated)
        total_withdrawals = sum(
            Decimal(str(t.event_data.get('amount_usdc', 0))) if t.event_data and 'amount_usdc' in t.event_data
            else Decimal(0)
            for t in filtered_withdrawals
        )
        
        net_deposits = total_deposits - total_withdrawals

        # Calculate total_pnl_percentage
        total_pnl_percentage = Decimal(0)
        if net_deposits > 0:
            total_pnl_percentage = (total_pnl / net_deposits) * 100

        active_positions_count = pnl_data.get("active_positions_count", 0)
    else:
        # Default to all-time (existing behavior)
        # Get positions to calculate PnL
        all_positions = await service.get_user_positions(user_id)

        # Calculate PnL components from positions
        realized_pnl = sum(p.realized_pnl_usdc or Decimal(0) for p in all_positions if p.status == 'CLOSED')

        # Calculate unrealized PnL using real-time values for active positions
        unrealized_pnl = Decimal(0)
        active_positions = [p for p in all_positions if p.status == 'ACTIVE']

        from app.core.positions_service import positions_service
        for pos in active_positions:
            try:
                # Fetch real-time position data from blockchain
                position_info = await positions_service.get_position_by_id(pos.token_id)
                if position_info and position_info.current_value_usd:
                    current_value = Decimal(str(position_info.current_value_usd))
                    entry_value = pos.entry_amount_usdc or Decimal(0)
                    pos_unrealized = current_value - entry_value
                    unrealized_pnl += pos_unrealized

                    # Update database with real-time value for future queries
                    if abs((pos.current_value_usdc or Decimal(0)) - current_value) > Decimal("0.01"):
                        pos.current_value_usdc = current_value
                        await db.commit()
                        logger.debug(f"Updated position {pos.token_id} current value to {current_value}")

                    logger.debug(f"Position {pos.token_id}: real-time value={current_value}, entry={entry_value}, unrealized={pos_unrealized}")
                else:
                    # Fallback to database values
                    unrealized_pnl += (pos.unrealized_pnl_usdc or Decimal(0))
            except Exception as e:
                logger.warning(f"Failed to fetch real-time data for position {pos.token_id}: {e}")
                # Fallback to database values
                unrealized_pnl += (pos.unrealized_pnl_usdc or Decimal(0))

        total_pnl = realized_pnl + unrealized_pnl

        # Get total deposits and withdrawals for all-time percentage calculation
        total_deposits, total_withdrawals = await service.get_deposit_withdrawal_totals(user_id)
        net_deposits = total_deposits - total_withdrawals

        # Calculate total_pnl_percentage using total deposits (not net) to avoid weird percentages
        total_pnl_percentage = Decimal(0)
        if total_deposits > 0:
            total_pnl_percentage = (total_pnl / total_deposits) * 100

        active_positions_count = len([p for p in all_positions if p.status == 'ACTIVE'])

    # Ensure net_deposits is defined for all code paths
    if 'net_deposits' not in locals():
        total_deposits, total_withdrawals = await service.get_deposit_withdrawal_totals(user_id)
        net_deposits = total_deposits - total_withdrawals
    
    # Get positions for APR calculation
    positions = await service.get_user_positions(user_id, status='ACTIVE')
    
    # Calculate total portfolio value (wallet + positions)
    current_positions_value = Decimal(0)
    for position in positions:
        # Current value (real-time when possible)
        try:
            position_info = await positions_service.get_position_by_id(position.nft_token_id)
            current_value_usd = Decimal(str(position_info.current_value_usd or 0))
            unclaimed_fees_usd = Decimal(str(position_info.unclaimed_fees_usd or 0))
            position_total = current_value_usd + unclaimed_fees_usd
            current_positions_value += position_total
        except Exception:
            current_positions_value += (position.current_value_usdc or Decimal(0))
    
    # Get wallet balance - prefer blockchain query for accuracy
    from app.core.blockchain_service import blockchain_service
    
    # Try to get balance from blockchain first
    if user.cdp_wallet_address:
        blockchain_balance = await blockchain_service.get_usdc_balance(user.cdp_wallet_address)
        if blockchain_balance is not None:
            wallet_balance = blockchain_balance
            # Update database if significantly different
            db_balance = await service.get_user_balance(user_id)
            if abs(float(db_balance) - blockchain_balance) > 0.01:
                logger.info(f"Updating {user_id} balance from {db_balance} to {blockchain_balance}")
                user.usdc_balance = float(blockchain_balance)
                await db.commit()
        else:
            # Fallback to database if blockchain query fails
            wallet_balance = await service.get_user_balance(user_id)
    else:
        wallet_balance = await service.get_user_balance(user_id)
    
    # Use Decimal consistently for precise financial math
    total_portfolio_value = Decimal(str(wallet_balance)) + current_positions_value
    
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
                    # First check portfolio_metrics.average_apr (primary source)
                    if hasattr(monitor_response, 'portfolio_metrics') and monitor_response.portfolio_metrics:
                        if hasattr(monitor_response.portfolio_metrics, 'average_apr') and monitor_response.portfolio_metrics.average_apr:
                            apr = float(monitor_response.portfolio_metrics.average_apr)
                            logger.info(f"Got APR {apr} from portfolio_metrics.average_apr")
                        elif hasattr(monitor_response.portfolio_metrics, 'current_apr') and monitor_response.portfolio_metrics.current_apr:
                            apr = float(monitor_response.portfolio_metrics.current_apr)
                            logger.info(f"Got APR {apr} from portfolio_metrics.current_apr")
                    # Then check root level average_apr
                    elif hasattr(monitor_response, 'average_apr') and monitor_response.average_apr:
                        apr = float(monitor_response.average_apr)
                        logger.info(f"Got APR {apr} from root average_apr")
                    # Finally check portfolio_summary
                    elif hasattr(monitor_response, 'portfolio_summary') and monitor_response.portfolio_summary:
                        apr = float(monitor_response.portfolio_summary.weighted_apr or 0)
                        logger.info(f"Got APR {apr} from portfolio_summary.weighted_apr")

                    if apr == 0.0:
                        logger.warning(f"APR is 0 despite getting monitor response. Debug: portfolio_metrics exists: {hasattr(monitor_response, 'portfolio_metrics')}")
        except Exception as e:
            logger.warning(f"Failed to get APR from strategy service: {e}")
            # Fallback - calculate simple average APR from positions
            apr = 0.0
            active_count = 0
            total_apr = 0.0

            for position in positions:
                if position.status == 'ACTIVE' and position.pool_address:
                    try:
                        pool_data = await pools_service.get_pool(position.pool_address)
                        if pool_data and 'apr' in pool_data:
                            pool_apr = float(pool_data.get('apr', 0))
                            total_apr += pool_apr
                            active_count += 1
                    except Exception:
                        pass

            if active_count > 0:
                apr = total_apr / active_count
    
    # Note: blockchain_data parameter has been removed
    # Gas costs and detailed blockchain metrics are now tracked via transaction events
    if False:  # Removed blockchain data fetching
        from app.services.blockchain_data_service import BlockchainDataService
        blockchain_service = BlockchainDataService()
        
        try:
            # Determine lookback hours based on period
            lookback_hours = 24  # Default
            if period == TimePeriod.DAY_7:
                lookback_hours = 24 * 7
            elif period == TimePeriod.DAY_30:
                lookback_hours = 24 * 30
            elif period == TimePeriod.ALL_TIME:
                lookback_hours = 24 * 365  # 1 year for all-time
            
            # Fetch blockchain data from CDP SQL API and save to database
            blockchain_data = await blockchain_service.get_wallet_performance_data(
                user_id=user_id,
                cdp_wallet=user.cdp_wallet_address,
                lookback_hours=lookback_hours,
                include_liquidity_events=True,
                db_session=db,
                save_to_db=True
            )
            
            # Optionally adjust PnL for gas costs from blockchain data
            if blockchain_data and blockchain_data.get('wallet_metrics'):
                gas_costs_usdc = Decimal(str(blockchain_data['wallet_metrics'].get('total_gas_usdc', 0)))
                
                # Adjust PnL for gas costs
                pnl_full = pnl_full - gas_costs_usdc
                pnl_full_pct = (pnl_full / net_deposits * 100) if net_deposits > 0 else Decimal(0)
                
                logger.info(f"Adjusted PnL for gas costs: {gas_costs_usdc} USDC")
            
            # Close the blockchain service client
            await blockchain_service.close()
            
        except Exception as e:
            logger.error(f"Failed to fetch blockchain data from CDP: {e}")
            # Continue without blockchain data
    
    # Calculate realized PnL percentage based on total deposits (not net)
    # Use total deposits as the denominator to avoid weird percentages when user has withdrawn
    realized_pnl_pct = Decimal(0)
    if period:
        # For period calculations, percentage is already calculated correctly
        if net_deposits > 0 and realized_pnl != 0:
            realized_pnl_pct = (realized_pnl / net_deposits) * 100
    else:
        # For all-time, use total deposits (not net) to avoid negative/weird percentages
        total_deposits_only, _ = await service.get_deposit_withdrawal_totals(user_id)
        if total_deposits_only > 0 and realized_pnl != 0:
            realized_pnl_pct = (realized_pnl / total_deposits_only) * 100

    # Return performance data with updated schema including balance breakdown
    return PerformanceResponse(
        # Core metrics with balance breakdown
        apr=apr,
        wallet_balance=Decimal(str(wallet_balance)),  # Current USDC in wallet
        positions_value=current_positions_value,  # Total value in positions
        total_balance=total_portfolio_value,  # wallet + positions (formerly just "balance")
        active_positions=active_positions_count if active_positions_count is not None else len(positions),

        # PnL metrics
        realized_pnl_usdc=realized_pnl,
        realized_pnl_pct=realized_pnl_pct,
        pnl_usdc=total_pnl,  # Total PnL (unrealized + realized)
        pnl_pct=total_pnl_percentage  # Total PnL percentage
    )


# NOTE: Protocol fees endpoint removed - fees are included in performance endpoint

# NOTE: sync-positions endpoint removed - position syncing happens automatically via blockchain events


@router.post("/{user_id}/strategy", response_model=DeltaNeutralStrategyResponse)
async def get_delta_neutral_strategy(
    user_id: str,
    db: AsyncSession = Depends(get_db)
) -> DeltaNeutralStrategyResponse:
    """
    Generate delta-neutral strategy recommendations for a user.

    This endpoint:
    1. Checks user's CDP wallet balance and positions
    2. Uses GPT-5 to determine optimal LP allocations and hedge sizes
    3. Provides recommendations for delta-neutral positioning
    4. Handles range break scenarios with rebalancing suggestions

    Strategy rules:
    - < $2k: Single position (WETH/USDC) + hedge
    - >= $2k: Two positions (WETH priority + cbBTC for stability)
    - 90% to LP, 10% to 5x leveraged short for delta neutrality
    - Monitors positions and suggests actions when out of range
    """
    from app.core.delta_neutral_service import delta_neutral_service

    try:
        # Generate strategy using delta-neutral service
        strategy = await delta_neutral_service.analyze_user_portfolio(
            user_id=user_id,
            db=db
        )

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


@router.get("/{user_id}/strategy/monitor", response_model=List[RangeBreakAction])
async def monitor_strategy_positions(
    user_id: str,
    db: AsyncSession = Depends(get_db)
) -> List[RangeBreakAction]:
    """
    Monitor existing positions for range breaks and get action recommendations.

    Returns a list of recommended actions for positions that are out of range.
    GPT-5 evaluates whether to:
    - Close and reopen with new range
    - Wait for price to return
    - Adjust hedge only
    """
    from app.core.delta_neutral_service import delta_neutral_service

    try:
        # Monitor positions and get recommendations
        actions = await delta_neutral_service.monitor_positions(
            user_id=user_id,
            db=db
        )

        return actions

    except Exception as e:
        logger.error(f"Error monitoring positions for user {user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to monitor positions: {str(e)}"
        )
