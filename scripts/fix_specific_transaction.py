#!/usr/bin/env python3
"""
Fix specific wrongly categorized transaction and improve categorization logic.

The transaction af1db10e-1bec-4c0f-b301-d35f490e096e should be POSITION_CLOSED, not AERO_SWAP.
It's a USDC transfer TO the user's agent wallet after closing a position.
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


async def fix_transaction(dry_run: bool = True):
    """Fix the specific wrongly categorized transaction."""
    
    async for session in get_async_session():
        # Fix the specific transaction
        tx_id = "af1db10e-1bec-4c0f-b301-d35f490e096e"
        
        result = await session.execute(
            select(Transaction).where(Transaction.id == tx_id)
        )
        tx = result.scalar_one_or_none()
        
        if not tx:
            logger.error(f"Transaction {tx_id} not found")
            return
        
        logger.info(f"Found transaction {tx_id}:")
        logger.info(f"  Current type: {tx.tx_type}")
        logger.info(f"  User: {tx.user_id}")
        logger.info(f"  Amount: {tx.event_data.get('amount_usdc', 0)}")
        logger.info(f"  Block: {tx.block_number}")
        
        if not dry_run:
            # Update to POSITION_CLOSED
            await session.execute(
                update(Transaction)
                .where(Transaction.id == tx_id)
                .values(tx_type='POSITION_CLOSED')
            )
            
            await session.commit()
            logger.info(f"✓ Updated transaction {tx_id} to POSITION_CLOSED")
        else:
            logger.info("\nDRY RUN - Would update transaction to POSITION_CLOSED")
        
        # Now check for other similar cases
        logger.info("\nChecking for other similar misclassified transactions...")
        
        # Find all AERO_SWAP transactions that might be misclassified
        result = await session.execute(
            select(Transaction).where(
                Transaction.tx_type == 'AERO_SWAP'
            )
        )
        
        aero_swaps = result.scalars().all()
        potential_fixes = []
        
        for swap in aero_swaps:
            event_data = swap.event_data
            if isinstance(event_data, str):
                event_data = json.loads(event_data)
            
            # Check if this looks like a position close rather than AERO swap
            # AERO swaps should have position_token_id or be small amounts
            # Position closes are larger USDC transfers without token_id references
            
            amount = float(event_data.get('amount_usdc', 0))
            has_position_ref = 'position_token_id' in event_data
            from_address = event_data.get('from_address', '').lower()
            
            # If it's a large USDC transfer (>50 USDC) without position reference,
            # it's likely a position close, not an AERO swap
            if amount > 50 and not has_position_ref and from_address == "0x00c1bc0ca9f703919c2ba320e5f200865f778aae":
                potential_fixes.append({
                    'id': swap.id,
                    'amount': amount,
                    'user_id': swap.user_id,
                    'block': swap.block_number
                })
        
        if potential_fixes:
            logger.info(f"\nFound {len(potential_fixes)} potentially misclassified AERO_SWAP transactions:")
            for fix in potential_fixes:
                logger.info(f"  {fix['id']}: ${fix['amount']:.2f} for user {fix['user_id']}")
            
            if not dry_run:
                logger.info("\nFixing these transactions...")
                for fix in potential_fixes:
                    await session.execute(
                        update(Transaction)
                        .where(Transaction.id == fix['id'])
                        .values(tx_type='POSITION_CLOSED')
                    )
                    logger.info(f"✓ Updated {fix['id']} to POSITION_CLOSED")
                
                await session.commit()
                logger.info("All fixes applied!")
            else:
                logger.info("\nDRY RUN - Would update these transactions to POSITION_CLOSED")
        else:
            logger.info("No other misclassified transactions found.")


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Fix specific wrongly categorized transaction')
    parser.add_argument('--execute', action='store_true', help='Actually apply the fixes (default is dry run)')
    
    args = parser.parse_args()
    
    await fix_transaction(dry_run=not args.execute)


if __name__ == "__main__":
    asyncio.run(main())