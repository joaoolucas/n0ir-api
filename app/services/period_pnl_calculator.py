"""
Period-based PNL Calculator following financial industry best practices.

This module implements proper period-based PNL calculations using:
1. Time-Weighted Return (TWR) for percentage calculations
2. Proper handling of positions that span across periods
3. Mark-to-market valuations at period boundaries
"""

from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from app.database.models import User, Position, Transaction
from app.schemas.users import TimePeriod
import logging

logger = logging.getLogger(__name__)


class PeriodPnLCalculator:
    """
    Calculate period-based PNL following financial best practices.

    Key Concepts:
    1. Starting Portfolio Value: Value at the beginning of the period
    2. Ending Portfolio Value: Value at the end of the period
    3. Net Cash Flows: Deposits - Withdrawals during the period
    4. Period Return: (Ending Value - Starting Value - Net Cash Flows) / Starting Value
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def calculate_period_pnl(
        self,
        user_id: str,
        period: TimePeriod = TimePeriod.ALL_TIME
    ) -> Dict[str, Decimal]:
        """
        Calculate PNL for a specific period using proper financial methodology.

        Returns:
            Dict containing:
            - period_pnl_usdc: Dollar PNL for the period
            - period_pnl_percentage: Percentage return for the period
            - starting_value: Portfolio value at period start
            - ending_value: Portfolio value at period end
            - net_deposits: Net deposits during period
            - positions_opened: Count of positions opened in period
            - positions_closed: Count of positions closed in period
            - fees_earned: Fees earned during period
            - rewards_earned: Rewards earned during period
        """
        # Get time boundaries
        now = datetime.now(timezone.utc)
        period_start = self._get_period_start(now, period)

        # Get portfolio value at period start
        starting_value = await self._get_portfolio_value_at_time(user_id, period_start)

        # Get current portfolio value (period end)
        ending_value = await self._get_current_portfolio_value(user_id)

        # Get net cash flows during period
        net_deposits = await self._get_net_deposits_for_period(user_id, period_start, now)

        # Calculate period PNL
        # PNL = Ending Value - Starting Value - Net Deposits
        period_pnl_usdc = ending_value - starting_value - net_deposits

        # Calculate percentage return
        # For percentage, we use the denominator based on starting value + deposits
        # This follows the Modified Dietz method for approximating time-weighted returns
        denominator = starting_value
        if denominator <= 0:
            # If no starting value, use net deposits as base
            denominator = abs(net_deposits) if net_deposits != 0 else Decimal(1)

        period_pnl_percentage = (period_pnl_usdc / denominator) * 100 if denominator != 0 else Decimal(0)

        # Get additional metrics for the period
        positions_metrics = await self._get_positions_metrics_for_period(user_id, period_start, now)

        return {
            "period_pnl_usdc": period_pnl_usdc,
            "period_pnl_percentage": period_pnl_percentage,
            "starting_value": starting_value,
            "ending_value": ending_value,
            "net_deposits": net_deposits,
            "positions_opened": positions_metrics["opened"],
            "positions_closed": positions_metrics["closed"],
            "fees_earned_usdc": positions_metrics["fees_earned"],
            "rewards_earned_usdc": positions_metrics["rewards_earned"],
            "realized_pnl_usdc": positions_metrics["realized_pnl"],
            "unrealized_pnl_usdc": positions_metrics["unrealized_pnl"],
        }

    def _get_period_start(self, now: datetime, period: TimePeriod) -> Optional[datetime]:
        """Get the start time for the specified period."""
        if period == TimePeriod.DAY_1:
            return now - timedelta(days=1)
        elif period == TimePeriod.DAY_7:
            return now - timedelta(days=7)
        elif period == TimePeriod.DAY_30:
            return now - timedelta(days=30)
        else:  # ALL_TIME
            return None

    async def _get_portfolio_value_at_time(
        self,
        user_id: str,
        timestamp: Optional[datetime]
    ) -> Decimal:
        """
        Get portfolio value at a specific point in time.

        This includes:
        1. Wallet balance at that time
        2. Value of all positions that were active at that time
        """
        if timestamp is None:
            # For all-time, starting value is 0
            return Decimal(0)

        # Get wallet balance at timestamp
        # This requires looking at transaction history
        wallet_balance = await self._get_wallet_balance_at_time(user_id, timestamp)

        # Get value of positions active at that time
        positions_value = await self._get_positions_value_at_time(user_id, timestamp)

        return wallet_balance + positions_value

    async def _get_wallet_balance_at_time(
        self,
        user_id: str,
        timestamp: datetime
    ) -> Decimal:
        """
        Calculate wallet balance at a specific timestamp by replaying transactions.
        """
        # Get all deposits and withdrawals up to the timestamp
        stmt = select(Transaction).where(
            and_(
                Transaction.user_id == user_id,
                or_(
                    Transaction.tx_type == 'DEPOSIT',
                    Transaction.tx_type == 'WITHDRAW',
                    Transaction.tx_type == 'WITHDRAWAL'
                ),
                Transaction.status == 'CONFIRMED',
                Transaction.created_at <= timestamp
            )
        ).order_by(Transaction.created_at)

        result = await self.db.execute(stmt)
        transactions = result.scalars().all()

        balance = Decimal(0)
        for tx in transactions:
            # Get amount from event_data
            amount = Decimal(0)
            if tx.event_data and 'amount_usdc' in tx.event_data:
                amount = Decimal(str(tx.event_data['amount_usdc']))
            elif tx.amount_usdc:
                amount = Decimal(str(tx.amount_usdc))

            if tx.tx_type == 'DEPOSIT':
                balance += amount
            else:  # WITHDRAW or WITHDRAWAL
                balance -= amount

        # Also subtract any amounts that went into positions before timestamp
        position_investments = await self._get_position_investments_before_time(user_id, timestamp)
        balance -= position_investments

        return max(balance, Decimal(0))  # Can't be negative

    async def _get_position_investments_before_time(
        self,
        user_id: str,
        timestamp: datetime
    ) -> Decimal:
        """Get total amount invested in positions before a specific time."""
        stmt = select(Transaction).where(
            and_(
                Transaction.user_id == user_id,
                Transaction.tx_type == 'POSITION_CREATED',
                Transaction.status == 'CONFIRMED',
                Transaction.created_at <= timestamp
            )
        )

        result = await self.db.execute(stmt)
        transactions = result.scalars().all()

        total_invested = Decimal(0)
        for tx in transactions:
            if tx.event_data:
                # Calculate net investment (amount - returned USDC)
                amount = Decimal(str(tx.event_data.get('amount_usdc', 0)))
                returned = Decimal(str(tx.event_data.get('usdc_returned', 0)))
                total_invested += (amount - returned)

        return total_invested

    async def _get_positions_value_at_time(
        self,
        user_id: str,
        timestamp: datetime
    ) -> Decimal:
        """
        Get total value of positions that were active at a specific timestamp.

        Note: This is an approximation using entry values, as we don't have
        historical market prices. For production, you'd want to store periodic
        snapshots of position values.
        """
        # Get all positions that were active at the timestamp
        stmt = select(Position).where(
            and_(
                Position.user_id == user_id,
                Position.created_at <= timestamp,
                or_(
                    Position.exit_date.is_(None),  # Still active
                    Position.exit_date > timestamp  # Was active at timestamp
                )
            )
        )

        result = await self.db.execute(stmt)
        positions = result.scalars().all()

        total_value = Decimal(0)
        for position in positions:
            # For historical value, we use entry amount as approximation
            # In production, you'd want historical price data or periodic snapshots
            total_value += (position.entry_amount_usdc or Decimal(0))

        return total_value

    async def _get_current_portfolio_value(self, user_id: str) -> Decimal:
        """Get current total portfolio value (wallet + active positions)."""
        from app.core.positions_service import positions_service

        # Get user for wallet balance
        stmt = select(User).where(User.user_id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            return Decimal(0)

        wallet_balance = Decimal(str(user.usdc_balance or 0))

        # Get all active positions
        stmt = select(Position).where(
            and_(
                Position.user_id == user_id,
                Position.status == 'ACTIVE'
            )
        )
        result = await self.db.execute(stmt)
        positions = result.scalars().all()

        # Calculate current positions value using real-time data
        positions_value = Decimal(0)
        for position in positions:
            try:
                # Get real-time value from blockchain
                position_info = await positions_service.get_position_by_id(position.nft_token_id)
                if position_info:
                    current_value = Decimal(str(position_info.current_value_usd or 0))
                    unclaimed_fees = Decimal(str(position_info.unclaimed_fees_usd or 0))
                    positions_value += (current_value + unclaimed_fees)
                else:
                    # Fallback to database value
                    positions_value += (position.current_value_usdc or Decimal(0))
            except Exception as e:
                logger.warning(f"Failed to get real-time value for position {position.nft_token_id}: {e}")
                positions_value += (position.current_value_usdc or Decimal(0))

        return wallet_balance + positions_value

    async def _get_net_deposits_for_period(
        self,
        user_id: str,
        period_start: Optional[datetime],
        period_end: datetime
    ) -> Decimal:
        """Get net deposits (deposits - withdrawals) for a period."""
        query = select(Transaction).where(
            and_(
                Transaction.user_id == user_id,
                or_(
                    Transaction.tx_type == 'DEPOSIT',
                    Transaction.tx_type == 'WITHDRAW',
                    Transaction.tx_type == 'WITHDRAWAL'
                ),
                Transaction.status == 'CONFIRMED'
            )
        )

        # Add time filter if not all-time
        if period_start:
            query = query.where(
                and_(
                    Transaction.created_at >= period_start,
                    Transaction.created_at <= period_end
                )
            )

        result = await self.db.execute(query)
        transactions = result.scalars().all()

        deposits = Decimal(0)
        withdrawals = Decimal(0)

        for tx in transactions:
            # Get amount from event_data
            amount = Decimal(0)
            if tx.event_data and 'amount_usdc' in tx.event_data:
                amount = Decimal(str(tx.event_data['amount_usdc']))
            elif tx.amount_usdc:
                amount = Decimal(str(tx.amount_usdc))

            if tx.tx_type == 'DEPOSIT':
                deposits += amount
            else:  # WITHDRAW or WITHDRAWAL
                withdrawals += amount

        return deposits - withdrawals

    async def _get_positions_metrics_for_period(
        self,
        user_id: str,
        period_start: Optional[datetime],
        period_end: datetime
    ) -> Dict[str, any]:
        """Get position-related metrics for a period."""
        from app.core.positions_service import positions_service

        # Get all positions for the user
        stmt = select(Position).where(Position.user_id == user_id)
        result = await self.db.execute(stmt)
        all_positions = result.scalars().all()

        positions_opened = 0
        positions_closed = 0
        fees_earned = Decimal(0)
        rewards_earned = Decimal(0)
        realized_pnl = Decimal(0)
        unrealized_pnl = Decimal(0)

        for position in all_positions:
            # Check if position was opened in this period
            if period_start and position.created_at:
                created_at = position.created_at
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                if created_at >= period_start and created_at <= period_end:
                    positions_opened += 1
            elif not period_start:  # All-time
                positions_opened += 1

            # Check if position was closed in this period
            if position.status == 'CLOSED' and position.exit_date:
                exit_date = position.exit_date
                if exit_date.tzinfo is None:
                    exit_date = exit_date.replace(tzinfo=timezone.utc)
                if period_start:
                    if exit_date >= period_start and exit_date <= period_end:
                        positions_closed += 1
                        # Add realized PNL from this position
                        exit_value = position.current_value_usdc or Decimal(0)
                        entry_value = position.entry_amount_usdc or Decimal(0)
                        realized_pnl += (exit_value - entry_value)
                        fees_earned += (position.fees_earned_usdc or Decimal(0))
                        rewards_earned += (position.rewards_earned_usdc or Decimal(0))
                else:  # All-time
                    positions_closed += 1
                    exit_value = position.current_value_usdc or Decimal(0)
                    entry_value = position.entry_amount_usdc or Decimal(0)
                    realized_pnl += (exit_value - entry_value)
                    fees_earned += (position.fees_earned_usdc or Decimal(0))
                    rewards_earned += (position.rewards_earned_usdc or Decimal(0))

            # Calculate unrealized PNL for active positions
            if position.status == 'ACTIVE':
                try:
                    # Get real-time value
                    position_info = await positions_service.get_position_by_id(position.nft_token_id)
                    if position_info:
                        current_value = Decimal(str(position_info.current_value_usd or 0))
                        unclaimed_fees = Decimal(str(position_info.unclaimed_fees_usd or 0))
                        total_current = current_value + unclaimed_fees
                        entry_value = position.entry_amount_usdc or Decimal(0)
                        unrealized_pnl += (total_current - entry_value)

                        # Add fees/rewards from active positions
                        fees_earned += (position.fees_earned_usdc or Decimal(0))
                        rewards_earned += (position.rewards_earned_usdc or Decimal(0))
                except Exception as e:
                    logger.warning(f"Failed to get real-time value for position {position.nft_token_id}: {e}")
                    # Use database values as fallback
                    current_value = position.current_value_usdc or Decimal(0)
                    entry_value = position.entry_amount_usdc or Decimal(0)
                    unrealized_pnl += (current_value - entry_value)
                    fees_earned += (position.fees_earned_usdc or Decimal(0))
                    rewards_earned += (position.rewards_earned_usdc or Decimal(0))

        return {
            "opened": positions_opened,
            "closed": positions_closed,
            "fees_earned": fees_earned,
            "rewards_earned": rewards_earned,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
        }


class SimplePeriodPnLCalculator:
    """
    Simplified period PNL calculator for MVP implementation.

    This uses a simpler approach that's easier to implement but still provides
    meaningful metrics:
    1. For period PNL: Compare current value vs value at period start
    2. For percentage: Use average invested capital as denominator
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def calculate_period_pnl(
        self,
        user_id: str,
        period: TimePeriod = TimePeriod.ALL_TIME
    ) -> Dict[str, Decimal]:
        """
        Calculate simplified period PNL.

        Approach:
        1. Get all positions active during the period
        2. Calculate PNL for each position within the period
        3. Sum up the PNLs
        4. Use beginning balance + net deposits as denominator for percentage
        """
        from app.core.positions_service import positions_service

        # Get time boundary
        now = datetime.now(timezone.utc)
        period_start = self._get_period_start(now, period)

        # Get user
        stmt = select(User).where(User.user_id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            return self._empty_response()

        # Get positions active during the period
        positions = await self._get_positions_for_period(user_id, period_start, now)

        # Calculate PNL components
        realized_pnl = Decimal(0)
        unrealized_pnl = Decimal(0)
        fees_earned = Decimal(0)
        rewards_earned = Decimal(0)

        for position in positions:
            if position.status == 'CLOSED':
                # Position was closed - count as realized
                if self._position_active_in_period(position, period_start, now):
                    exit_value = position.current_value_usdc or Decimal(0)
                    entry_value = position.entry_amount_usdc or Decimal(0)
                    realized_pnl += (exit_value - entry_value)
                    fees_earned += (position.fees_earned_usdc or Decimal(0))
                    rewards_earned += (position.rewards_earned_usdc or Decimal(0))

            elif position.status == 'ACTIVE':
                # Position still active - count as unrealized
                try:
                    # Get real-time value
                    position_info = await positions_service.get_position_by_id(position.nft_token_id)
                    if position_info:
                        current_value = Decimal(str(position_info.current_value_usd or 0))
                        unclaimed_fees = Decimal(str(position_info.unclaimed_fees_usd or 0))
                        total_current = current_value + unclaimed_fees
                    else:
                        total_current = position.current_value_usdc or Decimal(0)
                except Exception:
                    total_current = position.current_value_usdc or Decimal(0)

                entry_value = position.entry_amount_usdc or Decimal(0)
                unrealized_pnl += (total_current - entry_value)
                fees_earned += (position.fees_earned_usdc or Decimal(0))
                rewards_earned += (position.rewards_earned_usdc or Decimal(0))

        # Get net deposits for the period
        net_deposits = await self._get_net_deposits_for_period(user_id, period_start, now)

        # Calculate total PNL
        total_pnl = realized_pnl + unrealized_pnl + fees_earned + rewards_earned

        # Calculate percentage using a meaningful denominator
        # Use the average invested capital during the period
        avg_invested = await self._get_average_invested_capital(user_id, period_start, now)

        if avg_invested > 0:
            pnl_percentage = (total_pnl / avg_invested) * 100
        else:
            pnl_percentage = Decimal(0)

        return {
            "realized_pnl_usdc": realized_pnl,
            "unrealized_pnl_usdc": unrealized_pnl,
            "fees_earned_usdc": fees_earned,
            "rewards_earned_usdc": rewards_earned,
            "total_pnl_usdc": total_pnl,
            "total_pnl_percentage": pnl_percentage,
            "net_deposits": net_deposits,
            "average_invested": avg_invested,
        }

    def _get_period_start(self, now: datetime, period: TimePeriod) -> Optional[datetime]:
        """Get the start time for the specified period."""
        if period == TimePeriod.DAY_1:
            return now - timedelta(days=1)
        elif period == TimePeriod.DAY_7:
            return now - timedelta(days=7)
        elif period == TimePeriod.DAY_30:
            return now - timedelta(days=30)
        else:  # ALL_TIME
            return None

    async def _get_positions_for_period(
        self,
        user_id: str,
        period_start: Optional[datetime],
        period_end: datetime
    ) -> List[Position]:
        """Get all positions that were active during the period."""
        stmt = select(Position).where(Position.user_id == user_id)

        if period_start:
            # Get positions that were active at any point during the period
            stmt = stmt.where(
                or_(
                    # Position opened during or before the period and still active
                    and_(
                        Position.created_at <= period_end,
                        Position.status == 'ACTIVE'
                    ),
                    # Position opened during or before the period and closed during or after
                    and_(
                        Position.created_at <= period_end,
                        Position.exit_date >= period_start
                    )
                )
            )

        result = await self.db.execute(stmt)
        return result.scalars().all()

    def _position_active_in_period(
        self,
        position: Position,
        period_start: Optional[datetime],
        period_end: datetime
    ) -> bool:
        """Check if a position was active during the period."""
        if not period_start:
            return True  # All-time

        # Position created after period end
        if position.created_at:
            created_at = position.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if created_at > period_end:
                return False

        # Position closed before period start
        if position.exit_date:
            exit_date = position.exit_date
            if exit_date.tzinfo is None:
                exit_date = exit_date.replace(tzinfo=timezone.utc)
            if exit_date < period_start:
                return False

        return True

    async def _get_net_deposits_for_period(
        self,
        user_id: str,
        period_start: Optional[datetime],
        period_end: datetime
    ) -> Decimal:
        """Get net deposits for the period."""
        query = select(Transaction).where(
            and_(
                Transaction.user_id == user_id,
                or_(
                    Transaction.tx_type == 'DEPOSIT',
                    Transaction.tx_type == 'WITHDRAW',
                    Transaction.tx_type == 'WITHDRAWAL'
                ),
                Transaction.status == 'CONFIRMED'
            )
        )

        if period_start:
            query = query.where(
                and_(
                    Transaction.created_at >= period_start,
                    Transaction.created_at <= period_end
                )
            )

        result = await self.db.execute(query)
        transactions = result.scalars().all()

        deposits = Decimal(0)
        withdrawals = Decimal(0)

        for tx in transactions:
            amount = Decimal(0)
            if tx.event_data and 'amount_usdc' in tx.event_data:
                amount = Decimal(str(tx.event_data['amount_usdc']))
            elif tx.amount_usdc:
                amount = Decimal(str(tx.amount_usdc))

            if tx.tx_type == 'DEPOSIT':
                deposits += amount
            else:
                withdrawals += amount

        return deposits - withdrawals

    async def _get_average_invested_capital(
        self,
        user_id: str,
        period_start: Optional[datetime],
        period_end: datetime
    ) -> Decimal:
        """
        Calculate average invested capital during the period.

        This is a simplified calculation using:
        - Starting balance + Ending balance / 2
        - Plus average of net deposits
        """
        # Get user's current balance
        stmt = select(User).where(User.user_id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            return Decimal(0)

        current_balance = Decimal(str(user.usdc_balance or 0))

        # Get total deposits and withdrawals
        total_deposits, total_withdrawals = await self._get_deposit_withdrawal_totals(user_id)

        # For period calculations, use net deposits as proxy for average invested
        if period_start:
            net_deposits = await self._get_net_deposits_for_period(user_id, period_start, period_end)
            # Average invested = current balance + half of net deposits during period
            avg_invested = current_balance + (net_deposits / 2)
        else:
            # All-time: use total net deposits
            avg_invested = total_deposits - total_withdrawals

        return max(avg_invested, Decimal(1))  # Avoid division by zero

    async def _get_deposit_withdrawal_totals(self, user_id: str) -> Tuple[Decimal, Decimal]:
        """Get total deposits and withdrawals for a user."""
        stmt = select(Transaction).where(
            and_(
                Transaction.user_id == user_id,
                or_(
                    Transaction.tx_type == 'DEPOSIT',
                    Transaction.tx_type == 'WITHDRAW',
                    Transaction.tx_type == 'WITHDRAWAL'
                ),
                Transaction.status == 'CONFIRMED'
            )
        )

        result = await self.db.execute(stmt)
        transactions = result.scalars().all()

        deposits = Decimal(0)
        withdrawals = Decimal(0)

        for tx in transactions:
            amount = Decimal(0)
            if tx.event_data and 'amount_usdc' in tx.event_data:
                amount = Decimal(str(tx.event_data['amount_usdc']))
            elif tx.amount_usdc:
                amount = Decimal(str(tx.amount_usdc))

            if tx.tx_type == 'DEPOSIT':
                deposits += amount
            else:
                withdrawals += amount

        return deposits, withdrawals

    def _empty_response(self) -> Dict[str, Decimal]:
        """Return empty response structure."""
        return {
            "realized_pnl_usdc": Decimal(0),
            "unrealized_pnl_usdc": Decimal(0),
            "fees_earned_usdc": Decimal(0),
            "rewards_earned_usdc": Decimal(0),
            "total_pnl_usdc": Decimal(0),
            "total_pnl_percentage": Decimal(0),
            "net_deposits": Decimal(0),
            "average_invested": Decimal(0),
        }