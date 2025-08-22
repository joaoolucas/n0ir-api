#!/usr/bin/env python3
"""Fix the alembic version table to use shorter version names"""

import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def fix_migration():
    # Get database URL
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        # Use default local database
        db_url = "postgresql+asyncpg://n0ir_user:n0ir_pass@localhost/n0ir_db"
    
    # Create engine
    engine = create_async_engine(db_url)
    
    async with engine.begin() as conn:
        # Check current version
        result = await conn.execute(text("SELECT version_num FROM alembic_version"))
        current = result.scalar()
        print(f"Current version: {current}")
        
        # Update to shorter name if needed
        if current == "005_add_pool_name_to_positions":
            await conn.execute(text("UPDATE alembic_version SET version_num = '005_add_pool_name_to_pos'"))
            print("Updated to shorter version name: 005_add_pool_name_to_pos")
        else:
            print(f"Version is already correct: {current}")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(fix_migration())