#!/usr/bin/env python3
"""
Script to drop all enum types in the database.
"""

import asyncio
import asyncpg

async def drop_all_enums():
    # Database connection parameters
    DATABASE_URL = "postgresql://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway"
    
    # Connect to the database
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        print("Connected to database successfully!")
        
        # Get all enum types
        enums = await conn.fetch("""
            SELECT typname 
            FROM pg_type 
            WHERE typtype = 'e'
            AND typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
            ORDER BY typname
        """)
        
        print(f"\nFound {len(enums)} enum types to drop:")
        for enum in enums:
            print(f"  - {enum['typname']}")
        
        print("\nDropping enum types...")
        for enum in enums:
            enum_name = enum['typname']
            try:
                await conn.execute(f"DROP TYPE IF EXISTS {enum_name} CASCADE")
                print(f"  ✓ Dropped enum: {enum_name}")
            except Exception as e:
                print(f"  ✗ Error dropping {enum_name}: {e}")
        
        # Verify all enums are dropped
        remaining_enums = await conn.fetch("""
            SELECT typname 
            FROM pg_type 
            WHERE typtype = 'e'
            AND typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
        """)
        
        if remaining_enums:
            print("\n⚠️  WARNING: The following enum types still exist:")
            for enum in remaining_enums:
                print(f"  - {enum['typname']}")
        else:
            print("\n✅ SUCCESS: All enum types have been dropped!")
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
    finally:
        await conn.close()
        print("\nDatabase connection closed.")

async def main():
    print("=" * 60)
    print("DROP ALL ENUM TYPES")
    print("=" * 60)
    
    response = input("\nType 'YES' to confirm: ")
    
    if response == 'YES':
        await drop_all_enums()
    else:
        print("\nOperation cancelled.")

if __name__ == "__main__":
    asyncio.run(main())