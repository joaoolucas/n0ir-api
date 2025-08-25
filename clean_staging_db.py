#!/usr/bin/env python3
"""Script to clean all data from the staging database"""

import asyncio
import os
import sys

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from app.core.logger import logger


async def clean_database():
    """Clean all data from the staging database."""
    
    # Use the provided staging database URL
    database_url = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"
    
    # Convert postgres:// to postgresql+asyncpg:// for async support
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    # Create async engine
    engine = create_async_engine(database_url, echo=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        try:
            logger.info("Starting database cleanup...")
            
            # Disable foreign key checks temporarily
            await db.execute(text("SET session_replication_role = replica;"))
            
            # Delete from all tables in the correct order (children first)
            tables_to_clean = [
                "agent_events",
                "daily_metrics",
                "executor_stats",
                "transactions",
                "positions",
                "users"
            ]
            
            for table in tables_to_clean:
                try:
                    result = await db.execute(text(f"DELETE FROM {table}"))
                    count = result.rowcount
                    logger.info(f"Deleted {count} rows from {table}")
                except Exception as e:
                    logger.warning(f"Could not clean table {table}: {e}")
            
            # Re-enable foreign key checks
            await db.execute(text("SET session_replication_role = DEFAULT;"))
            
            # Commit all changes
            await db.commit()
            
            # Verify counts
            logger.info("\nVerifying cleanup:")
            for table in tables_to_clean:
                try:
                    result = await db.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    count = result.scalar()
                    logger.info(f"{table}: {count} rows remaining")
                except Exception as e:
                    logger.warning(f"Could not verify table {table}: {e}")
            
            logger.info("\nDatabase cleanup completed successfully!")
            
        except Exception as e:
            logger.error(f"Error cleaning database: {e}")
            await db.rollback()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    # Confirm before proceeding
    print("\n⚠️  WARNING: This will DELETE ALL DATA from the staging database!")
    print("Database: postgresql://postgres:***@shuttle.proxy.rlwy.net:17669/railway")
    print("\nProceeding with cleanup...")
    asyncio.run(clean_database())