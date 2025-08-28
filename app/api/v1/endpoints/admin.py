"""Admin endpoints for balance adjustments and maintenance."""
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import uuid
from datetime import datetime

from app.database.session import get_db
from app.database.models import Transaction
from app.schemas.transaction import TransactionResponse
from sqlalchemy import select, and_

router = APIRouter()

class BalanceAdjustmentRequest(BaseModel):
    """Request to adjust user balance."""
    user_id: str
    amount_usdc: Decimal
    adjustment_type: str = "WITHDRAWAL"  # DEPOSIT to add, WITHDRAWAL to subtract
    reason: str
    note: Optional[str] = None


@router.post("/balance-adjustment", response_model=TransactionResponse)
async def create_balance_adjustment(
    request: BalanceAdjustmentRequest,
    db: AsyncSession = Depends(get_db)
):
    """Create a balance adjustment transaction.
    
    This is used to correct balance discrepancies caused by:
    - Historical calculation errors
    - Slippage not properly accounted for
    - Missing or incorrect transactions
    """
    
    # Validate adjustment type
    if request.adjustment_type not in ["DEPOSIT", "WITHDRAWAL"]:
        raise HTTPException(status_code=400, detail="adjustment_type must be DEPOSIT or WITHDRAWAL")
    
    # Create adjustment transaction
    tx_id = str(uuid.uuid4())
    tx_hash = f"adjustment-{tx_id[:8]}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    
    transaction = Transaction(
        id=tx_id,
        user_id=request.user_id,
        tx_type=request.adjustment_type,
        status='CONFIRMED',
        event_data={
            'amount_usdc': float(request.amount_usdc),
            'type': 'balance_adjustment',
            'reason': request.reason,
            'note': request.note or '',
            'adjusted_at': datetime.utcnow().isoformat()
        },
        tx_hash=tx_hash,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        tx_metadata={
            'adjustment': True,
            'manual': True,
            'reason': request.reason
        }
    )
    
    db.add(transaction)
    await db.commit()
    await db.refresh(transaction)
    
    return TransactionResponse.model_validate(transaction)


@router.get("/verify-balance/{user_id}")
async def verify_balance(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Verify user balance calculation with detailed breakdown."""
    
    # Get all confirmed transactions
    stmt = select(Transaction).where(
        and_(
            Transaction.user_id == user_id,
            Transaction.status == 'CONFIRMED'
        )
    ).order_by(Transaction.created_at)
    
    result = await db.execute(stmt)
    transactions = result.scalars().all()
    
    deposits = Decimal(0)
    withdrawals = Decimal(0)
    position_created = Decimal(0)
    position_closed = Decimal(0)
    aero_swaps = Decimal(0)
    adjustments = Decimal(0)
    
    for tx in transactions:
        amount = Decimal(0)
        if tx.event_data and 'amount_usdc' in tx.event_data:
            try:
                amount = Decimal(str(tx.event_data['amount_usdc']))
            except:
                amount = Decimal(0)
        
        # Check if this is an adjustment
        is_adjustment = (
            tx.tx_metadata and 
            tx.tx_metadata.get('adjustment') == True
        )
        
        if tx.tx_type == 'DEPOSIT':
            if is_adjustment:
                adjustments += amount
            else:
                deposits += amount
        elif tx.tx_type in ['WITHDRAWAL', 'WITHDRAW']:
            if is_adjustment:
                adjustments -= amount
            else:
                withdrawals += amount
        elif tx.tx_type == 'POSITION_CREATED':
            # Account for USDC returns
            usdc_returned = Decimal(0)
            if tx.event_data and 'usdc_returned' in tx.event_data:
                try:
                    usdc_returned = Decimal(str(tx.event_data['usdc_returned']))
                except:
                    usdc_returned = Decimal(0)
            position_created += (amount - usdc_returned)
        elif tx.tx_type == 'POSITION_CLOSED':
            position_closed += amount
        elif tx.tx_type == 'AERO_SWAP':
            aero_swaps += amount
    
    # Calculate balance
    balance = deposits + position_closed + aero_swaps - withdrawals - position_created + adjustments
    
    return {
        "user_id": user_id,
        "calculated_balance": float(balance),
        "breakdown": {
            "deposits": float(deposits),
            "withdrawals": float(withdrawals),
            "position_created_net": float(position_created),
            "position_closed": float(position_closed),
            "aero_swaps": float(aero_swaps),
            "adjustments": float(adjustments)
        },
        "transaction_count": len(transactions)
    }