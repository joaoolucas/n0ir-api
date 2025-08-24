#!/usr/bin/env python3
"""
Mark all migrations as completed in the alembic_version table.
This is useful when starting with a fresh database.
"""

import asyncio
import asyncpg

async def mark_migrations_complete():
    # Database connection parameters
    DATABASE_URL = "postgresql://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway"
    
    # Connect to the database
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        print("Connected to database successfully!")
        
        # Create alembic_version table if it doesn't exist
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS alembic_version (
                version_num VARCHAR(32) NOT NULL PRIMARY KEY
            )
        """)
        print("✓ Alembic version table ready")
        
        # Clear any existing version
        await conn.execute("DELETE FROM alembic_version")
        
        # Insert the latest migration version
        # The latest migration appears to be 30ff38b3b56d
        await conn.execute("""
            INSERT INTO alembic_version (version_num) 
            VALUES ('30ff38b3b56d')
        """)
        print("✓ Marked all migrations as complete (up to 30ff38b3b56d)")
        
        # Verify
        version = await conn.fetchval("SELECT version_num FROM alembic_version")
        print(f"✓ Current migration version: {version}")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
    finally:
        await conn.close()
        print("\nDatabase connection closed.")

async def main():
    print("=" * 60)
    print("MARK MIGRATIONS AS COMPLETE")
    print("=" * 60)
    print("\nThis will mark all migrations as already run.")
    print("Use this when starting with a fresh database.")
    
    response = input("\nType 'YES' to confirm: ")
    
    if response == 'YES':
        await mark_migrations_complete()
    else:
        print("\nOperation cancelled.")

if __name__ == "__main__":
    asyncio.run(main())