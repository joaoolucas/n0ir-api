#!/usr/bin/env python3
"""
Link specific AERO_SWAP to POSITION_CLOSED transaction.
"""

import asyncio
import json
from decimal import Decimal
import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.database.models.transaction import Transaction
from app.core.logger import logger
from app.core.config import settings


async def get_async_session():
    """Create an async database session."""
    db_url = settings.get_database_url
    
    # Convert to asyncpg URL
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    
    engine = create_async_engine(db_url, echo=False)
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False
    )
    
    async with async_session_maker() as session:
        yield session
    
    await engine.dispose()


async def link_transactions(dry_run: bool = True):
    """Link the specific AERO_SWAP to POSITION_CLOSED."""
    
    async for session in get_async_session():
        position_id = "af1db10e-1bec-4c0f-b301-d35f490e096e"
        aero_swap_id = "0e319330-1471-4dea-b224-9d61063ec75c"
        
        # Get both transactions
        position_result = await session.execute(
            select(Transaction).where(Transaction.id == position_id)
        )
        position = position_result.scalar_one_or_none()
        
        swap_result = await session.execute(
            select(Transaction).where(Transaction.id == aero_swap_id)
        )
        swap = swap_result.scalar_one_or_none()
        
        if not position or not swap:
            logger.error("Could not find one or both transactions")
            return
        
        logger.info("Found transactions:")
        logger.info(f"  Position Close: {position_id}")
        logger.info(f"    User: {position.user_id}")
        logger.info(f"    Block: {position.block_number}")
        logger.info(f"    Amount: {position.event_data.get('amount_usdc', 0)}")
        
        logger.info(f"  AERO Swap: {aero_swap_id}")
        logger.info(f"    User: {swap.user_id}")
        logger.info(f"    Block: {swap.block_number}")
        logger.info(f"    Amount: {swap.event_data.get('amount_usdc', 0)}")
        
        if position.user_id != swap.user_id:
            logger.error("Users don't match!")
            return
        
        # Update the POSITION_CLOSED event_data to include AERO swap
        position_data = position.event_data
        if isinstance(position_data, str):
            position_data = json.loads(position_data)
        
        aero_amount = float(swap.event_data.get('amount_usdc', 0))
        position_data['aero_swap_usdc'] = aero_amount
        
        # Calculate total return
        usdc_out = float(position_data.get('amount_usdc', 0))
        total_return = usdc_out + aero_amount
        position_data['total_return_usdc'] = total_return
        
        # Since this doesn't have a token_id, we need to add one based on the transaction
        # Looking at the pattern, this appears to be a position that wasn't tracked
        # We'll leave tokenId empty for now since we can't determine it without chain data
        # position_data['tokenId'] = None  # Would need chain data to determine
        position_data['pool_name'] = 'Unknown'  # Can't determine without more data
        
        logger.info(f"\nWill update position close with:")
        logger.info(f"  AERO swap amount: {aero_amount}")
        logger.info(f"  Total return: {total_return}")
        
        if not dry_run:
            # Update position close
            await session.execute(
                update(Transaction)
                .where(Transaction.id == position_id)
                .values(event_data=position_data)
            )
            
            # Update AERO swap to link it
            swap_data = swap.event_data
            if isinstance(swap_data, str):
                swap_data = json.loads(swap_data)
            # Link by position transaction ID instead of token_id since we don't have it
            swap_data['linked_position_tx'] = position_id
            
            await session.execute(
                update(Transaction)
                .where(Transaction.id == aero_swap_id)
                .values(event_data=swap_data)
            )
            
            await session.commit()
            logger.info("✓ Successfully linked transactions!")
        else:
            logger.info("\nDRY RUN - No changes made. Run with --execute to apply.")


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Link specific AERO swap to position close')
    parser.add_argument('--execute', action='store_true', help='Actually apply the fixes (default is dry run)')
    
    args = parser.parse_args()
    
    await link_transactions(dry_run=not args.execute)


if __name__ == "__main__":
    asyncio.run(main())