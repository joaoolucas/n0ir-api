"""
Info API endpoints for querying user data and performance.
Read-only endpoints for retrieving user information, transactions, positions, and metrics.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from decimal import Decimal
from loguru import logger

from app.database.session import get_db
from app.services.user_service import UserService
from app.core.pools_service import pools_service
from app.core.positions_service import positions_service
from app.core.config import settings
from app.schemas.users import (
    UserListResponse,
    TransactionListResponse,
    TransactionResponse,
    PositionListResponse,
    PerformanceResponse,
    PositionResponse,
    TransactionType,
    TransactionStatus,
    PositionStatus,
    TimePeriod
)

# Enums for database compatibility
DBTransactionType = TransactionType
DBTransactionStatus = TransactionStatus
DBPositionStatus = PositionStatus

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
        position_dict['in_range'] = False

        return position_dict

    # For active positions, fetch blockchain data
    try:
        position_data = await positions_service.get_position_by_id(position.nft_token_id)

        if position_data:
            # Update with blockchain data
            position_dict['current_value_usdc'] = position_data.get('current_value_usd', 0)
            position_dict['current_total_value'] = position_data.get('current_value_usd', 0)
            position_dict['pool_name'] = position_data.get('pool_name', 'Unknown/Unknown')
            position_dict['in_range'] = position_data.get('in_range', False)

            # Get pool APR data
            if position.pool_address:
                try:
                    pool_info = await pools_service.get_pool_info(position.pool_address)
                    position_dict['pool_base_apr'] = Decimal(str(pool_info.get('apr_7d', 0)))
                    position_dict['effective_apr'] = Decimal(str(pool_info.get('apr_7d', 0)))
                except:
                    position_dict['pool_base_apr'] = Decimal(0)
                    position_dict['effective_apr'] = Decimal(0)

            # Calculate PnL (simple version - current value minus entry amount)
            current_value = Decimal(str(position_data.get('current_value_usd', 0)))

            # Total PnL includes fees and rewards
            total_fees_rewards = position.fees_earned_usdc + position.rewards_earned_usdc
            position_dict['unrealized_pnl_usdc'] = current_value - net_entry_amount
            position_dict['total_pnl_usdc'] = position_dict['unrealized_pnl_usdc'] + total_fees_rewards

            if net_entry_amount and net_entry_amount > 0:
                position_dict['pnl_percentage'] = (position_dict['total_pnl_usdc'] / net_entry_amount) * Decimal(100)
            else:
                position_dict['pnl_percentage'] = Decimal(0)
        else:
            # Blockchain data not available, use defaults
            position_dict['pool_name'] = "Unknown/Unknown"
            position_dict['current_value_usdc'] = Decimal(0)
            position_dict['current_total_value'] = Decimal(0)
            position_dict['unrealized_pnl_usdc'] = Decimal(0)
            position_dict['total_pnl_usdc'] = Decimal(0)
            position_dict['pnl_percentage'] = Decimal(0)
            position_dict['pool_base_apr'] = Decimal(0)
            position_dict['effective_apr'] = Decimal(0)
            position_dict['in_range'] = False
    except Exception as e:
        logger.warning(f"Could not fetch blockchain data for position {position.nft_token_id}: {e}")
        position_dict['pool_name'] = "Unknown/Unknown"
        position_dict['current_value_usdc'] = Decimal(0)
        position_dict['current_total_value'] = Decimal(0)
        position_dict['unrealized_pnl_usdc'] = Decimal(0)
        position_dict['total_pnl_usdc'] = Decimal(0)
        position_dict['pnl_percentage'] = Decimal(0)
        position_dict['pool_base_apr'] = Decimal(0)
        position_dict['effective_apr'] = Decimal(0)
        position_dict['in_range'] = False

    return position_dict


@router.get("", response_model=List[UserListResponse])
async def list_users(
    db: AsyncSession = Depends(get_db)
):
    """
    List all users with comprehensive metrics.

    Returns:
    - User details with CDP wallet address
    - Wallet balance and total portfolio value
    - Position counts (active/closed)
    - Total PnL metrics
    - Agent status
    """
    service = UserService(db)
    users = await service.list_all_users()

    # Enrich with balance data
    from app.core.blockchain_service import blockchain_service

    enriched_users = []
    for user in users:
        # Build user dict from scratch with required fields
        user_dict = {
            'user_id': user.user_id,
            'cdp_wallet_address': user.cdp_wallet_address,
            'status': user.status,
            'created_at': user.created_at,
            'total_portfolio_value': Decimal(0),  # Will be calculated below
            'active_positions_count': 0,
            'total_pnl_usdc': Decimal(0),
            'total_pnl_percentage': Decimal(0),
            'agent_active': bool(user.cdp_wallet_address)
        }

        # Get wallet balance if CDP wallet exists
        if user.cdp_wallet_address:
            try:
                balance = await blockchain_service.get_usdc_balance(user.cdp_wallet_address)
                user_dict['wallet_balance'] = Decimal(str(balance))
            except:
                user_dict['wallet_balance'] = Decimal(0)

        # Get position counts and total value
        positions = await service.get_user_positions(user.user_id)
        active_positions = [p for p in positions if p.status == 'ACTIVE']

        user_dict['active_positions_count'] = len(active_positions)

        # Calculate total portfolio value (wallet + positions)
        positions_value = sum(
            p.current_value_usdc for p in active_positions
            if p.current_value_usdc
        )
        wallet_balance = user_dict.get('wallet_balance', Decimal(0))
        user_dict['total_portfolio_value'] = wallet_balance + positions_value

        # Calculate total PnL
        total_realized_pnl = sum(
            p.realized_pnl_usdc for p in positions
            if p.realized_pnl_usdc
        )
        total_fees = sum(
            p.fees_earned_usdc for p in positions
            if p.fees_earned_usdc
        )
        user_dict['total_pnl_usdc'] = total_realized_pnl + total_fees

        # Calculate PnL percentage if there's an investment
        total_invested = sum(
            p.entry_amount_usdc for p in positions
            if p.entry_amount_usdc
        )
        if total_invested > 0:
            user_dict['total_pnl_percentage'] = (user_dict['total_pnl_usdc'] / total_invested) * 100
        else:
            user_dict['total_pnl_percentage'] = Decimal(0)

        enriched_users.append(user_dict)

    return enriched_users


@router.get("/{user_id}/transactions", response_model=TransactionListResponse)
async def get_transactions(
    user_id: str,
    limit: int = 100,
    offset: int = 0,
    transaction_type: Optional[DBTransactionType] = None,
    sort_order: str = "desc",  # "asc" for oldest first, "desc" for newest first
    db: AsyncSession = Depends(get_db)
):
    """
    Get user transactions with automatic sync from CDP.

    Args:
        user_id: User identifier
        limit: Maximum number of transactions to return
        offset: Number of transactions to skip
        transaction_type: Filter by transaction type
        sort_order: Sort order (asc for oldest first, desc for newest first)

    Returns:
        List of transactions with pool names and details
    """
    # Auto-sync logic
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

    # Enrich transactions with pool names
    enriched_transactions = []
    for tx in transactions:
        # Convert to dict to add pool_name
        tx_dict = TransactionResponse.model_validate(tx).model_dump()

        # Get pool name from event_data for position transactions
        if tx.tx_type in ['POSITION_CREATED', 'POSITION_CLOSED'] and tx.event_data:
            pool_address = tx.event_data.get('pool')
            if pool_address:
                try:
                    pool_info = await pools_service.get_pool(pool_address)
                    # Extract pool name from symbol (e.g., "WETH-USDC-0.05%" -> "WETH-USDC")
                    symbol = pool_info.get('symbol', '')
                    if symbol and '-' in symbol:
                        tx_dict['pool_name'] = symbol.rsplit('-', 1)[0]  # Remove fee tier
                    else:
                        tx_dict['pool_name'] = symbol or 'Unknown'
                except:
                    tx_dict['pool_name'] = 'Unknown'
            else:
                tx_dict['pool_name'] = None
        else:
            tx_dict['pool_name'] = None

        enriched_transactions.append(tx_dict)

    # Get total count for pagination (transactions are already fetched without limit)
    # For proper pagination, we'll need to add a separate count method later
    # For now, use the length of all transactions before slicing
    total_count = len(enriched_transactions)

    # Apply pagination to enriched transactions
    paginated_transactions = enriched_transactions[offset:offset + limit]

    return TransactionListResponse(
        transactions=paginated_transactions,
        total=total_count,
        limit=limit,
        offset=offset
    )


@router.get("/{user_id}/positions", response_model=PositionListResponse)
async def get_positions(
    user_id: str,
    status: Optional[DBPositionStatus] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get user positions with enriched data.

    Returns positions with:
    - Current value and PnL calculations
    - Pool information and APR
    - Range status
    - Fees and rewards earned
    """
    service = UserService(db)
    positions = await service.get_user_positions(user_id=user_id, status=status)

    # Enrich positions with pool data
    enriched_positions = []
    for position in positions:
        enriched = await enrich_position_with_pool_data(position, db)
        enriched_positions.append(enriched)

    # Sort by status (active first) then by created_at (newest first)
    enriched_positions.sort(
        key=lambda p: (
            0 if p.get('status') == 'ACTIVE' else 1,
            -(p.get('created_at').timestamp() if p.get('created_at') else 0)
        )
    )

    return PositionListResponse(
        positions=enriched_positions,
        total=len(enriched_positions)
    )


