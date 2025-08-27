#!/usr/bin/env python3
"""Check migration chain in staging database."""

import asyncio
import asyncpg
from urllib.parse import urlparse

# Database URL from Railway staging
DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"


async def check_migrations():
    """Check migration chain."""
    
    # Parse database URL
    parsed = urlparse(DATABASE_URL)
    
    # Connect to database
    conn = await asyncpg.connect(
        host=parsed.hostname,
        port=parsed.port,
        user=parsed.username,
        password=parsed.password,
        database=parsed.path.lstrip('/'),
        ssl='require'
    )
    
    print("Connected to staging database")
    
    try:
        # Check alembic version
        version = await conn.fetchrow("SELECT * FROM alembic_version")
        print(f"\nCurrent alembic version: {version['version_num'] if version else 'None'}")
        
        # Check migration history if exists
        history_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'alembic_revision'
            )
        """)
        
        if history_exists:
            print("\nMigration history:")
            history = await conn.fetch("""
                SELECT * FROM alembic_revision 
                ORDER BY revision_id
            """)
            for h in history:
                print(f"  - {h}")
        
        # Check for any references to 006
        print("\nChecking for 006 references in database...")
        
        # List all tables
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name LIKE '%alembic%'
        """)
        print(f"Alembic tables: {[t['table_name'] for t in tables]}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise
    finally:
        await conn.close()
        print("\nDisconnected from database")


if __name__ == "__main__":
    print("🔍 Checking migration chain in Railway staging database")
    asyncio.run(check_migrations())