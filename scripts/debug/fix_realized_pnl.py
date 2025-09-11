#!/usr/bin/env python3
"""Fix realized PnL values for closed positions.

This script corrects positions where realized_pnl_usdc was incorrectly
set to the final value instead of the actual profit/loss.
"""

import asyncio
import os
from decimal import Decimal
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.database.models.position import Position
from app.database.models.user import User
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")

# Convert to async URL if needed
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def fix_realized_pnl():
    """Fix realized PnL values for closed positions."""
    async with AsyncSessionLocal() as db:
        try:
            # Find all closed positions
            stmt = select(Position).where(Position.status == 'CLOSED')
            result = await db.execute(stmt)
            positions = result.scalars().all()
            
            logger.info(f"Found {len(positions)} closed positions")
            
            fixed_count = 0
            for position in positions:
                # Check if realized_pnl seems wrong (way too high)
                if position.realized_pnl_usd and position.entry_amount_usdc:
                    # If realized PnL is close to or greater than the entry amount,
                    # it's likely the final value was stored instead of the PnL
                    pnl_ratio = float(position.realized_pnl_usd) / float(position.entry_amount_usdc)
                    
                    if pnl_ratio > 0.5:  # If PnL is more than 50% of entry, it's suspicious
                        old_pnl = position.realized_pnl_usd
                        
                        # Calculate correct PnL
                        if position.current_value_usdc:
                            correct_pnl = position.current_value_usdc - position.entry_amount_usdc
                        else:
                            # If current_value is not set, use realized_pnl as final value
                            final_value = position.realized_pnl_usd
                            correct_pnl = final_value - position.entry_amount_usdc
                            position.current_value_usdc = final_value
                        
                        position.realized_pnl_usd = correct_pnl
                        
                        logger.info(
                            f"Fixed position {position.token_id}: "
                            f"entry={position.entry_amount_usdc}, "
                            f"final={position.current_value_usdc}, "
                            f"old_pnl={old_pnl} -> new_pnl={correct_pnl}"
                        )
                        fixed_count += 1
            
            if fixed_count > 0:
                await db.commit()
                logger.info(f"Fixed {fixed_count} positions")
            else:
                logger.info("No positions needed fixing")
                
        except Exception as e:
            logger.error(f"Error fixing realized PnL: {e}")
            await db.rollback()
            raise


async def main():
    """Main entry point."""
    try:
        await fix_realized_pnl()
        logger.info("Successfully completed PnL fix")
    except Exception as e:
        logger.error(f"Failed to fix PnL: {e}")
        raise
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())