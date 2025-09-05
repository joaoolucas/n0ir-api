#!/usr/bin/env python3
"""
Link AERO_SWAP transactions to POSITION_CLOSED by proximity.

When a position is closed and AERO rewards are swapped, the AERO_SWAP 
typically happens within a few blocks of the position close.
"""

import asyncio
import json
from decimal import Decimal
from typing import Optional, Dict, List
import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, and_, update, or_
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


async def link_aero_swaps(dry_run: bool = True):
    """Link AERO_SWAP transactions to nearby POSITION_CLOSED transactions."""
    
    async for session in get_async_session():
        # Find all POSITION_CLOSED transactions with 0 or missing AERO swaps
        result = await session.execute(
            select(Transaction).where(
                Transaction.tx_type == 'POSITION_CLOSED'
            ).order_by(Transaction.block_timestamp.desc())
        )
        
        position_closes = result.scalars().all()
        
        logger.info(f"Checking {len(position_closes)} POSITION_CLOSED transactions")
        
        fixes_needed = []
        
        for position in position_closes:
            event_data = position.event_data
            if isinstance(event_data, str):
                event_data = json.loads(event_data)
            
            # Check if already has AERO swap
            aero_amount = float(event_data.get('aero_swap_usdc', 0))
            if aero_amount > 0:
                continue
            
            token_id = event_data.get('tokenId') or event_data.get('token_id')
            if not token_id:
                continue
            
            # Look for AERO_SWAP transactions for the same user within 50 blocks
            swaps_result = await session.execute(
                select(Transaction).where(
                    and_(
                        Transaction.user_id == position.user_id,
                        Transaction.tx_type == 'AERO_SWAP',
                        Transaction.block_number >= position.block_number,
                        Transaction.block_number <= position.block_number + 50
                    )
                ).order_by(Transaction.block_number.asc())
            )
            
            aero_swaps = swaps_result.scalars().all()
            
            # Find the closest unlinked AERO_SWAP
            best_match = None
            best_distance = float('inf')
            
            for swap in aero_swaps:
                swap_data = swap.event_data
                if isinstance(swap_data, str):
                    swap_data = json.loads(swap_data)
                
                # Check if this swap is already linked to another position
                linked_token = swap_data.get('position_token_id')
                if linked_token and linked_token != token_id:
                    continue
                
                # Calculate distance in blocks
                distance = abs(swap.block_number - position.block_number)
                
                # Prefer swaps that happen after the position close
                if swap.block_number >= position.block_number and distance < best_distance:
                    best_match = swap
                    best_distance = distance
            
            if best_match:
                swap_data = best_match.event_data
                if isinstance(swap_data, str):
                    swap_data = json.loads(swap_data)
                
                amount = float(swap_data.get('amount_usdc', 0))
                
                fixes_needed.append({
                    'position_id': position.id,
                    'token_id': token_id,
                    'aero_swap_id': best_match.id,
                    'aero_swap_amount': amount,
                    'aero_swap_tx': best_match.tx_hash,
                    'position_block': position.block_number,
                    'swap_block': best_match.block_number,
                    'blocks_apart': best_distance,
                    'position_event_data': event_data,
                    'swap_event_data': swap_data
                })
                
                logger.info(f"Matched position {token_id} (block {position.block_number}) with AERO swap (block {best_match.block_number}, {best_distance} blocks apart): {amount} USDC")
        
        if fixes_needed:
            logger.info(f"\nFound {len(fixes_needed)} positions to link with AERO swaps:")
            
            for fix in fixes_needed:
                logger.info(f"  Token {fix['token_id']}: {fix['aero_swap_amount']} USDC ({fix['blocks_apart']} blocks apart)")
            
            if not dry_run:
                logger.info("\nApplying fixes...")
                
                for fix in fixes_needed:
                    # Update position event_data
                    position_data = fix['position_event_data']
                    position_data['aero_swap_usdc'] = fix['aero_swap_amount']
                    
                    # Recalculate total_return_usdc
                    usdc_out = float(position_data.get('amount_usdc', 0))
                    total_return = usdc_out + fix['aero_swap_amount']
                    position_data['total_return_usdc'] = total_return
                    
                    # Update the position transaction
                    await session.execute(
                        update(Transaction)
                        .where(Transaction.id == fix['position_id'])
                        .values(event_data=position_data)
                    )
                    
                    # Update AERO_SWAP to link it to the position
                    swap_data = fix['swap_event_data']
                    swap_data['position_token_id'] = fix['token_id']
                    
                    await session.execute(
                        update(Transaction)
                        .where(Transaction.id == fix['aero_swap_id'])
                        .values(event_data=swap_data)
                    )
                    
                    logger.info(f"Linked position {fix['token_id']} with AERO swap")
                
                await session.commit()
                logger.info("All links created successfully!")
            else:
                logger.info("\nDRY RUN - No changes made. Run with --execute to apply fixes.")
        else:
            logger.info("No unlinked AERO swaps found.")


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Link AERO swaps to positions by proximity')
    parser.add_argument('--execute', action='store_true', help='Actually apply the fixes (default is dry run)')
    
    args = parser.parse_args()
    
    await link_aero_swaps(dry_run=not args.execute)


if __name__ == "__main__":
    asyncio.run(main())