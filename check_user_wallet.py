#!/usr/bin/env python3
"""Check user's CDP wallet address."""

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.database.models.user import User
from app.core.config import settings

async def check_user_wallet():
    """Check the CDP wallet address for the user."""
    # Create database connection
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Query user
        user_id = "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51"
        stmt = select(User).where(User.user_id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user:
            print(f"User ID: {user.user_id}")
            print(f"CDP Wallet Address: {user.cdp_wallet_address}")
            print(f"CDP Wallet Name: {user.cdp_wallet_name}")
            print(f"Status: {user.status}")
            print(f"Agent Status: {user.agent_status}")
        else:
            print(f"User {user_id} not found")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_user_wallet())