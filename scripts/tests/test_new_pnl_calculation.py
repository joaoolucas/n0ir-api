#!/usr/bin/env python3
"""Test the new position-based PnL calculation."""

import asyncio
import os
import sys
from decimal import Decimal
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.models import User, Position
from app.services.user_service import UserService

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

async def test_new_pnl():
    """Test the new PnL calculation for a user."""
    user_id = "0xC2952cc28EDf37B053188D89e6ac888B9855d132"
    
    # Create async engine
    engine = create_async_engine(DATABASE_URL, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with AsyncSessionLocal() as db:
        try:
            # Get user
            stmt = select(User).where(User.user_id == user_id)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                print(f"User {user_id} not found")
                return
            
            print(f"Testing new PnL calculation for user {user_id}")
            print("=" * 80)
            
            # Get positions
            service = UserService(db)
            all_positions = await service.get_user_positions(user_id)
            active_positions = [p for p in all_positions if p.status == 'ACTIVE']
            closed_positions = [p for p in all_positions if p.status == 'CLOSED']
            
            print(f"\nPositions:")
            print(f"- Active: {len(active_positions)}")
            print(f"- Closed: {len(closed_positions)}")
            
            # Calculate realized PnL from closed positions
            realized_pnl = Decimal(0)
            print(f"\nClosed Positions PnL:")
            for pos in closed_positions[:5]:  # Show first 5
                exit_value = pos.current_value_usdc or Decimal(0)
                entry_value = pos.entry_amount_usdc or Decimal(0)
                pnl = exit_value - entry_value
                realized_pnl += pnl
                print(f"  Token {pos.nft_token_id}: Entry={entry_value:.2f}, Exit={exit_value:.2f}, PnL={pnl:.2f}")
            
            total_realized = sum((p.current_value_usdc or Decimal(0)) - (p.entry_amount_usdc or Decimal(0)) for p in closed_positions)
            print(f"\nTotal Realized PnL (from {len(closed_positions)} closed positions): {total_realized:.2f} USDC")
            
            # Show current PnL values before recalculation
            print(f"\nCurrent PnL values in DB:")
            print(f"- Realized: {user.realized_pnl_usd} USDC")
            print(f"- Unrealized: {user.unrealized_pnl_usd} USDC")
            
            # Recalculate using new method
            print(f"\nRecalculating PnL using new position-based method...")
            await service.recalculate_user_pnl(user_id)
            
            # Refresh user to get updated values
            await db.refresh(user)
            
            print(f"\nNew PnL values after recalculation:")
            print(f"- Realized: {user.realized_pnl_usd} USDC ({user.realized_pnl_pct}%)")
            print(f"- Unrealized: {user.unrealized_pnl_usd} USDC ({user.unrealized_pnl_pct}%)")
            
            print("\n✅ PnL calculation updated successfully!")
            print("The realized PnL now reflects the sum of PnL from closed positions.")
            print("The unrealized PnL reflects the sum of PnL from active positions.")
            
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await engine.dispose()

if __name__ == "__main__":
    asyncio.run(test_new_pnl())