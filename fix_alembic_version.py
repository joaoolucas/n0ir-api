#!/usr/bin/env python3
"""
Fix alembic version to skip the problematic migration that's causing deployment crash.
The migration d8de59893c30 tries to rename wallet_address to cdp_wallet_address,
but our fresh tables already have cdp_wallet_address.
"""

import asyncio
import asyncpg

async def fix_alembic_version():
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
        
        # Check current version
        current_version = await conn.fetchval("SELECT version_num FROM alembic_version")
        print(f"Current alembic version: {current_version}")
        
        # Clear any existing version
        await conn.execute("DELETE FROM alembic_version")
        
        # Insert the LATEST migration to skip all migrations
        # since we already have the latest schema from create_tables.py
        await conn.execute("""
            INSERT INTO alembic_version (version_num) 
            VALUES ('008_add_agent_state_tracking')
        """)
        print("✓ Set alembic version to 008_add_agent_state_tracking (latest migration)")
        
        # Verify
        version = await conn.fetchval("SELECT version_num FROM alembic_version")
        print(f"✓ New migration version: {version}")
        print("\n✅ Alembic version fixed! The deployment should work now.")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
    finally:
        await conn.close()
        print("\nDatabase connection closed.")

async def main():
    print("=" * 60)
    print("FIX ALEMBIC VERSION FOR DEPLOYMENT")
    print("=" * 60)
    print("\nThis will set the alembic version to the latest migration")
    print("to skip all migrations since we have fresh tables with the latest schema.")
    
    await fix_alembic_version()

if __name__ == "__main__":
    asyncio.run(main())