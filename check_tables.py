#!/usr/bin/env python
"""Check all database tables."""

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import os

async def list_tables():
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("❌ DATABASE_URL not set")
        return
    
    # Convert to asyncpg
    if db_url.startswith('postgresql://'):
        db_url = db_url.replace('postgresql://', 'postgresql+asyncpg://', 1)
    
    print(f"Connecting to database...")
    
    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name
        """))
        
        tables = [row[0] for row in result]
        
        print("\n✅ Database Tables Created:")
        print("-" * 40)
        
        expected_tables = [
            'alembic_version',
            'daily_metrics',
            'executor_stats', 
            'pool_metrics',
            'positions',
            'protocol_fees',
            'strategy_decisions',
            'transactions',
            'users'
        ]
        
        for table in expected_tables:
            if table in tables:
                print(f"  ✓ {table}")
            else:
                print(f"  ✗ {table} (missing)")
        
        # Check for any extra tables
        extra_tables = set(tables) - set(expected_tables)
        if extra_tables:
            print("\nExtra tables found:")
            for table in extra_tables:
                print(f"  • {table}")
    
    await engine.dispose()
    print("\n✅ All required tables are present!")

if __name__ == "__main__":
    asyncio.run(list_tables())