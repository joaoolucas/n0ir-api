#!/usr/bin/env python3
"""
Script to drop all data from the database by dropping and recreating all tables.

WARNING: This will DELETE ALL DATA in the database!

Run with: python3 drop_all_data.py
"""

import asyncio
import os
import sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.base import Base
from app.core.config import settings

# Import all models to ensure they're registered with Base
from app.database.models.user import User
from app.database.models.position import Position
from app.database.models.transaction import Transaction
from app.database.models.agent_state import AgentState
from app.database.models.daily_metrics import DailyMetrics
from app.database.models.pool_metrics import PoolMetrics
from app.database.models.strategy_decision import StrategyDecision

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def drop_all_tables(engine):
    """Drop all tables in the database."""
    async with engine.begin() as conn:
        # Drop all tables
        logger.info("Dropping all tables...")
        await conn.run_sync(Base.metadata.drop_all)
        logger.info("All tables dropped successfully!")


async def create_all_tables(engine):
    """Create all tables in the database."""
    async with engine.begin() as conn:
        # Create all tables
        logger.info("Creating all tables...")
        await conn.run_sync(Base.metadata.create_all)
        logger.info("All tables created successfully!")


async def verify_database_empty(engine):
    """Verify that all tables are empty."""
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with AsyncSessionLocal() as session:
        # Check each table
        tables_to_check = [
            ("users", "SELECT COUNT(*) FROM users"),
            ("positions", "SELECT COUNT(*) FROM positions"),
            ("transactions", "SELECT COUNT(*) FROM transactions"),
            ("agent_states", "SELECT COUNT(*) FROM agent_states"),
            ("daily_metrics", "SELECT COUNT(*) FROM daily_metrics"),
            ("pool_metrics", "SELECT COUNT(*) FROM pool_metrics"),
            ("strategy_decisions", "SELECT COUNT(*) FROM strategy_decisions"),
        ]
        
        logger.info("\nVerifying tables are empty:")
        all_empty = True
        
        for table_name, query in tables_to_check:
            try:
                result = await session.execute(text(query))
                count = result.scalar()
                if count == 0:
                    logger.info(f"  ✅ {table_name}: EMPTY")
                else:
                    logger.warning(f"  ⚠️ {table_name}: {count} records found")
                    all_empty = False
            except Exception as e:
                logger.info(f"  ℹ️ {table_name}: Table doesn't exist or error: {e}")
        
        return all_empty


async def main():
    """Main function to drop all data."""
    # Create engine with the database URL
    database_url = "postgresql+asyncpg://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway"
    engine = create_async_engine(database_url, echo=False)
    
    try:
        # Drop all tables
        await drop_all_tables(engine)
        
        # Recreate all tables
        await create_all_tables(engine)
        
        # Verify database is empty
        is_empty = await verify_database_empty(engine)
        
        if is_empty:
            logger.info("\n" + "=" * 80)
            logger.info("✅ SUCCESS: All data has been dropped and tables recreated!")
            logger.info("The database is now completely empty and ready for fresh data.")
            logger.info("=" * 80)
        else:
            logger.warning("\n" + "=" * 80)
            logger.warning("⚠️ WARNING: Some tables still contain data!")
            logger.warning("Please check the tables manually.")
            logger.warning("=" * 80)
            
    except Exception as e:
        logger.error(f"Error during database reset: {e}")
        raise
    finally:
        await engine.dispose()


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("⚠️  DATABASE RESET WARNING ⚠️")
    print("=" * 80)
    print("\nThis script will DELETE ALL DATA in the database:")
    print("postgresql://postgres:***@shuttle.proxy.rlwy.net:37929/railway")
    print("\nThis action is IRREVERSIBLE!")
    print("\nTables to be dropped and recreated:")
    print("  - users")
    print("  - positions")
    print("  - transactions")
    print("  - agent_states")
    print("  - daily_metrics")
    print("  - pool_metrics")
    print("  - strategy_decisions")
    
    response = input("\nAre you ABSOLUTELY SURE you want to delete all data? Type 'DELETE ALL' to confirm: ")
    
    if response == 'DELETE ALL':
        print("\nProceeding with database reset...")
        asyncio.run(main())
    else:
        print("\nDatabase reset cancelled. No data was deleted.")