#!/usr/bin/env python3
"""Mark migration 025 as complete since tables already exist."""

import os
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.config import settings
from app.core.logger import logger

async def mark_migration_complete():
    """Mark migration 025 as already applied."""
    try:
        # Get database URL
        db_url = settings.get_database_url
        if not db_url:
            logger.error("No database URL configured")
            return False
        
        # Ensure it uses asyncpg
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
        
        logger.info(f"Connecting to database...")
        
        # Create async engine
        engine = create_async_engine(db_url)
        
        async with engine.begin() as conn:
            # Check current version
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            current_version = result.scalar()
            logger.info(f"Current migration version: {current_version}")
            
            if current_version == "024_relax_position_fields":
                # Update to 025 since tables already exist
                await conn.execute(text("""
                    UPDATE alembic_version 
                    SET version_num = '025_add_hedge_positions'
                    WHERE version_num = '024_relax_position_fields'
                """))
                logger.info("✅ Marked migration 025_add_hedge_positions as complete")
            else:
                logger.info(f"Migration is at version {current_version}, no update needed")
        
        await engine.dispose()
        return True
        
    except Exception as e:
        logger.error(f"Failed to mark migration complete: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(mark_migration_complete())
    exit(0 if success else 1)