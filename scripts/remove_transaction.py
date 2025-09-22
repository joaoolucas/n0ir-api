#!/usr/bin/env python3
"""
Remove a specific transaction from the database by ID
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, delete
from app.database.models import Transaction

DATABASE_URL = "postgresql+asyncpg://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def remove_transaction():
    """Remove the duplicate/incorrect withdrawal transaction"""

    transaction_id = "8daf4cf3-96b2-434b-9dac-83ff0ba621de"

    # Create database connection
    engine = create_async_engine(DATABASE_URL, echo=True)
    async_session = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with async_session() as db:
        try:
            # First, check if the transaction exists
            stmt = select(Transaction).where(Transaction.id == transaction_id)
            result = await db.execute(stmt)
            transaction = result.scalar_one_or_none()

            if not transaction:
                print(f"Transaction {transaction_id} not found in database")
                return

            # Show transaction details before deletion
            print(f"Found transaction to delete:")
            print(f"  ID: {transaction.id}")
            print(f"  User: {transaction.user_id}")
            print(f"  Type: {transaction.tx_type}")
            print(f"  Hash: {transaction.tx_hash}")
            print(f"  Status: {transaction.status}")
            print(f"  Created: {transaction.created_at}")

            # Delete the transaction
            delete_stmt = delete(Transaction).where(Transaction.id == transaction_id)
            await db.execute(delete_stmt)
            await db.commit()

            print(f"\n✅ Successfully deleted transaction {transaction_id}")

        except Exception as e:
            print(f"❌ Error removing transaction: {e}")
            await db.rollback()
            raise
        finally:
            await engine.dispose()

if __name__ == "__main__":
    asyncio.run(remove_transaction())