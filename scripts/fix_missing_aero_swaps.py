#!/usr/bin/env python3
"""
Script to find and link missing AERO_SWAP transactions with their corresponding POSITION_CLOSED transactions.

This script:
1. Finds all POSITION_CLOSED transactions with aero_swap_usdc = 0
2. Searches for AERO_SWAP transactions in the same block or nearby blocks
3. Updates the event_data to include the correct aero_swap_usdc values
"""

import asyncio
import json
from datetime import datetime
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

# Known AERO swap routers
AERO_SWAP_ROUTERS = [
    "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",  # SwapRouter02
    "0xecC41a494F45Cd8704e6Cf4Ce982B20c94C66a36",  # OKX DEX
    "0x00c1bc0ca9f703919c2ba320e5f200865f778aae",  # Another router
]

AERO_TOKEN = "0x940181a94A35A4569E4529A3CDfB74e38FD98631"
USDC_TOKEN = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


async def find_aero_swap_for_position_close(
    session: AsyncSession,
    user_id: str,
    token_id: str,
    block_number: int,
    tx_hash: str
) -> Optional[Dict]:
    """Find AERO_SWAP transaction for a given position close."""
    
    # Search for AERO_SWAP transactions within 20 blocks
    result = await session.execute(
        select(Transaction).where(
            and_(
                Transaction.user_id == user_id,
                Transaction.tx_type == 'AERO_SWAP',
                Transaction.block_number >= block_number,
                Transaction.block_number <= block_number + 20
            )
        ).order_by(Transaction.block_number.asc())
    )
    
    aero_swaps = result.scalars().all()
    
    for swap in aero_swaps:
        event_data = swap.event_data
        if isinstance(event_data, str):
            event_data = json.loads(event_data)
        
        # Check if this swap references the same token_id
        swap_token_id = event_data.get('position_token_id') or event_data.get('tokenId')
        if swap_token_id == token_id:
            # Get amount from event_data
            amount = event_data.get('amount_usdc', 0)
            if not amount and swap.amount_usdc:
                amount = float(swap.amount_usdc)
            return {
                'transaction_id': swap.id,
                'amount_usdc': float(amount) if amount else 0,
                'tx_hash': swap.tx_hash,
                'block_number': swap.block_number
            }
    
    # If no direct match, try to find deposits from known routers
    result = await session.execute(
        select(Transaction).where(
            and_(
                Transaction.user_id == user_id,
                Transaction.tx_type == 'DEPOSIT',
                Transaction.block_number >= block_number,
                Transaction.block_number <= block_number + 20
            )
        ).order_by(Transaction.block_number.asc())
    )
    
    deposits = result.scalars().all()
    
    for deposit in deposits:
        event_data = deposit.event_data
        if isinstance(event_data, str):
            event_data = json.loads(event_data)
        
        from_address = event_data.get('from_address', '').lower()
        
        # Check if from known router
        if any(router.lower() == from_address for router in AERO_SWAP_ROUTERS):
            amount = event_data.get('amount_usdc', 0)
            if not amount and deposit.amount_usdc:
                amount = float(deposit.amount_usdc)
            return {
                'transaction_id': deposit.id,
                'amount_usdc': float(amount) if amount else 0,
                'tx_hash': deposit.tx_hash,
                'block_number': deposit.block_number,
                'is_deposit': True
            }
    
    return None


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


async def fix_missing_aero_swaps(dry_run: bool = True):
    """Main function to fix missing AERO swap values."""
    
    async for session in get_async_session():
        # Find all POSITION_CLOSED transactions
        result = await session.execute(
            select(Transaction).where(
                Transaction.tx_type == 'POSITION_CLOSED'
            ).order_by(Transaction.block_timestamp.desc())
        )
        
        position_closes = result.scalars().all()
        
        logger.info(f"Found {len(position_closes)} POSITION_CLOSED transactions with missing AERO swaps")
        
        fixes_needed = []
        
        for position in position_closes:
            event_data = position.event_data
            if isinstance(event_data, str):
                event_data = json.loads(event_data)
            
            token_id = event_data.get('tokenId') or event_data.get('token_id')
            user_id = position.user_id
            block_number = position.block_number
            
            # Skip if event_data already has non-zero aero_swap_usdc
            existing_aero = event_data.get('aero_swap_usdc', 0)
            if existing_aero and float(existing_aero) > 0:
                logger.debug(f"Position {token_id} already has aero_swap_usdc in event_data: {existing_aero}")
                continue
            
            logger.info(f"Checking position {token_id} for user {user_id} at block {block_number}")
            
            # Find corresponding AERO swap
            aero_swap = await find_aero_swap_for_position_close(
                session, user_id, token_id, block_number, position.tx_hash
            )
            
            if aero_swap:
                fixes_needed.append({
                    'position_tx_id': position.id,
                    'token_id': token_id,
                    'aero_swap_amount': aero_swap['amount_usdc'],
                    'aero_swap_tx': aero_swap.get('tx_hash'),
                    'event_data': event_data
                })
                logger.info(f"Found AERO swap for position {token_id}: {aero_swap['amount_usdc']} USDC")
            else:
                logger.debug(f"No AERO swap found for position {token_id}")
        
        # Apply fixes
        if fixes_needed:
            logger.info(f"\nFound {len(fixes_needed)} positions needing fixes:")
            
            for fix in fixes_needed:
                logger.info(f"  Token {fix['token_id']}: {fix['aero_swap_amount']} USDC")
            
            if not dry_run:
                logger.info("\nApplying fixes...")
                
                for fix in fixes_needed:
                    # Update event_data
                    event_data = fix['event_data']
                    event_data['aero_swap_usdc'] = fix['aero_swap_amount']
                    
                    # Recalculate total_return_usdc
                    usdc_out = float(event_data.get('amount_usdc', 0))
                    total_return = usdc_out + fix['aero_swap_amount']
                    event_data['total_return_usdc'] = total_return
                    
                    # Update the transaction (only event_data since aero_swap_usdc is computed property)
                    await session.execute(
                        update(Transaction)
                        .where(Transaction.id == fix['position_tx_id'])
                        .values(
                            event_data=event_data
                        )
                    )
                    
                    logger.info(f"Updated position {fix['token_id']}")
                
                await session.commit()
                logger.info("All fixes applied successfully!")
            else:
                logger.info("\nDRY RUN - No changes made. Run with --execute to apply fixes.")
        else:
            logger.info("No fixes needed - all positions have correct AERO swap values or no swaps found.")


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Fix missing AERO swap values in POSITION_CLOSED transactions')
    parser.add_argument('--execute', action='store_true', help='Actually apply the fixes (default is dry run)')
    
    args = parser.parse_args()
    
    await fix_missing_aero_swaps(dry_run=not args.execute)


if __name__ == "__main__":
    asyncio.run(main())