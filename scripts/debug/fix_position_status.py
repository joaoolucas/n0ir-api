#!/usr/bin/env python3
"""Fix position 23569687 status to active"""

import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

async def fix_position_status():
    """Update position status to active."""
    
    # Get database URL
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set")
        return
    
    # Convert to asyncpg URL if needed
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    print(f"Connecting to database...")
    
    # Create engine and session
    engine = create_async_engine(db_url)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Check current status
        result = await session.execute(
            text("SELECT token_id, user_id, status FROM positions WHERE token_id = 23569687")
        )
        row = result.fetchone()
        
        if row:
            print(f"Found position 23569687:")
            print(f"  User ID: {row[1]}")
            print(f"  Current status: {row[2]}")
            
            if row[2] != 'active':
                # Update to active
                await session.execute(
                    text("UPDATE positions SET status = 'active' WHERE token_id = 23569687")
                )
                await session.commit()
                print(f"✓ Updated position status to 'active'")
            else:
                print("Position already has status 'active'")
        else:
            print("ERROR: Position 23569687 not found in database")
    
    await engine.dispose()
    print("Done!")

if __name__ == "__main__":
    asyncio.run(fix_position_status())