#!/usr/bin/env python3
"""
Simple script to drop all tables using raw SQL without SQLAlchemy ORM.
"""

import asyncio
import asyncpg

async def drop_all_tables():
    # Database connection parameters
    DATABASE_URL = "postgresql://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway"
    
    # Connect to the database
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        print("Connected to database successfully!")
        
        # Drop all tables in correct order (to handle foreign key constraints)
        tables_to_drop = [
            "strategy_decisions",
            "pool_metrics", 
            "daily_metrics",
            "agent_states",
            "transactions",
            "positions",
            "users"
        ]
        
        print("\nDropping tables...")
        for table in tables_to_drop:
            try:
                await conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
                print(f"  ✓ Dropped table: {table}")
            except Exception as e:
                print(f"  ✗ Error dropping {table}: {e}")
        
        # Drop sequences
        sequences_to_drop = [
            "transactions_transaction_id_seq",
            "agent_states_state_id_seq",
            "daily_metrics_id_seq",
            "pool_metrics_id_seq",
            "strategy_decisions_id_seq"
        ]
        
        print("\nDropping sequences...")
        for seq in sequences_to_drop:
            try:
                await conn.execute(f"DROP SEQUENCE IF EXISTS {seq} CASCADE")
                print(f"  ✓ Dropped sequence: {seq}")
            except Exception as e:
                print(f"  ✗ Error dropping {seq}: {e}")
        
        # Drop enums
        enums_to_drop = [
            "transactiontype",
            "transactionstatus",
            "positionstatus",
            "agentstatus",
            "strategyaction"
        ]
        
        print("\nDropping enum types...")
        for enum in enums_to_drop:
            try:
                await conn.execute(f"DROP TYPE IF EXISTS {enum} CASCADE")
                print(f"  ✓ Dropped enum: {enum}")
            except Exception as e:
                print(f"  ✗ Error dropping {enum}: {e}")
        
        # List remaining tables
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
            print("The database is now empty.")
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
    finally:
        await conn.close()
        print("\nDatabase connection closed.")

async def main():
    print("=" * 60)
    print("DATABASE RESET - DROP ALL TABLES")
    print("=" * 60)
    print("\nThis will DELETE ALL DATA from:")
    print("shuttle.proxy.rlwy.net:37929/railway")
    print("\n⚠️  This action is IRREVERSIBLE! ⚠️")
    
    response = input("\nType 'YES' to confirm: ")
    
    if response == 'YES':
        await drop_all_tables()
    else:
        print("\nOperation cancelled.")

if __name__ == "__main__":
    asyncio.run(main())