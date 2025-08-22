#!/usr/bin/env python3
"""Sync PnL for all users to fix any calculation issues"""

import asyncio
import os
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.database.models.user import User
from app.services.user_service import UserService
from datetime import datetime

async def sync_all_users_pnl():
    """Recalculate PnL for all users"""
    
    # Get database URL
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        # Use default local database
        db_url = "postgresql+asyncpg://n0ir_user:n0ir_pass@localhost/n0ir_db"
    
    # Convert to asyncpg URL if needed
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    print(f"Connecting to database...")
    
    # Create engine and session
    engine = create_async_engine(db_url)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Get all users
        result = await session.execute(select(User))
        users = result.scalars().all()
        
        print(f"Found {len(users)} users to sync")
        
        # Create UserService instance
        service = UserService(session)
        
        # Sync each user's PnL
        for user in users:
            try:
                print(f"\nSyncing PnL for user: {user.user_id}")
                
                # Recalculate PnL with fixed logic
                await service.recalculate_user_pnl(user.user_id)
                
                # Commit changes
                await session.commit()
                
                # Refresh user to get updated values
                await session.refresh(user)
                
                print(f"  ✓ Unrealized PnL: {user.unrealized_pnl_usdc}")
                print(f"  ✓ Realized PnL: {user.realized_pnl_usdc}")
                print(f"  ✓ Unrealized %: {user.unrealized_pnl_percentage}%")
                print(f"  ✓ Realized %: {user.realized_pnl_percentage}%")
                
            except Exception as e:
                print(f"  ✗ Error syncing user {user.user_id}: {e}")
                await session.rollback()
    
    await engine.dispose()
    print(f"\n✅ PnL sync completed at {datetime.now()}")

if __name__ == "__main__":
    asyncio.run(sync_all_users_pnl())