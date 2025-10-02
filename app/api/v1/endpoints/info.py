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
    hedge_info = None

    # Fetch live hedge info from LiquidityManager contract
    live_hedge_data = None
    try:
        from app.core.hedge_service import hedge_service
        hedge_response = await hedge_service.get_hedge_position_by_token_id(position.nft_token_id)

        if hedge_response.positions and len(hedge_response.positions) > 0:
            live_hedge = hedge_response.positions[0]
            live_hedge_data = {
                'is_hedged': live_hedge.is_hedged,
                'collateral': live_hedge.collateral_usdc,
                'debt_asset': live_hedge.hedged_asset_symbol,
                'debt_amount': live_hedge.debt_amount,
                'debt_value_usd': live_hedge.debt_usd,
                'hedged_asset': live_hedge.hedged_asset,
                'collateral_supply_apy': live_hedge.collateral_supply_apy,
                'hedged_asset_borrow_apy': live_hedge.hedged_asset_borrow_apy
            }
            logger.info(f"Position {position.nft_token_id} - Live hedge info: {live_hedge_data}")
    except Exception as e:
        logger.warning(f"Could not fetch live hedge info for position {position.nft_token_id}: {e}")

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
            usdc_returned_wei = position_created_tx.event_data.get('usdc_returned', 0)
            usdc_returned = Decimal(str(usdc_returned_wei)) / Decimal(1_000_000) if usdc_returned_wei else Decimal(0)
            net_entry_amount = amount - usdc_returned

            # Build hedge info from event_data (as fallback for missing fields)
            is_hedged = position_created_tx.event_data.get('is_hedged', False)
            if is_hedged or live_hedge_data:
                # Get token symbol from address
                hedged_asset = position_created_tx.event_data.get('hedged_asset', '0x0')
                if hedged_asset and hedged_asset != '0x0':
                    # Simple mapping for known assets
                    debt_asset = 'WETH' if '0x42000000' in hedged_asset else 'cbBTC'
                else:
                    debt_asset = None

                # Extract hedge values from event_data (convert from wei if needed)
                usdc_invested = position_created_tx.event_data.get('usdc_invested', 0)
                hedge_collateral = position_created_tx.event_data.get('hedge_collateral', 0)
                hedge_debt = position_created_tx.event_data.get('hedge_debt', 0)
                hedge_debt_usd = position_created_tx.event_data.get('hedge_debt_usd', 0)

                # Convert from wei if values are large
                lp_amount = Decimal(usdc_invested) / Decimal(1_000_000) if usdc_invested > 1000 else Decimal(usdc_invested)
                collateral = Decimal(hedge_collateral) / Decimal(1_000_000) if hedge_collateral > 1000 else Decimal(hedge_collateral)
                debt_value_usd = Decimal(hedge_debt_usd) if isinstance(hedge_debt_usd, (int, float)) else Decimal(str(hedge_debt_usd))

                # Calculate debt amount in asset (divide by decimals)
                decimals = 18 if debt_asset == 'WETH' else 8
                debt_amount = Decimal(hedge_debt) / Decimal(10 ** decimals) if hedge_debt > 0 else Decimal(0)

                hedge_info = {
                    'is_hedged': True,
                    'lp_amount': lp_amount,
                    'collateral': collateral,
                    'debt_asset': debt_asset,
                    'debt_amount': debt_amount,
                    'debt_value_usd': debt_value_usd,
                    'tick_lower': position_created_tx.event_data.get('tick_lower'),
                    'tick_upper': position_created_tx.event_data.get('tick_upper')
                }

                # Override with live data if available
                if live_hedge_data:
                    hedge_info['is_hedged'] = live_hedge_data['is_hedged']
                    hedge_info['collateral'] = live_hedge_data['collateral']
                    hedge_info['debt_asset'] = live_hedge_data['debt_asset']
                    hedge_info['debt_amount'] = live_hedge_data['debt_amount']
                    hedge_info['debt_value_usd'] = live_hedge_data['debt_value_usd']
                    if 'hedged_asset' in live_hedge_data:
                        hedge_info['hedged_asset'] = live_hedge_data['hedged_asset']
                    if 'collateral_supply_apy' in live_hedge_data:
                        hedge_info['collateral_supply_apy'] = live_hedge_data['collateral_supply_apy']
                    if 'hedged_asset_borrow_apy' in live_hedge_data:
                        hedge_info['hedged_asset_borrow_apy'] = live_hedge_data['hedged_asset_borrow_apy']

    # Override the entry_amount_usdc with the net amount
    position_dict['entry_amount_usdc'] = net_entry_amount
    position_dict['hedge'] = hedge_info

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
            # position_data is a PositionInfo object, use attributes not .get()
            blockchain_value = Decimal(str(getattr(position_data, 'current_value_usd', 0)))

            # Calculate net hedge value (collateral - debt) if position is hedged
            net_hedge_value = Decimal(0)
            if hedge_info and hedge_info.get('is_hedged'):
                collateral = Decimal(str(hedge_info.get('collateral', 0)))
                debt_value_usd = Decimal(str(hedge_info.get('debt_value_usd', 0)))
                net_hedge_value = collateral - debt_value_usd

                # Enrich hedge_info with LP position data
                hedge_info['lp_current_value_usd'] = blockchain_value
                hedge_info['unclaimed_fees_usd'] = getattr(position_data, 'unclaimed_fees_usd', None)
                hedge_info['unclaimed_rewards_aero'] = getattr(position_data, 'unclaimed_rewards_aero', None)

            position_dict['current_value_usdc'] = blockchain_value + net_hedge_value
            position_dict['current_total_value'] = blockchain_value + net_hedge_value
            position_dict['pool_name'] = getattr(position_data, 'pool_name', 'Unknown/Unknown')
            position_dict['in_range'] = getattr(position_data, 'in_range', False)

            # Add token information from blockchain
            position_dict['token0'] = getattr(position_data, 'token0', None)
            position_dict['token1'] = getattr(position_data, 'token1', None)
            position_dict['token0_amount'] = getattr(position_data, 'token0_amount', None)
            position_dict['token1_amount'] = getattr(position_data, 'token1_amount', None)

            # Add tick information from blockchain
            position_dict['tick_lower'] = getattr(position_data, 'tick_lower', None)
            position_dict['tick_upper'] = getattr(position_data, 'tick_upper', None)
            position_dict['current_tick'] = getattr(position_data, 'current_tick', None)

            # Add unclaimed fees and rewards from blockchain (also at top level)
            position_dict['unclaimed_fees_usd'] = getattr(position_data, 'unclaimed_fees_usd', None)
            position_dict['unclaimed_rewards_aero'] = getattr(position_data, 'unclaimed_rewards_aero', None)

            # Update staked status from blockchain (overrides database value)
            position_dict['staked'] = getattr(position_data, 'staked', False)
            # Update gauge_address if available
            if hasattr(position_data, 'gauge_address') and position_data.gauge_address:
                position_dict['gauge_address'] = position_data.gauge_address

            # Get pool APR data from pools service
            if position.pool_address:
                try:
                    pool_info = await pools_service.get_pool(position.pool_address, include_effective_apr=True)
                    base_apr = pool_info.get('apr') or 0
                    # Get standard effective APR from the range options
                    effective_apr_range = pool_info.get('effective_apr_range')
                    standard_apr = effective_apr_range.get('standard', 0) if effective_apr_range else 0

                    position_dict['pool_base_apr'] = Decimal(str(base_apr))
                    position_dict['effective_apr'] = Decimal(str(standard_apr))
                    logger.debug(f"Position {position.nft_token_id} - Base APR: {base_apr}, Effective APR: {standard_apr}")
                except Exception as e:
                    logger.warning(f"Could not fetch pool APR for {position.pool_address}: {e}")
                    position_dict['pool_base_apr'] = Decimal(0)
                    position_dict['effective_apr'] = Decimal(0)

            # Calculate neutral_ratio for hedged positions
            # Formula: debt_amount / relevant_token_amount (token0 for WETH, token1 for cbBTC)
            neutral_ratio = None
            if hedge_info and hedge_info.get('is_hedged'):
                try:
                    debt_amount = hedge_info.get('debt_amount')
                    token0 = position_dict.get('token0', '').lower()
                    token1 = position_dict.get('token1', '').lower()
                    token0_amount = position_dict.get('token0_amount')
                    token1_amount = position_dict.get('token1_amount')

                    # Determine which token to use based on pool composition
                    # For WETH/USDC: use token0_amount (WETH is typically token0)
                    # For USDC/cbBTC: use token1_amount (cbBTC is typically token1)
                    from app.core.config import settings
                    weth_address = settings.weth_address.lower()
                    cbbtc_address = settings.cbbtc_address.lower() if hasattr(settings, 'cbbtc_address') else None

                    if debt_amount and debt_amount > 0:
                        if token0 == weth_address and token0_amount and token0_amount > 0:
                            # WETH/USDC pool - use token0_amount (WETH)
                            neutral_ratio = Decimal(str(debt_amount)) / Decimal(str(token0_amount))
                            logger.debug(f"Position {position.nft_token_id} - WETH pool neutral_ratio: {neutral_ratio}")
                        elif cbbtc_address and token1 == cbbtc_address and token1_amount and token1_amount > 0:
                            # USDC/cbBTC pool - use token1_amount (cbBTC)
                            neutral_ratio = Decimal(str(debt_amount)) / Decimal(str(token1_amount))
                            logger.debug(f"Position {position.nft_token_id} - cbBTC pool neutral_ratio: {neutral_ratio}")

                    position_dict['neutral_ratio'] = neutral_ratio
                except Exception as e:
                    logger.warning(f"Could not calculate neutral_ratio for position {position.nft_token_id}: {e}")
                    position_dict['neutral_ratio'] = None
            else:
                position_dict['neutral_ratio'] = None

            # Calculate net_apr (weighted average APR considering all position components)
            # Formula: ((effective_apr × lp_value) + (collateral_apy × collateral) - (borrow_apy × debt)) / (lp_value + collateral - debt)
            net_apr = None
            if hedge_info and hedge_info.get('is_hedged'):
                try:
                    effective_apr = position_dict.get('effective_apr', Decimal(0))
                    lp_value = hedge_info.get('lp_current_value_usd', Decimal(0)) or Decimal(0)
                    collateral_apy = hedge_info.get('collateral_supply_apy', Decimal(0)) or Decimal(0)
                    collateral = hedge_info.get('collateral', Decimal(0)) or Decimal(0)
                    borrow_apy = hedge_info.get('hedged_asset_borrow_apy', Decimal(0)) or Decimal(0)
                    debt_value = hedge_info.get('debt_value_usd', Decimal(0)) or Decimal(0)

                    # Calculate total position value (denominator)
                    total_value = lp_value + collateral - debt_value

                    # Calculate weighted net APR
                    if total_value > 0:
                        numerator = (
                            (effective_apr * lp_value) +
                            (collateral_apy * collateral) -
                            (borrow_apy * debt_value)
                        )
                        net_apr = numerator / total_value
                    else:
                        net_apr = Decimal(0)

                    position_dict['net_apr'] = net_apr
                    logger.debug(f"Position {position.nft_token_id} - Net APR: {net_apr}")
                except Exception as e:
                    logger.warning(f"Could not calculate net_apr for position {position.nft_token_id}: {e}")
                    position_dict['net_apr'] = None
            else:
                # For non-hedged positions, net_apr = effective_apr
                position_dict['net_apr'] = position_dict.get('effective_apr')

            # Calculate PnL (simple version - current value minus entry amount)
            current_value = blockchain_value + net_hedge_value

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
            position_dict['unclaimed_fees_usd'] = None
            position_dict['unclaimed_rewards_aero'] = None
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
        position_dict['unclaimed_fees_usd'] = None
        position_dict['unclaimed_rewards_aero'] = None

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
    # Sync blockchain data to get latest transactions
    service = UserService(db)
    sync_result = await service.sync_blockchain_data(user_id)

    if sync_result.get('success'):
        logger.info(f"Synced {sync_result.get('transactions_synced', 0)} transactions for user {user_id}")
    transactions = await service.get_user_transactions(
        user_id=user_id,
        limit=limit,
        offset=offset,
        transaction_type=transaction_type,
        sort_order=sort_order
    )

    # Enrich transactions with pool names and in_range status
    enriched_transactions = []

    # Get current positions to check if they're in range
    from app.database.models import Position
    from sqlalchemy import select, and_
    positions_stmt = select(Position).where(
        and_(
            Position.user_id == user_id,
            Position.status == 'ACTIVE'
        )
    )
    positions_result = await db.execute(positions_stmt)
    active_positions = {p.token_id: p for p in positions_result.scalars().all()}

    for tx in transactions:
        # Convert to dict to add pool_name and in_range
        tx_dict = TransactionResponse.model_validate(tx).model_dump()

        # Check if position is in range for position-related transactions
        if tx.position_id and tx.tx_type in ['POSITION_CREATED', 'POSITION_CLOSED']:
            # Check if this position is still active
            position = active_positions.get(tx.position_id)
            if position:
                # Check if position is in range
                try:
                    from app.core.positions_service import positions_service
                    position_info = await positions_service.get_position_by_id(tx.position_id)
                    if position_info:
                        tx_dict['in_range'] = position_info.in_range
                    else:
                        tx_dict['in_range'] = None
                except Exception as e:
                    logger.debug(f"Could not check in_range for position {tx.position_id}: {e}")
                    tx_dict['in_range'] = None
            else:
                # Position is closed or doesn't exist
                tx_dict['in_range'] = False if tx.tx_type == 'POSITION_CLOSED' else None
        else:
            tx_dict['in_range'] = None

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

    # Sync blockchain data to get latest positions
    await service.sync_blockchain_data(user_id)

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

    # Sync blockchain data to get latest performance metrics
    await service.sync_blockchain_data(user_id)

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

            # Always publish balance event when performance is checked
            # This ensures agent manager is aware of current balance
            if wallet_balance > 0:
                try:
                    from app.services.agent_management_service import get_agent_service
                    agent_service = get_agent_service()

                    # Check if user has deposited 50+ USDC
                    has_deposited_50 = wallet_balance >= 50 or (hasattr(user, 'has_deposited_50_usdc') and user.has_deposited_50_usdc)

                    # Publish balance event to trigger agent if needed
                    await agent_service.publish_balance_event(
                        user_id=user_id,
                        balance=wallet_balance,
                        event_type="BALANCE_CHECK",
                        has_deposited_50_usdc=has_deposited_50
                    )
                    logger.info(f"Published balance check event for {user_id}: {wallet_balance} USDC")
                except Exception as e:
                    logger.warning(f"Could not publish balance event: {e}")
                    # Continue even if event publishing fails

        except Exception as e:
            logger.warning(f"Could not fetch wallet balance: {e}")
            wallet_balance = 0

    # Get positions for metrics calculation
    positions = await service.get_user_positions(user_id)

    # Enrich active positions with blockchain data to get accurate current values
    active_positions = [p for p in positions if p.status == 'ACTIVE']
    enriched_active_positions = []
    for position in active_positions:
        try:
            enriched = await enrich_position_with_pool_data(position, db)
            enriched_active_positions.append(enriched)
        except Exception as e:
            logger.warning(f"Could not enrich position {position.nft_token_id}: {e}")
            continue

    # Calculate current positions value using enriched blockchain data
    current_positions_value = sum(
        Decimal(str(p.get('current_value_usdc', 0))) for p in enriched_active_positions
        if p.get('current_value_usdc')
    )

    # Total portfolio value
    total_portfolio_value = Decimal(str(wallet_balance)) + current_positions_value

    # Calculate PnL metrics
    # Realized PnL from closed positions only
    closed_positions = [p for p in positions if p.status == 'CLOSED']
    realized_pnl = sum(p.realized_pnl_usdc for p in closed_positions if p.realized_pnl_usdc)

    # Unrealized PnL from active positions (current_value - entry_amount)
    unrealized_pnl = sum(
        Decimal(str(p.get('unrealized_pnl_usdc', 0))) for p in enriched_active_positions
        if p.get('unrealized_pnl_usdc') is not None
    )

    # Fees and rewards from all positions
    total_fees = sum(p.fees_earned_usdc for p in positions if p.fees_earned_usdc)
    total_rewards = sum(p.rewards_earned_usdc for p in positions if p.rewards_earned_usdc)

    # Total PnL = unrealized + realized + fees + rewards
    total_pnl = unrealized_pnl + realized_pnl + total_fees + total_rewards

    # Calculate PnL percentage based on total invested
    total_invested = sum(p.entry_amount_usdc for p in positions if p.entry_amount_usdc)
    if total_invested > 0:
        realized_pnl_pct = (realized_pnl / total_invested) * 100
        total_pnl_percentage = (total_pnl / total_invested) * 100
    else:
        realized_pnl_pct = Decimal(0)
        total_pnl_percentage = Decimal(0)

    # Calculate weighted average APR from enriched active positions using net_apr
    # Formula: Σ(current_value_usdc × net_apr) / Σ(current_value_usdc)
    apr = Decimal(0)
    if enriched_active_positions:
        weighted_apr_sum = Decimal(0)
        total_value = Decimal(0)

        for position_dict in enriched_active_positions:
            net_apr = position_dict.get('net_apr')
            current_value = position_dict.get('current_value_usdc')

            if net_apr is not None and current_value and current_value > 0:
                weighted_apr_sum += Decimal(str(net_apr)) * Decimal(str(current_value))
                total_value += Decimal(str(current_value))
                logger.debug(f"Position {position_dict.get('nft_token_id')}: net_apr={net_apr}, value={current_value}")

        if total_value > 0:
            apr = weighted_apr_sum / total_value
            logger.info(f"Calculated weighted APR: {apr} from {len(enriched_active_positions)} positions")

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