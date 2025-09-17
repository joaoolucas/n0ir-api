#!/usr/bin/env python3
"""
Script to immediately drop unwanted tables from the database.
We only want 3 core tables: users, positions, transactions
"""

import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings
from loguru import logger

async def cleanup_tables():
    """Drop unwanted tables that keep getting recreated."""
    
    # Get database URL
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return
    
    # Convert to async URL if needed
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
    
    # Create engine
    engine = create_async_engine(database_url, echo=True)
    
    try:
        async with engine.begin() as conn:
            # List of tables to drop
            tables_to_drop = [
                'wallet_transactions',
                'liquidity_events',
                'blockchain_sync',
                'daily_metrics',
                'pool_metrics',
                'executor_stats',
                'strategy_decisions'
            ]
            
            logger.info("Starting cleanup of unwanted tables...")
            
            for table in tables_to_drop:
                try:
                    await conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                    logger.info(f"✅ Dropped table: {table}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not drop {table}: {e}")
            
            # Verify what tables remain
            result = await conn.execute(text("""
                SELECT tablename FROM pg_tables 
                WHERE schemaname = 'public' 
                ORDER BY tablename
            """))
            remaining_tables = [row[0] for row in result.fetchall()]
            
            logger.info(f"\n✅ Cleanup complete!")
            logger.info(f"📊 Remaining tables: {', '.join(remaining_tables)}")
            
            # Check if we have exactly the 3 core tables (plus alembic)
            core_tables = {'users', 'positions', 'transactions'}
            actual_tables = set(remaining_tables) - {'alembic_version'}
            
            if actual_tables == core_tables:
                logger.success("✅ Database is clean! Only 3 core tables remain.")
            else:
                extra = actual_tables - core_tables
                missing = core_tables - actual_tables
                if extra:
                    logger.warning(f"⚠️ Extra tables found: {extra}")
                if missing:
                    logger.error(f"❌ Missing core tables: {missing}")
    
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(cleanup_tables())