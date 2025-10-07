#!/usr/bin/env python3
"""Update pool_name for existing position transactions by directly using pools service."""

import asyncio
import sys
import os
import json

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.database.models import Transaction, Position
from app.core.pools_service import pools_service

DATABASE_URL = "postgresql+asyncpg://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def update_transaction_pool_names():
    """Update pool_name for existing transactions using pools service."""
    # Create async engine
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        try:
            # Find all position-related transactions
            stmt = select(Transaction).where(
                Transaction.tx_type.in_(['POSITION_CREATED', 'POSITION_CLOSED', 'STAKING'])
            )
            result = await session.execute(stmt)
            transactions = result.scalars().all()

            print(f"Found {len(transactions)} position-related transactions")

            updated_count = 0
            for tx in transactions:
                # Skip if already has pool_name
                if tx.event_data.get('pool_name'):
                    continue

                # Get pool address from event_data or position
                pool_address = tx.event_data.get('pool')

                # If POSITION_CLOSED and no pool address, look it up from position
                if not pool_address and tx.tx_type == 'POSITION_CLOSED' and tx.position_id:
                    stmt = select(Position).where(Position.token_id == tx.position_id)
                    result = await session.execute(stmt)
                    position = result.scalar_one_or_none()
                    if position:
                        pool_address = position.pool_address

                if pool_address:
                    try:
                        # Fetch pool data using pools_service
                        pool_data = await pools_service.get_pool(pool_address, include_effective_apr=False)

                        if pool_data and 'symbol' in pool_data:
                            symbol = pool_data['symbol']
                            # Symbol format is "TOKEN0/TOKEN1-0.3%"
                            # We want to keep "TOKEN0/TOKEN1" format
                            if symbol and '-' in symbol:
                                # Remove fee percentage (everything after last dash)
                                pool_name = symbol.rsplit('-', 1)[0]  # Gets "TOKEN0/TOKEN1"
                            else:
                                pool_name = symbol

                            if pool_name:
                                # Update event_data with pool_name
                                tx.event_data = tx.event_data or {}
                                tx.event_data['pool_name'] = pool_name
                                if not tx.event_data.get('pool'):
                                    tx.event_data['pool'] = pool_address

                                updated_count += 1
                                print(f"✅ Updated {tx.tx_type} transaction {tx.tx_hash[:10]}... with pool_name={pool_name}")
                    except Exception as e:
                        print(f"⚠️  Could not fetch pool data for {pool_address}: {e}")

            # Commit all updates
            if updated_count > 0:
                await session.commit()
                print(f"\n✅ Updated {updated_count} transactions with pool_name")
            else:
                print("\n✅ No transactions needed updating")

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await engine.dispose()

if __name__ == "__main__":
    asyncio.run(update_transaction_pool_names())