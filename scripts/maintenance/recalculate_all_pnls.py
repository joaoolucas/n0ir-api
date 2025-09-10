#!/usr/bin/env python3
"""
Migration script to recalculate all user PNLs with the new position-based logic.

This script:
1. Fetches all users from the database
2. Recalculates their PNL using the new position-based method
3. Updates their PNL values in the database

Run with: python recalculate_all_pnls.py
"""

import asyncio
import os
from datetime import datetime
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
import logging

# Add parent directory to path to import app modules
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.user_service import UserService
from app.database.models.user import User
from app.database.models.position import Position, PositionStatus
from app.core.config import settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create async engine
engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def recalculate_all_user_pnls():
    """Recalculate PNL for all users using the new position-based logic."""
    
    logger.info("=" * 80)
    logger.info("Starting PNL recalculation for all users")
    logger.info("=" * 80)
    
    async with AsyncSessionLocal() as db:
        service = UserService(db)
        
        # Get all users
        stmt = select(User)
        result = await db.execute(stmt)
        users = result.scalars().all()
        
        total_users = len(users)
        logger.info(f"Found {total_users} users to process")
        
        success_count = 0
        error_count = 0
        users_with_positions = 0
        
        for i, user in enumerate(users, 1):
            try:
                logger.info(f"[{i}/{total_users}] Processing user: {user.user_id}")
                
                # Get user's positions to check if they have any
                positions = await service.get_user_positions(user.user_id)
                
                if positions:
                    users_with_positions += 1
                    logger.info(f"  - Found {len(positions)} positions")
                    
                    # Log current PNL values
                    logger.info(f"  - Current PNL: Unrealized={user.unrealized_pnl_usdc}, Realized={user.realized_pnl_usdc}")
                    
                    # Recalculate PNL with new logic
                    await service.recalculate_user_pnl(user.user_id)
                    
                    # Refresh user to get updated values
                    await db.refresh(user)
                    
                    # Log new PNL values
                    logger.info(f"  - New PNL: Unrealized={user.unrealized_pnl_usdc}, Realized={user.realized_pnl_usdc}")
                    
                    success_count += 1
                else:
                    # User has no positions, set PNL to 0
                    if user.unrealized_pnl_usdc != 0 or user.realized_pnl_usdc != 0:
                        logger.info(f"  - No positions, resetting PNL to 0")
                        await service.update_user_pnl(
                            user_id=user.user_id,
                            unrealized_pnl=Decimal(0),
                            realized_pnl=Decimal(0),
                            unrealized_pnl_percentage=Decimal(0),
                            realized_pnl_percentage=Decimal(0)
                        )
                    else:
                        logger.info(f"  - No positions, PNL already 0")
                    success_count += 1
                    
            except Exception as e:
                logger.error(f"  - ERROR processing user {user.user_id}: {e}")
                error_count += 1
                continue
        
        # Commit all changes
        await db.commit()
        
        logger.info("=" * 80)
        logger.info("PNL Recalculation Complete!")
        logger.info(f"Total users processed: {total_users}")
        logger.info(f"Users with positions: {users_with_positions}")
        logger.info(f"Successful: {success_count}")
        logger.info(f"Errors: {error_count}")
        logger.info("=" * 80)


async def verify_sample_users():
    """Verify PNL calculations for a few sample users."""
    
    logger.info("\n" + "=" * 80)
    logger.info("Verifying sample users")
    logger.info("=" * 80)
    
    async with AsyncSessionLocal() as db:
        # Get a few users with positions
        stmt = select(User).join(Position).limit(5)
        result = await db.execute(stmt)
        sample_users = result.scalars().unique().all()
        
        for user in sample_users:
            logger.info(f"\nUser: {user.user_id}")
            
            # Get positions
            stmt = select(Position).where(Position.user_id == user.user_id)
            result = await db.execute(stmt)
            positions = result.scalars().all()
            
            active_positions = [p for p in positions if p.status == PositionStatus.ACTIVE]
            closed_positions = [p for p in positions if p.status == PositionStatus.CLOSED]
            
            # Calculate expected PNL
            expected_realized = sum(p.realized_pnl_usdc or Decimal(0) for p in closed_positions)
            expected_unrealized = sum(
                (p.current_value_usdc or p.entry_amount_usdc) - p.entry_amount_usdc 
                for p in active_positions
            )
            
            logger.info(f"  Active positions: {len(active_positions)}")
            logger.info(f"  Closed positions: {len(closed_positions)}")
            logger.info(f"  Expected Realized PNL: {expected_realized}")
            logger.info(f"  Expected Unrealized PNL: {expected_unrealized}")
            logger.info(f"  Actual Realized PNL: {user.realized_pnl_usdc}")
            logger.info(f"  Actual Unrealized PNL: {user.unrealized_pnl_usdc}")
            
            # Check if they match
            if abs(expected_realized - (user.realized_pnl_usdc or Decimal(0))) < Decimal("0.01"):
                logger.info("  ✅ Realized PNL matches!")
            else:
                logger.warning("  ⚠️ Realized PNL mismatch!")
                
            if abs(expected_unrealized - (user.unrealized_pnl_usdc or Decimal(0))) < Decimal("0.01"):
                logger.info("  ✅ Unrealized PNL matches!")
            else:
                logger.warning("  ⚠️ Unrealized PNL mismatch!")


async def main():
    """Main function to run the migration."""
    try:
        # Run the recalculation
        await recalculate_all_user_pnls()
        
        # Verify a few sample users
        await verify_sample_users()
        
        logger.info("\n🎉 Migration completed successfully!")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


if __name__ == "__main__":
    # Confirm before running
    print("\n" + "=" * 80)
    print("PNL RECALCULATION MIGRATION")
    print("=" * 80)
    print("\nThis script will recalculate PNL for ALL users using the new position-based logic.")
    print("The new logic:")
    print("  - Calculates PNL only from positions (not portfolio value)")
    print("  - Withdrawals no longer affect PNL")
    print("  - Works correctly for users with no deposits")
    print("\nDatabase:", settings.database_url.split('@')[1] if '@' in settings.database_url else 'local')
    
    response = input("\nDo you want to proceed? (yes/no): ")
    
    if response.lower() == 'yes':
        asyncio.run(main())
    else:
        print("Migration cancelled.")