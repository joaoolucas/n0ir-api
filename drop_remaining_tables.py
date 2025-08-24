#!/usr/bin/env python3
"""
Script to drop the remaining tables.
"""

import asyncio
import asyncpg

async def drop_remaining_tables():
    # Database connection parameters
    DATABASE_URL = "postgresql://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway"
    
    # Connect to the database
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        print("Connected to database successfully!")
        
        # Drop remaining tables
        tables_to_drop = [
            "agent_events",
            "alembic_version",
            "executor_stats",
            "protocol_fees"
        ]
        
        print("\nDropping remaining tables...")
        for table in tables_to_drop:
            try:
                await conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
                print(f"  ✓ Dropped table: {table}")
            except Exception as e:
                print(f"  ✗ Error dropping {table}: {e}")
        
        # List any remaining tables
        remaining_tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        
        if remaining_tables:
            print("\n⚠️  WARNING: The following tables still exist:")
            for table in remaining_tables:
                print(f"  - {table['table_name']}")
        else:
            print("\n✅ SUCCESS: All tables have been dropped!")
            print("The database is now completely empty.")
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
    finally:
        await conn.close()
        print("\nDatabase connection closed.")

async def main():
    print("=" * 60)
    print("DROP REMAINING TABLES")
    print("=" * 60)
    print("\nThis will drop the remaining tables:")
    print("  - agent_events")
    print("  - alembic_version")
    print("  - executor_stats")
    print("  - protocol_fees")
    
    response = input("\nType 'YES' to confirm: ")
    
    if response == 'YES':
        await drop_remaining_tables()
    else:
        print("\nOperation cancelled.")

if __name__ == "__main__":
    asyncio.run(main())