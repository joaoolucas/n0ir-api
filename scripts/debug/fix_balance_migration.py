#!/usr/bin/env python3
"""
One-time script to fix balance discrepancy for user 0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51
- Adjusts balance from 15 USDC to 0.017701 USDC (actual wallet balance)
- Creates missing POSITION_ENTRY transaction for the difference
"""

import asyncio
import os
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update
from uuid import uuid4

# Import models
from app.database.models.user import User
from app.database.models.transaction import Transaction, TransactionType, TransactionStatus

USER_ID = "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51"
ACTUAL_WALLET_BALANCE = Decimal("0.017701")
CURRENT_DB_BALANCE = Decimal("15.0")
POSITION_AMOUNT = CURRENT_DB_BALANCE - ACTUAL_WALLET_BALANCE  # 14.982299

async def fix_balance():
    """Fix the balance discrepancy."""
    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")
    
    # Convert to async URL if needed
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    
    # Create async engine
    engine = create_async_engine(database_url, echo=True)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with AsyncSessionLocal() as session:
        try:
            # Check current user balance
            user_stmt = select(User).where(User.user_id == USER_ID)
            result = await session.execute(user_stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                print(f"User {USER_ID} not found")
                return
            
            print(f"Current database balance: {user.balance_usdc} USDC")
            print(f"Actual wallet balance: {ACTUAL_WALLET_BALANCE} USDC")
            print(f"Position amount to record: {POSITION_AMOUNT} USDC")
            
            # Update user balance to match actual wallet
            update_stmt = (
                update(User)
                .where(User.user_id == USER_ID)
                .values(balance_usdc=ACTUAL_WALLET_BALANCE)
            )
            await session.execute(update_stmt)
            print(f"Updated balance to {ACTUAL_WALLET_BALANCE} USDC")
            
            # Check if we already have a position entry transaction
            tx_stmt = select(Transaction).where(
                Transaction.user_id == USER_ID,
                Transaction.transaction_type == TransactionType.POSITION_ENTRY
            )
            result = await session.execute(tx_stmt)
            existing_tx = result.scalar_one_or_none()
            
            if not existing_tx:
                # Create missing POSITION_ENTRY transaction
                position_tx = Transaction(
                    transaction_id=uuid4(),
                    user_id=USER_ID,
                    transaction_type=TransactionType.POSITION_ENTRY,
                    amount_usdc=POSITION_AMOUNT,
                    status=TransactionStatus.CONFIRMED,
                    created_at=datetime.now(timezone.utc),
                    confirmed_at=datetime.now(timezone.utc),
                    tx_metadata="Retroactive transaction for existing position"
                )
                session.add(position_tx)
                print(f"Created POSITION_ENTRY transaction for {POSITION_AMOUNT} USDC")
            else:
                print(f"POSITION_ENTRY transaction already exists: {existing_tx.amount_usdc} USDC")
            
            # Commit changes
            await session.commit()
            print("Balance fix completed successfully!")
            
        except Exception as e:
            print(f"Error fixing balance: {e}")
            await session.rollback()
            raise
        finally:
            await engine.dispose()

if __name__ == "__main__":
    asyncio.run(fix_balance())