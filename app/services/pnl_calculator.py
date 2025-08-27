"""PnL calculation service for proper profit/loss tracking."""

from decimal import Decimal
from typing import Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.user import User
from app.database.models.transaction import Transaction
import logging

logger = logging.getLogger(__name__)

class PnLCalculator:
    """Service for calculating realized and unrealized PnL."""
    
    @staticmethod
    async def calculate_realized_pnl_on_withdrawal(
        db: AsyncSession,
        user_id: str,
        withdrawal_amount: Decimal
    ) -> Dict[str, Decimal]:
        """
        Calculate realized PnL when a withdrawal occurs.
        
        Realized PnL represents the actual profit or loss that has been "locked in"
        by withdrawing funds from the system.
        
        Formula:
        - If total_withdrawals > total_deposits:
          realized_pnl = total_withdrawals - total_deposits (profit realized)
        - Otherwise:
          realized_pnl = 0 (no profit realized yet)
        
        Args:
            db: Database session
            user_id: User ID
            withdrawal_amount: Amount being withdrawn
            
        Returns:
            Dict with realized_pnl_usd and realized_pnl_pct
        """
        # Get user record
        stmt = select(User).where(User.user_id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error(f"User {user_id} not found")
            return {"realized_pnl_usd": Decimal(0), "realized_pnl_pct": Decimal(0)}
        
        # Get current totals
        total_deposits = Decimal(str(user.total_deposits_usdc or 0))
        current_withdrawals = Decimal(str(user.total_withdrawals_usdc or 0))
        
        # Add the new withdrawal to get updated total
        total_withdrawals = current_withdrawals + withdrawal_amount
        
        # Calculate realized PnL
        # Only positive if withdrawals exceed deposits (taking out more than put in)
        if total_withdrawals > total_deposits:
            realized_pnl_usd = total_withdrawals - total_deposits
        else:
            # Haven't withdrawn enough to realize profit yet
            realized_pnl_usd = Decimal(0)
        
        # Calculate percentage based on deposits
        if total_deposits > 0:
            realized_pnl_pct = (realized_pnl_usd / total_deposits) * Decimal(100)
        else:
            realized_pnl_pct = Decimal(0)
        
        # Update user record
        user.realized_pnl_usd = realized_pnl_usd
        user.realized_pnl_pct = realized_pnl_pct
        user.total_withdrawals_usdc = total_withdrawals
        
        await db.commit()
        
        logger.info(
            f"Updated realized PnL for user {user_id} on withdrawal of {withdrawal_amount}: "
            f"realized_pnl=${realized_pnl_usd} ({realized_pnl_pct:.2f}%), "
            f"total_deposits=${total_deposits}, total_withdrawals=${total_withdrawals}"
        )
        
        return {
            "realized_pnl_usd": realized_pnl_usd,
            "realized_pnl_pct": realized_pnl_pct
        }
    
    @staticmethod
    async def reset_realized_pnl_if_no_withdrawals(
        db: AsyncSession,
        user_id: str
    ) -> None:
        """
        Reset realized PnL to 0 if user has no withdrawals.
        This ensures realized PnL is only set when actual withdrawals occur.
        """
        stmt = select(User).where(User.user_id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user:
            total_withdrawals = Decimal(str(user.total_withdrawals_usdc or 0))
            
            # If no withdrawals, realized PnL should be 0
            if total_withdrawals == 0:
                user.realized_pnl_usd = Decimal(0)
                user.realized_pnl_pct = Decimal(0)
                await db.commit()
                logger.info(f"Reset realized PnL to 0 for user {user_id} (no withdrawals)")
    
    @staticmethod
    def should_update_realized_pnl(tx_type: str) -> bool:
        """
        Determine if a transaction type should trigger realized PnL update.
        
        Only WITHDRAWAL transactions should update realized PnL.
        """
        return tx_type in ['WITHDRAWAL', 'WITHDRAW']