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
from app.core.signature_service import signature_service

router = APIRouter(prefix="/users")


async def enrich_position_with_pool_data(position, db: Optional[AsyncSession] = None) -> dict:
    """Enrich position with pool information, PNL, APR, and calculated values from blockchain."""
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
    
    # Verify signature to prove wallet ownership
    # The frontend sends the exact message that was signed
    logger.info(f"Verifying signature for user {request.user_id}")
    logger.info(f"Message: {request.message}")
    logger.info(f"Signature length: {len(request.signature)} (EOA=132, Smart Wallet=1000+)")
    logger.info(f"Signature preview: {request.signature[:50]}...")
    
    # Smart wallets use ERC-6492 signatures which are much longer than EOA signatures
    # So we don't validate length here - let the signature service handle it
    
    if not signature_service.verify_signature(request.message, request.signature, request.user_id):
        raise HTTPException(status_code=401, detail="Invalid signature - wallet ownership verification failed")
    
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
            cdp_wallet_address=None,  # Will be set when CDP wallet is created
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
        
        logger.info(f"User {request.user_id} created successfully. Agent will auto-start when balance >= 50 USDC")
        
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
        # Verify signature to prove wallet ownership
        # The frontend sends the exact message that was signed
        logger.info(f"Verifying withdrawal signature for {user_id}")
        logger.info(f"Signature length: {len(request.signature)} (EOA=132, Smart Wallet=1000+)")
        
        if not signature_service.verify_signature(request.message, request.signature, user_id):
            raise HTTPException(status_code=401, detail="Invalid signature - withdrawal authorization failed")
        
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
        # Create response manually to avoid property setter issues
        return TransactionResponse(
            transaction_id=transaction.id,
            user_id=transaction.user_id,
            transaction_type=transaction.tx_type,
            amount_usdc=transaction.amount_usdc,  # This reads from the property
            tx_hash=transaction.tx_hash,
            status=transaction.status,
            event_data=transaction.event_data,
            created_at=transaction.created_at,
            tx_metadata=transaction.tx_metadata,
            # Include optional fields with None defaults
            block_number=getattr(transaction, 'block_number', None),
            block_timestamp=getattr(transaction, 'block_timestamp', None),
            gas_used=getattr(transaction, 'gas_used', None),
            gas_price=getattr(transaction, 'gas_price', None),
            confirmed_at=getattr(transaction, 'confirmed_at', None),
            pool_name=None
        )
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
    
    # Get wallet balance - prefer blockchain query for accuracy
    from app.services.blockchain_service import blockchain_service
    
    # Try to get balance from blockchain first
    if user.cdp_wallet_address:
        blockchain_balance = await blockchain_service.get_usdc_balance(user.cdp_wallet_address)
        if blockchain_balance is not None:
            wallet_balance = blockchain_balance
            # Update database if significantly different
            db_balance = await service.get_user_balance(user_id)
            if abs(db_balance - blockchain_balance) > 0.01:
                logger.info(f"Updating {user_id} balance from {db_balance} to {blockchain_balance}")
                user.usdc_balance = float(blockchain_balance)
                await db.commit()
        else:
            # Fallback to database if blockchain query fails
            wallet_balance = await service.get_user_balance(user_id)
    else:
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
    
    # Calculate invested amount from ACTIVE positions using net amounts from transactions
    invested_in_pools = Decimal(0)
    for position in positions:
        # Find the POSITION_CREATED transaction for this position
        position_created_txs = await service.get_user_transactions(
            user_id=user_id,
            transaction_type=DBTransactionType.POSITION_CREATED,
            status=DBTransactionStatus.CONFIRMED
        )
        
        # Find the transaction for this specific position token
        for tx in position_created_txs:
            if tx.event_data and str(tx.event_data.get('tokenId')) == str(position.nft_token_id):
                # Calculate net amount (amount - returned USDC)
                amount = Decimal(str(tx.event_data.get('amount_usdc', 0)))
                usdc_returned = Decimal(str(tx.event_data.get('usdc_returned', 0))) if tx.event_data.get('usdc_returned') else Decimal(0)
                net_invested = amount - usdc_returned
                invested_in_pools += net_invested
                break
    
    # Calculate total positions value using real-time blockchain data
    current_positions_value = Decimal(0)
    
    for position in positions:
        try:
            # Use the same enrichment logic to get real-time values
            position_info = await positions_service.get_position_by_id(position.nft_token_id)
            
            current_value_usd = Decimal(str(position_info.current_value_usd or 0))
            unclaimed_fees_usd = Decimal(str(position_info.unclaimed_fees_usd or 0))
            
            # Calculate total position value: blockchain value + unclaimed fees
            # Note: We don't add database fees/rewards here as they are already reflected in the blockchain values
            position_total = current_value_usd + unclaimed_fees_usd
            
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
    # Use Decimal consistently for precise financial math
    total_portfolio_value = Decimal(str(wallet_balance)) + current_positions_value
    
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
                stmt = select(Transaction).where(
                    and_(
                        Transaction.user_id == user_id,
                        Transaction.tx_type == 'AERO_SWAP',
                        or_(
                            Transaction.event_data['tokenId'].astext == token_id,
                            Transaction.event_data['position_token_id'].astext == token_id
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
    
    Returns key metrics:
    - balance: wallet + current positions (real-time when possible)
    - pnl_usdc: unrealized PnL from active positions
    - pnl_pct: unrealized PnL percentage
    - apr and active positions count
    """
    service = UserService(db)
    
    # Verify user exists
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Recalculate PnL with real-time position values from blockchain (same as /pnl endpoint)
    await service.recalculate_user_pnl(user_id)
    
    # Refresh user to get updated values
    await db.refresh(user)
    
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
    from app.services.blockchain_service import blockchain_service
    
    # Try to get balance from blockchain first
    if user.cdp_wallet_address:
        blockchain_balance = await blockchain_service.get_usdc_balance(user.cdp_wallet_address)
        if blockchain_balance is not None:
            wallet_balance = blockchain_balance
            # Update database if significantly different
            db_balance = await service.get_user_balance(user_id)
            if abs(db_balance - blockchain_balance) > 0.01:
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
    
    # Use unrealized PnL values from the recalculated user object (same as /pnl endpoint)
    # This ensures consistency between /performance and /pnl endpoints
    return PerformanceResponse(
        apr=apr,
        balance=total_portfolio_value,
        pnl_usdc=user.unrealized_pnl_usdc,  # Use unrealized PnL from user object
        pnl_pct=user.unrealized_pnl_percentage,  # Use unrealized PnL percentage from user object
        active_positions=len(positions)
    )

# NOTE: Protocol fees endpoint removed - fees are included in other endpoints like /pnl