@router.get("/{user_id}/performance", response_model=PerformanceResponse)
async def get_performance(
    user_id: str,
    period: Optional[TimePeriod] = Query(None, description="Time period for performance calculation (24h, 7d, 30d, all)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get comprehensive user performance metrics.

    Returns:
    - Average APR across active positions
    - Current wallet balance and positions value breakdown
    - Total portfolio value
    - Realized and total PnL metrics
    - Active position count
    """
    from sqlalchemy import select
    from app.database.models import User
    from app.core.blockchain_service import blockchain_service

    service = UserService(db)

    # Get user
    stmt = select(User).where(User.user_id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    # Get current wallet balance
    wallet_balance = 0
    if user.cdp_wallet_address:
        try:
            wallet_balance = await blockchain_service.get_usdc_balance(user.cdp_wallet_address)
        except Exception as e:
            logger.warning(f"Could not fetch wallet balance: {e}")
            wallet_balance = 0

    # Get positions for metrics calculation
    positions = await service.get_user_positions(user_id)

    # Calculate current positions value
    active_positions = [p for p in positions if p.status == 'ACTIVE']
    current_positions_value = sum(
        p.current_value_usdc for p in active_positions
        if p.current_value_usdc
    )

    # Total portfolio value
    total_portfolio_value = Decimal(str(wallet_balance)) + current_positions_value

    # Calculate realized PnL from all positions
    realized_pnl = sum(p.realized_pnl_usdc for p in positions if p.realized_pnl_usdc)
    total_fees = sum(p.fees_earned_usdc for p in positions if p.fees_earned_usdc)
    total_rewards = sum(p.rewards_earned_usdc for p in positions if p.rewards_earned_usdc)

    # Calculate total PnL (realized + fees + rewards)
    total_pnl = realized_pnl + total_fees + total_rewards

    # Calculate PnL percentage based on total invested
    total_invested = sum(p.entry_amount_usdc for p in positions if p.entry_amount_usdc)
    if total_invested > 0:
        realized_pnl_pct = (realized_pnl / total_invested) * 100
        total_pnl_percentage = (total_pnl / total_invested) * 100
    else:
        realized_pnl_pct = Decimal(0)
        total_pnl_percentage = Decimal(0)

    # Calculate average APR from active positions
    apr = Decimal(0)
    if active_positions:
        # Try to get APR from pool data
        total_apr = 0
        active_count = 0
        for position in active_positions:
            if position.pool_address:
                try:
                    pool_data = await pools_service.get_pool_info(position.pool_address)
                    if pool_data and 'apr_7d' in pool_data:
                        pool_apr = float(pool_data.get('apr_7d', 0))
                        total_apr += pool_apr
                        active_count += 1
                except:
                    pass

        if active_count > 0:
            apr = Decimal(str(total_apr / active_count))

    # Return performance data
    return PerformanceResponse(
        # Core metrics with balance breakdown
        apr=apr,
        wallet_balance=Decimal(str(wallet_balance)),  # Current USDC in wallet
        positions_value=current_positions_value,  # Total value in positions
        total_balance=total_portfolio_value,  # wallet + positions
        active_positions=len(active_positions),

        # PnL metrics
        realized_pnl_usdc=realized_pnl,
        realized_pnl_pct=realized_pnl_pct,
        pnl_usdc=total_pnl,  # Total PnL (realized + fees + rewards)
        pnl_pct=total_pnl_percentage  # Total PnL percentage
    )