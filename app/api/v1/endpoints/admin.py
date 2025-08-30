"""Admin endpoints for system maintenance."""

from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from typing import Optional

from app.db.connection import get_db
from app.core.config import settings
from loguru import logger

router = APIRouter()

async def verify_admin_token(authorization: Optional[str] = Header(None)) -> bool:
    """Verify admin authorization."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization required")
    
    # Check for Bearer token
    if authorization.startswith("Bearer "):
        token = authorization[7:]
        # Use the API_BEARER_TOKEN for admin access
        if token == settings.API_BEARER_TOKEN:
            return True
    
    raise HTTPException(status_code=403, detail="Invalid authorization")

@router.post("/fix-balance/{user_id}")
async def fix_user_balance(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin_token)
):
    """Recalculate user balance from transaction history."""
    
    # Get all confirmed transactions
    result = await db.execute(text("""
        SELECT tx_type, amount_usdc, created_at
        FROM transactions
        WHERE user_id = :user_id
        AND status = 'CONFIRMED'
        ORDER BY created_at ASC
    """), {"user_id": user_id})
    
    transactions = result.fetchall()
    
    balance = Decimal(0)
    deposits = Decimal(0)
    withdrawals = Decimal(0)
    positions_created = Decimal(0)
    positions_closed = Decimal(0)
    aero_swaps = Decimal(0)
    
    transaction_log = []
    
    for tx in transactions:
        tx_type = tx.tx_type
        amount = Decimal(str(tx.amount_usdc or 0))
        created_at = tx.created_at
        
        if tx_type == 'DEPOSIT':
            balance += amount
            deposits += amount
            transaction_log.append(f"{created_at}: DEPOSIT +${amount:.2f} → ${balance:.2f}")
            
        elif tx_type in ['WITHDRAWAL', 'WITHDRAW']:
            balance -= amount
            withdrawals += amount
            transaction_log.append(f"{created_at}: WITHDRAWAL -${amount:.2f} → ${balance:.2f}")
            
        elif tx_type == 'POSITION_CREATED':
            balance -= amount
            positions_created += amount
            transaction_log.append(f"{created_at}: POSITION_CREATED -${amount:.2f} → ${balance:.2f}")
            
        elif tx_type == 'POSITION_CLOSED':
            balance += amount
            positions_closed += amount
            transaction_log.append(f"{created_at}: POSITION_CLOSED +${amount:.2f} → ${balance:.2f}")
            
        elif tx_type == 'AERO_SWAP':
            balance += amount
            aero_swaps += amount
            transaction_log.append(f"{created_at}: AERO_SWAP +${amount:.2f} → ${balance:.2f}")
    
    # Ensure balance doesn't go negative
    balance = max(balance, Decimal(0))
    
    # Get current database values
    result = await db.execute(text("""
        SELECT usdc_balance, total_deposits_usdc, total_withdrawals_usdc
        FROM users
        WHERE user_id = :user_id
    """), {"user_id": user_id})
    
    user = result.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    old_balance = Decimal(str(user.usdc_balance))
    
    # Update the balance
    await db.execute(text("""
        UPDATE users
        SET usdc_balance = :balance
        WHERE user_id = :user_id
    """), {"balance": float(balance), "user_id": user_id})
    await db.commit()
    
    logger.info(f"Fixed balance for {user_id}: {old_balance:.6f} → {balance:.6f}")
    
    return {
        "user_id": user_id,
        "old_balance": float(old_balance),
        "new_balance": float(balance),
        "transaction_summary": {
            "deposits": float(deposits),
            "withdrawals": float(withdrawals),
            "positions_created": float(positions_created),
            "positions_closed": float(positions_closed),
            "aero_swaps": float(aero_swaps),
            "total_transactions": len(transactions)
        },
        "last_10_transactions": transaction_log[-10:] if transaction_log else []
    }

@router.post("/fix-all-balances")
async def fix_all_balances(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin_token)
):
    """Fix balances for all users."""
    
    # Get all users
    result = await db.execute(text("""
        SELECT user_id FROM users WHERE cdp_wallet_address IS NOT NULL
    """))
    
    users = result.fetchall()
    fixed_count = 0
    errors = []
    
    for user in users:
        user_id = user.user_id
        try:
            # Fix each user's balance
            await fix_user_balance(user_id, db, True)
            fixed_count += 1
        except Exception as e:
            errors.append({"user_id": user_id, "error": str(e)})
    
    return {
        "total_users": len(users),
        "fixed": fixed_count,
        "errors": errors
    }