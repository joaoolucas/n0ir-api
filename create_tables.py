#!/usr/bin/env python3
"""
Create all database tables using SQLAlchemy models.
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine
from app.database.base import Base
from app.core.config import settings

# Import all models to ensure they're registered with Base
from app.database.models.user import User
from app.database.models.position import Position
from app.database.models.transaction import Transaction
from app.database.models.agent_event import AgentEvent
from app.database.models.daily_metrics import DailyMetrics
from app.database.models.pool_metrics import PoolMetrics
from app.database.models.strategy_decision import StrategyDecision
from app.database.models.executor_stats import ExecutorStats

async def create_tables():
    """Create all tables in the database."""
    
    # Use the Railway database URL
    DATABASE_URL = "postgresql+asyncpg://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway"
    
    # Create engine
    engine = create_async_engine(DATABASE_URL, echo=True)
    
    try:
        print("Creating database tables...")
        print("=" * 60)
        
        # Create all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        print("=" * 60)
        print("✅ All tables created successfully!")
        
        # List created tables
        async with engine.connect() as conn:
            result = await conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """))
            tables = result.fetchall()
            
            print("\nCreated tables:")
            for table in tables:
                print(f"  ✓ {table[0]}")
        
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        raise
    finally:
        await engine.dispose()

# Import text for SQL query
from sqlalchemy import text

async def main():
    print("=" * 60)
    print("CREATE DATABASE TABLES")
    print("=" * 60)
    print("\nThis will create all necessary tables in the database.")
    print("Database: shuttle.proxy.rlwy.net:37929/railway")
    
    response = input("\nProceed? (yes/no): ")
    
    if response.lower() == 'yes':
        await create_tables()
    else:
        print("Operation cancelled.")

if __name__ == "__main__":
    asyncio.run(main())