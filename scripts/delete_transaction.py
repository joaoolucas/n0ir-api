#!/usr/bin/env python3
"""Delete a specific transaction by ID."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

async def delete_transaction(tx_id: str):
    """Delete a transaction by ID."""
    # Direct database URL
    database_url = "postgresql+asyncpg://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

    # Create engine
    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        from app.database.models import Transaction

        stmt = delete(Transaction).where(Transaction.id == tx_id)
        result = await db.execute(stmt)
        await db.commit()
        print(f'Deleted {result.rowcount} transaction(s) with ID: {tx_id}')

    await engine.dispose()

if __name__ == "__main__":
    # Transaction ID to delete
    tx_id = "88bcf6c2-749e-485a-8ba3-443f725b4f99"
    asyncio.run(delete_transaction(tx_id))