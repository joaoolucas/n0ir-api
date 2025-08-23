"""Admin endpoints for maintenance and recovery tasks."""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from decimal import Decimal
from datetime import datetime, timezone
from uuid import uuid4
from app.database.session import get_db
from app.database.models.user import User
from app.database.models.transaction import Transaction, TransactionType, TransactionStatus
from app.services.user_service import UserService
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
    EXPECTED_DEPOSIT = Decimal("15.0")
    POSITION_AMOUNT = EXPECTED_DEPOSIT - ACTUAL_WALLET_BALANCE  # 14.982299
    
    try:
        # Check if user exists
        user_stmt = select(User).where(User.user_id == user_id)
        result = await db.execute(user_stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")
        
        # Get current balance from UserService
        user_service = UserService(db)
        current_balance = await user_service.get_user_balance(user_id)
        logger.info(f"Current calculated balance: {current_balance} USDC")
        
        # Check if we already have a position entry transaction
        tx_stmt = select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.transaction_type == TransactionType.POSITION_ENTRY
        )
        result = await db.execute(tx_stmt)
        existing_tx = result.scalar_one_or_none()
        
        if not existing_tx:
            # Create missing POSITION_ENTRY transaction to correct the balance
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
            
            # Commit changes
            await db.commit()
            
            # Get new balance
            new_balance = await user_service.get_user_balance(user_id)
            
            return {
                "success": True,
                "message": "Balance fixed successfully",
                "old_balance": str(current_balance),
                "new_balance": str(new_balance),
                "position_entry_amount": str(POSITION_AMOUNT)
            }
        else:
            logger.info(f"POSITION_ENTRY transaction already exists: {existing_tx.amount_usdc} USDC")
            return {
                "success": False,
                "message": "POSITION_ENTRY transaction already exists",
                "existing_amount": str(existing_tx.amount_usdc)
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fixing balance: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-all-pnl")
async def sync_all_users_pnl(
    db: AsyncSession = Depends(get_db)
):
    """
    Sync PnL for all users to ensure calculations are correct.
    This recalculates unrealized and realized PnL with current blockchain values.
    """
    try:
        # Get all users
        result = await db.execute(select(User))
        users = result.scalars().all()
        
        logger.info(f"Starting PnL sync for {len(users)} users")
        
        # Create UserService instance
        service = UserService(db)
        
        results = []
        errors = []
        
        # Sync each user's PnL
        for user in users:
            try:
                # Recalculate PnL with fixed logic
                await service.recalculate_user_pnl(user.user_id)
                
                # Refresh user to get updated values
                await db.refresh(user)
                
                results.append({
                    "user_id": user.user_id,
                    "unrealized_pnl": float(user.unrealized_pnl_usdc),
                    "realized_pnl": float(user.realized_pnl_usdc),
                    "unrealized_pnl_percentage": float(user.unrealized_pnl_percentage),
                    "realized_pnl_percentage": float(user.realized_pnl_percentage)
                })
                
                logger.info(f"Synced PnL for user {user.user_id}")
                
            except Exception as e:
                logger.error(f"Error syncing PnL for user {user.user_id}: {e}")
                errors.append({
                    "user_id": user.user_id,
                    "error": str(e)
                })
        
        # Commit all changes
        await db.commit()
        
        return {
            "message": f"PnL sync completed for {len(results)} users",
            "synced_count": len(results),
            "error_count": len(errors),
            "results": results,
            "errors": errors,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in sync_all_pnl: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fix-position-status/{nft_token_id}")
async def fix_position_status(
    nft_token_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Fix position status mismatch between database and blockchain.
    Reopens a position that was marked closed in DB but is still open on-chain.
    """
    from app.database.models.position import Position, PositionStatus
    from app.core.positions_service import positions_service
    
    try:
        # Get position from database
        result = await db.execute(
            select(Position).where(Position.nft_token_id == nft_token_id)
        )
        position = result.scalar_one_or_none()
        
        if not position:
            raise HTTPException(status_code=404, detail=f"Position {nft_token_id} not found in database")
        
        # Check blockchain status
        try:
            position_info = await positions_service.get_position_by_id(nft_token_id)
            
            if position_info and position_info.current_value_usd:
                # Position exists on blockchain
                if position.status == PositionStatus.CLOSED:
                    # Reopen the position in database
                    position.status = PositionStatus.ACTIVE
                    position.exit_date = None
                    position.exit_tx_hash = None
                    position.realized_pnl_usdc = Decimal(0)
                    position.current_value_usdc = Decimal(str(position_info.current_value_usd or 0))
                    
                    # Also remove the POSITION_EXIT transaction if it exists
                    exit_tx = await db.execute(
                        select(Transaction).where(
                            and_(
                                Transaction.transaction_type == TransactionType.POSITION_EXIT,
                                Transaction.tx_metadata.like(f'%"nft_token_id": {nft_token_id}%')
                            )
                        ).order_by(Transaction.created_at.desc()).limit(1)
                    )
                    exit_transaction = exit_tx.scalar_one_or_none()
                    
                    if exit_transaction:
                        await db.delete(exit_transaction)
                        logger.info(f"Removed invalid POSITION_EXIT transaction for position {nft_token_id}")
                    
                    await db.commit()
                    
                    return {
                        "message": f"Position {nft_token_id} reopened successfully",
                        "status": "ACTIVE",
                        "current_value_usd": float(position_info.current_value_usd),
                        "exit_transaction_removed": exit_transaction is not None
                    }
                else:
                    return {
                        "message": f"Position {nft_token_id} is already active in database",
                        "status": position.status.value,
                        "current_value_usd": float(position_info.current_value_usd)
                    }
            else:
                # Position doesn't exist on blockchain
                if position.status == PositionStatus.ACTIVE:
                    # Mark as closed in database
                    position.status = PositionStatus.CLOSED
                    position.exit_date = position.exit_date or datetime.now(timezone.utc)
                    
                    await db.commit()
                    
                    return {
                        "message": f"Position {nft_token_id} marked as closed (not found on blockchain)",
                        "status": "CLOSED"
                    }
                else:
                    return {
                        "message": f"Position {nft_token_id} correctly marked as closed",
                        "status": position.status.value
                    }
                    
        except Exception as e:
            if "execution reverted: ID" in str(e) or "ContractLogicError" in str(e):
                # Position doesn't exist on blockchain
                if position.status == PositionStatus.ACTIVE:
                    position.status = PositionStatus.CLOSED
                    position.exit_date = position.exit_date or datetime.now(timezone.utc)
                    await db.commit()
                    
                    return {
                        "message": f"Position {nft_token_id} marked as closed (not found on blockchain)",
                        "status": "CLOSED"
                    }
                else:
                    return {
                        "message": f"Position {nft_token_id} is closed on blockchain and database",
                        "status": position.status.value
                    }
            else:
                raise e
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fixing position status: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-positions/{user_id}")
async def sync_user_positions(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Sync all positions for a user with blockchain state.
    Fixes any mismatches between database and blockchain.
    """
    from app.database.models.position import Position, PositionStatus
    from app.core.positions_service import positions_service
    
    try:
        # Get all positions from database
        result = await db.execute(
            select(Position).where(Position.user_id == user_id)
        )
        positions = result.scalars().all()
        
        fixed_positions = []
        errors = []
        
        for position in positions:
            try:
                # Check blockchain status
                position_info = await positions_service.get_position_by_id(position.nft_token_id)
                
                if position_info and position_info.current_value_usd:
                    # Position exists on blockchain
                    if position.status == PositionStatus.CLOSED:
                        # Reopen incorrectly closed position
                        position.status = PositionStatus.ACTIVE
                        position.exit_date = None
                        position.exit_tx_hash = None
                        position.realized_pnl_usdc = Decimal(0)
                        position.current_value_usdc = Decimal(str(position_info.current_value_usd or 0))
                        
                        fixed_positions.append({
                            "nft_token_id": position.nft_token_id,
                            "action": "reopened",
                            "value": float(position_info.current_value_usd)
                        })
                    else:
                        # Update current value
                        position.current_value_usdc = Decimal(str(position_info.current_value_usd or 0))
                        
                else:
                    # Position doesn't exist on blockchain
                    if position.status == PositionStatus.ACTIVE:
                        # Close incorrectly active position
                        position.status = PositionStatus.CLOSED
                        position.exit_date = position.exit_date or datetime.now(timezone.utc)
                        
                        fixed_positions.append({
                            "nft_token_id": position.nft_token_id,
                            "action": "closed",
                            "reason": "not found on blockchain"
                        })
                        
            except Exception as e:
                if "execution reverted: ID" in str(e) or "ContractLogicError" in str(e):
                    # Position doesn't exist on blockchain
                    if position.status == PositionStatus.ACTIVE:
                        position.status = PositionStatus.CLOSED
                        position.exit_date = position.exit_date or datetime.now(timezone.utc)
                        
                        fixed_positions.append({
                            "nft_token_id": position.nft_token_id,
                            "action": "closed",
                            "reason": "blockchain error"
                        })
                else:
                    errors.append({
                        "nft_token_id": position.nft_token_id,
                        "error": str(e)
                    })
        
        # Commit all changes
        await db.commit()
        
        # Recalculate user PnL after sync
        service = UserService(db)
        await service.recalculate_user_pnl(user_id)
        
        return {
            "message": f"Synced {len(positions)} positions for user {user_id}",
            "fixed_count": len(fixed_positions),
            "error_count": len(errors),
            "fixed_positions": fixed_positions,
            "errors": errors,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error syncing positions: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))