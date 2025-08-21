"""Admin endpoints for maintenance tasks."""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from decimal import Decimal
from datetime import datetime, timezone
from uuid import uuid4
from app.database.session import get_db
from app.database.models.user import User
from app.database.models.transaction import Transaction, TransactionType, TransactionStatus
from app.core.logger import logger

router = APIRouter()

@router.post("/fix-balance/{user_id}")
async def fix_user_balance(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    One-time endpoint to fix balance discrepancy.
    This will be removed after fixing the production data.
    """
    # Only allow for specific user during migration
    if user_id != "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51":
        raise HTTPException(status_code=403, detail="Not authorized")
    
    ACTUAL_WALLET_BALANCE = Decimal("0.017701")
    CURRENT_DB_BALANCE = Decimal("15.0")
    POSITION_AMOUNT = CURRENT_DB_BALANCE - ACTUAL_WALLET_BALANCE
    
    try:
        # Check current user balance
        user_stmt = select(User).where(User.user_id == user_id)
        result = await db.execute(user_stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")
        
        logger.info(f"Current database balance: {user.balance_usdc} USDC")
        
        # Update user balance to match actual wallet
        update_stmt = (
            update(User)
            .where(User.user_id == user_id)
            .values(balance_usdc=ACTUAL_WALLET_BALANCE)
        )
        await db.execute(update_stmt)
        logger.info(f"Updated balance to {ACTUAL_WALLET_BALANCE} USDC")
        
        # Check if we already have a position entry transaction
        tx_stmt = select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.transaction_type == TransactionType.POSITION_ENTRY
        )
        result = await db.execute(tx_stmt)
        existing_tx = result.scalar_one_or_none()
        
        if not existing_tx:
            # Create missing POSITION_ENTRY transaction
            position_tx = Transaction(
                transaction_id=uuid4(),
                user_id=user_id,
                transaction_type=TransactionType.POSITION_ENTRY,
                amount_usdc=POSITION_AMOUNT,
                status=TransactionStatus.CONFIRMED,
                created_at=datetime.now(timezone.utc),
                confirmed_at=datetime.now(timezone.utc),
                tx_metadata="Retroactive transaction for existing position"
            )
            db.add(position_tx)
            logger.info(f"Created POSITION_ENTRY transaction for {POSITION_AMOUNT} USDC")
        else:
            logger.info(f"POSITION_ENTRY transaction already exists: {existing_tx.amount_usdc} USDC")
        
        # Commit changes
        await db.commit()
        
        return {
            "success": True,
            "message": "Balance fixed successfully",
            "old_balance": str(CURRENT_DB_BALANCE),
            "new_balance": str(ACTUAL_WALLET_BALANCE),
            "position_amount": str(POSITION_AMOUNT)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fixing balance: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))