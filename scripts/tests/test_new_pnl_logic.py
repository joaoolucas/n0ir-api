#!/usr/bin/env python3
"""Test the new PnL calculation logic."""

import asyncio
import os
from decimal import Decimal
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.services.user_service import UserService
import logging

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


async def test_pnl_calculation():
    """Test PnL calculation for a specific user."""
    async with AsyncSessionLocal() as db:
        service = UserService(db)
        
        # Test user from production
        user_id = "0xC2952cc28EDf37B053188D89e6ac888B9855d132"
        
        logger.info(f"Testing PnL calculation for user {user_id}")
        
        # Get user
        user = await service.get_user(user_id)
        if not user:
            logger.error(f"User {user_id} not found")
            return
        
        # Get current PnL values before recalculation
        logger.info(f"Before recalculation:")
        logger.info(f"  Realized PnL: {user.realized_pnl_usdc}")
        logger.info(f"  Unrealized PnL: {user.unrealized_pnl_usdc}")
        
        # Recalculate PnL with new logic
        await service.recalculate_user_pnl(user_id)
        
        # Refresh user to get updated values
        await db.refresh(user)
        
        logger.info(f"After recalculation:")
        logger.info(f"  Realized PnL: {user.realized_pnl_usdc}")
        logger.info(f"  Unrealized PnL: {user.unrealized_pnl_usdc}")
        
        # Get positions to understand the breakdown
        positions = await service.get_user_positions(user_id)
        active_positions = [p for p in positions if p.status == 'ACTIVE']
        closed_positions = [p for p in positions if p.status == 'CLOSED']
        
        logger.info(f"\nPosition breakdown:")
        logger.info(f"  Active positions: {len(active_positions)}")
        logger.info(f"  Closed positions: {len(closed_positions)}")
        
        # Calculate expected realized PnL from closed positions
        expected_realized = Decimal(0)
        for p in closed_positions:
            if p.realized_pnl_usdc:
                expected_realized += p.realized_pnl_usdc
                logger.info(f"    Position {p.nft_token_id}: PnL={p.realized_pnl_usdc}")
        
        logger.info(f"\nExpected realized PnL from closed positions: {expected_realized}")
        
        # Get deposit and withdrawal totals
        deposits, withdrawals = await service.get_deposit_withdrawal_totals(user_id)
        logger.info(f"\nCash flow:")
        logger.info(f"  Total deposits: {deposits}")
        logger.info(f"  Total withdrawals: {withdrawals}")
        logger.info(f"  Net invested: {deposits - withdrawals}")


async def main():
    """Main entry point."""
    try:
        await test_pnl_calculation()
        logger.info("Test completed successfully")
    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())