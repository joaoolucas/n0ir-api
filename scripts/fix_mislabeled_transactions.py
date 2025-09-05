#!/usr/bin/env python3
"""
Fix mislabeled transactions - some USDC transfers are incorrectly marked as POSITION_CLOSED.

These should be DEPOSIT or AERO_SWAP transactions.
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

# Known AERO swap router
AERO_SWAP_ROUTER = "0x00c1bc0ca9f703919c2ba320e5f200865f778aae"


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


async def fix_mislabeled_transactions(dry_run: bool = True):
    """Fix transactions that are mislabeled as POSITION_CLOSED when they're actually transfers."""
    
    async for session in get_async_session():
        # Find POSITION_CLOSED transactions that don't have tokenId in event_data
        result = await session.execute(
            select(Transaction).where(
                Transaction.tx_type == 'POSITION_CLOSED'
            )
        )
        
        transactions = result.scalars().all()
        fixes_needed = []
        
        logger.info(f"Checking {len(transactions)} POSITION_CLOSED transactions")
        
        for tx in transactions:
            event_data = tx.event_data
            if isinstance(event_data, str):
                event_data = json.loads(event_data)
            
            # Check if this has the structure of a real POSITION_CLOSED
            has_token_id = 'tokenId' in event_data or 'token_id' in event_data
            has_usdc_out = 'usdcOut' in event_data or 'usdc_out' in event_data
            
            # If it doesn't have token_id but has token/to_address/from_address, it's a transfer
            if not has_token_id and not has_usdc_out:
                if 'token' in event_data and 'from_address' in event_data:
                    from_address = event_data.get('from_address', '').lower()
                    
                    # Determine correct type
                    if from_address == AERO_SWAP_ROUTER.lower():
                        new_type = 'AERO_SWAP'
                    else:
                        new_type = 'DEPOSIT'
                    
                    fixes_needed.append({
                        'id': tx.id,
                        'old_type': tx.tx_type,
                        'new_type': new_type,
                        'user_id': tx.user_id,
                        'amount': event_data.get('amount_usdc', 0),
                        'from': from_address,
                        'block': tx.block_number
                    })
        
        if fixes_needed:
            logger.info(f"\nFound {len(fixes_needed)} mislabeled transactions:")
            for fix in fixes_needed:
                logger.info(f"  {fix['id']}: {fix['old_type']} -> {fix['new_type']} (${fix['amount']} from {fix['from'][:10]}...)")
            
            if not dry_run:
                logger.info("\nApplying fixes...")
                for fix in fixes_needed:
                    await session.execute(
                        update(Transaction)
                        .where(Transaction.id == fix['id'])
                        .values(tx_type=fix['new_type'])
                    )
                    logger.info(f"Updated {fix['id']} to {fix['new_type']}")
                
                await session.commit()
                logger.info("All fixes applied!")
            else:
                logger.info("\nDRY RUN - No changes made. Run with --execute to apply fixes.")
        else:
            logger.info("No mislabeled transactions found.")


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Fix mislabeled transactions')
    parser.add_argument('--execute', action='store_true', help='Actually apply the fixes (default is dry run)')
    
    args = parser.parse_args()
    
    await fix_mislabeled_transactions(dry_run=not args.execute)


if __name__ == "__main__":
    asyncio.run(main())