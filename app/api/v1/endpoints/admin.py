"""Admin endpoints for system maintenance."""

from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.database.session import get_db
from app.core.config import settings
from loguru import logger

router = APIRouter()

@router.post("/update-usdc-returned")
async def update_usdc_returned(
    db: AsyncSession = Depends(get_db)
):
    """Update POSITION_CREATED transactions with usdc_returned field."""
    from app.database.models import Transaction
    from sqlalchemy import select, update
    from decimal import Decimal
    
    # Find the specific transaction
    tx_hash = "0x39f2fa2ede784c9e1be75df47f67742c7bac830ba0afeaa8662c839fd8801c14"
    
    result = await db.execute(
        select(Transaction).where(Transaction.tx_hash == tx_hash)
    )
    tx = result.scalar_one_or_none()
    
    if tx:
        # Update the event_data to include usdc_returned
        if not tx.event_data:
            tx.event_data = {}
        
        # Add the usdc_returned field
        tx.event_data['usdc_returned'] = "0.010091"
        
        # Also ensure amount_usdc is present
        if 'amount_usdc' not in tx.event_data:
            tx.event_data['amount_usdc'] = tx.event_data.get('usdc_in', '49.99')
        
        # Mark the field as modified to ensure SQLAlchemy updates it
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(tx, "event_data")
        
        await db.commit()
        
        return {"status": "success", "message": f"Updated transaction {tx_hash[:10]}... with usdc_returned=0.010091", "event_data": tx.event_data}
    else:
        return {"status": "error", "message": f"Transaction {tx_hash} not found"}

@router.post("/fix-balance/{user_id}")
async def fix_user_balance(
    user_id: str,
    db: AsyncSession = Depends(get_db)
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
    db: AsyncSession = Depends(get_db)
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
            await fix_user_balance(user_id, db)
            fixed_count += 1
        except Exception as e:
            errors.append({"user_id": user_id, "error": str(e)})
    
    return {
        "total_users": len(users),
        "fixed": fixed_count,
        "errors": errors
    }

@router.post("/fix-position-tokens")
async def fix_position_tokens(
    db: AsyncSession = Depends(get_db)
):
    """Fix positions with missing token addresses by fetching from blockchain."""
    from app.core.positions_service import positions_service
    from app.database.models import Position
    
    # Get all positions with missing token addresses
    result = await db.execute(text("""
        SELECT token_id, user_id, pool_address
        FROM positions
        WHERE (token0_address IS NULL OR token0_address = '' 
               OR token1_address IS NULL OR token1_address = '')
        AND status = 'ACTIVE'
    """))
    
    positions = result.fetchall()
    fixed_count = 0
    errors = []
    
    logger.info(f"Found {len(positions)} positions with missing token addresses")
    
    for position in positions:
        token_id = position.token_id
        try:
            # Fetch position details from blockchain
            position_info = await positions_service.get_position_by_id(token_id)
            
            # Update the position with token addresses
            if position_info.token0 and position_info.token1:
                await db.execute(text("""
                    UPDATE positions
                    SET token0_address = :token0,
                        token1_address = :token1,
                        tick_spacing = :tick_spacing
                    WHERE token_id = :token_id
                """), {
                    "token0": position_info.token0.lower(),
                    "token1": position_info.token1.lower(),
                    "tick_spacing": position_info.tick_spacing or 100,
                    "token_id": token_id
                })
                fixed_count += 1
                logger.info(f"Fixed position {token_id} with tokens {position_info.token0[:10]}.../{position_info.token1[:10]}...")
            else:
                errors.append({
                    "token_id": token_id,
                    "error": "No token addresses returned from blockchain"
                })
        except Exception as e:
            errors.append({
                "token_id": token_id,
                "error": str(e)
            })
            logger.error(f"Failed to fix position {token_id}: {e}")
    
    await db.commit()
    
    return {
        "total_positions": len(positions),
        "fixed": fixed_count,
        "errors": errors
    }

@router.post("/fix-position/{token_id}")
async def fix_single_position(
    token_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Fix a single position's token addresses by fetching from blockchain."""
    from app.core.positions_service import positions_service
    from app.database.models import Position
    
    # Check if position exists
    result = await db.execute(select(Position).where(Position.token_id == token_id))
    position = result.scalar_one_or_none()
    
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    
    try:
        # Fetch position details from blockchain
        position_info = await positions_service.get_position_by_id(token_id)
        
        old_token0 = position.token0_address
        old_token1 = position.token1_address
        
        # Update the position with all available data
        if position_info.token0 and position_info.token1:
            position.token0_address = position_info.token0.lower()
            position.token1_address = position_info.token1.lower()
            position.tick_spacing = position_info.tick_spacing or 100
            position.tick_lower = position_info.tick_lower
            position.tick_upper = position_info.tick_upper
            position.staked = position_info.staked
            position.gauge_address = position_info.gauge_address or ''
            
            # Update position data JSON
            if not position.position_data:
                position.position_data = {}
            
            position.position_data['in_range'] = position_info.in_range
            position.position_data['current_tick'] = position_info.current_tick
            
            await db.commit()
            
            logger.info(f"Fixed position {token_id}: tokens {old_token0} -> {position_info.token0}, {old_token1} -> {position_info.token1}")
            
            return {
                "token_id": token_id,
                "old_token0": old_token0,
                "old_token1": old_token1,
                "new_token0": position_info.token0,
                "new_token1": position_info.token1,
                "tick_spacing": position_info.tick_spacing,
                "staked": position_info.staked,
                "in_range": position_info.in_range
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"No token addresses returned from blockchain for position {token_id}"
            )
            
    except Exception as e:
        logger.error(f"Failed to fix position {token_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fix position: {str(e)}"
        )