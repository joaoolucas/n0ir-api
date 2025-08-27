"""Admin endpoints for maintenance and recovery tasks."""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from decimal import Decimal
from datetime import datetime, timezone
from uuid import uuid4
from app.database.session import get_db
from app.database.models.user import User
from app.database.models.transaction import Transaction
from app.schemas.users import TransactionType, TransactionStatus
from app.services.user_service import UserService
from app.core.logger import logger

router = APIRouter()

@router.post("/fix-balance/{user_id}")
async def fix_user_balance(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Fix balance discrepancy by creating proper transaction records.
    Creates both DEPOSIT and POSITION_ENTRY transactions to reflect user's actual state.
    """
    # Calculate position amount from user's actual positions
    from app.database.models.position import Position
    
    positions_stmt = select(Position).where(
        Position.user_id == user_id,
        Position.status == 'ACTIVE'
    )
    positions_result = await db.execute(positions_stmt)
    positions = positions_result.scalars().all()
    
    if not positions:
        raise HTTPException(status_code=404, detail=f"No active positions found for user {user_id}")
    
    POSITION_AMOUNT = sum(p.entry_amount_usdc for p in positions)
    
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
        
        # Check if we already have deposit and position entry transactions
        deposit_stmt = select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.tx_type == 'DEPOSIT'
        )
        deposit_result = await db.execute(deposit_stmt)
        existing_deposit = deposit_result.scalar_one_or_none()
        
        position_stmt = select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.tx_type == 'POSITION_CREATED'
        )
        position_result = await db.execute(position_stmt)
        existing_position_tx = position_result.scalar_one_or_none()
        
        transactions_created = []
        
        if not existing_deposit:
            # Create DEPOSIT transaction (money coming in)
            deposit_tx = Transaction(
                id=uuid4(),
                user_id=user_id,
                tx_type='DEPOSIT',  # Credits user's balance
                status='CONFIRMED',
                event_data={'amount_usdc': float(POSITION_AMOUNT)},
                tx_metadata={
                    'action': 'retroactive_deposit',
                    'reason': 'Position synced from blockchain without corresponding deposit record'
                },
                created_at=datetime.now(timezone.utc),
                processed_at=datetime.now(timezone.utc)
            )
            db.add(deposit_tx)
            transactions_created.append(f"DEPOSIT: {POSITION_AMOUNT} USDC")
            logger.info(f"Created DEPOSIT transaction for {POSITION_AMOUNT} USDC")
        
        if not existing_position_tx and positions:
            # Create POSITION_ENTRY transaction for the actual position (money going out to position)
            main_position = positions[0]  # Use the first/main position
            position_entry_tx = Transaction(
                id=uuid4(),
                user_id=user_id,
                tx_type='POSITION_CREATED',  # Debits user's balance, creates position
                status='CONFIRMED',
                event_data={'amount_usdc': float(main_position.entry_amount_usdc)},
                tx_metadata={
                    'action': 'retroactive_position_entry',
                    'nft_token_id': main_position.nft_token_id,
                    'pool_address': main_position.pool_address,
                    'reason': 'Position synced from blockchain without corresponding entry record'
                },
                created_at=datetime.now(timezone.utc),
                processed_at=datetime.now(timezone.utc),
                position_id=main_position.nft_token_id
            )
            db.add(position_entry_tx)
            transactions_created.append(f"POSITION_ENTRY: {main_position.entry_amount_usdc} USDC for position {main_position.nft_token_id}")
            logger.info(f"Created POSITION_ENTRY transaction for position {main_position.nft_token_id}")
            
        if transactions_created:
            
            # Commit changes
            await db.commit()
            
            # Get new balance
            new_balance = await user_service.get_user_balance(user_id)
            
            return {
                "success": True,
                "message": "Balance and transactions fixed successfully",
                "old_balance": str(current_balance),
                "new_balance": str(new_balance),
                "transactions_created": transactions_created,
                "total_position_amount": str(POSITION_AMOUNT)
            }
        else:
            logger.info("All required transactions already exist")
            return {
                "success": False,
                "message": "All required transactions already exist",
                "current_balance": str(current_balance),
                "deposit_exists": existing_deposit is not None,
                "position_tx_exists": existing_position_tx is not None
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
    from app.database.models.position import Position
    from app.schemas.users import PositionStatus
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
                    position.status = 'ACTIVE'
                    position.exit_date = None
                    position.exit_tx_hash = None
                    position.realized_pnl_usd = Decimal(0)
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
                if position.status == 'ACTIVE':
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
                if position.status == 'ACTIVE':
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
    from app.database.models.position import Position
    from app.schemas.users import PositionStatus
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
                        position.status = 'ACTIVE'
                        position.exit_date = None
                        position.exit_tx_hash = None
                        position.realized_pnl_usd = Decimal(0)
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
                    if position.status == 'ACTIVE':
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
                    if position.status == 'ACTIVE':
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