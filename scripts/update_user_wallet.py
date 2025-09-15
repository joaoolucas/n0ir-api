"""Script to update user's CDP wallet address."""

import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.database.session import AsyncSessionLocal
from app.database.models import User
import sys

async def update_user_wallet(user_id: str, wallet_address: str):
    """Update user's CDP wallet address."""
    async with AsyncSessionLocal() as session:
        # Check if user exists
        stmt = select(User).where(User.user_id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"User {user_id} not found")
            return False
        
        # Update wallet address
        stmt = update(User).where(User.user_id == user_id).values(cdp_wallet_address=wallet_address)
        await session.execute(stmt)
        await session.commit()
        
        print(f"Updated user {user_id} with CDP wallet {wallet_address}")
        return True

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python update_user_wallet.py <user_id> <wallet_address>")
        sys.exit(1)
    
    user_id = sys.argv[1]
    wallet_address = sys.argv[2]
    
    asyncio.run(update_user_wallet(user_id, wallet_address))