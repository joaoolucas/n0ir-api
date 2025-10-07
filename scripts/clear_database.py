#!/usr/bin/env python3
"""Clear all data from PostgreSQL database."""

import asyncio
import asyncpg
import sys

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def clear_database():
    """Clear all data from PostgreSQL database."""
    conn = None
    try:
        # Connect to database
        print("Connecting to PostgreSQL database...")
        conn = await asyncpg.connect(DATABASE_URL)
        print("✓ Connected to database successfully")

        # Get list of tables (excluding system tables)
        tables_query = """
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY tablename;
        """
        tables = await conn.fetch(tables_query)

        if not tables:
            print("No tables found in database")
            return True

        print(f"\nFound {len(tables)} tables:")
        for table in tables:
            # Get row count for each table
            count_query = f"SELECT COUNT(*) FROM {table['tablename']}"
            count = await conn.fetchval(count_query)
            print(f"  - {table['tablename']}: {count} rows")

        # Confirm before clearing
        print(f"\n⚠️  WARNING: This will delete ALL data from ALL {len(tables)} tables!")
        print("This action cannot be undone!")
        response = input("Are you sure you want to continue? (yes/no): ")

        if response.lower() != 'yes':
            print("Aborted")
            return False

        print("\nClearing database...")

        # Disable foreign key checks temporarily
        await conn.execute("SET session_replication_role = 'replica';")

        # Truncate all tables with CASCADE to handle foreign keys
        for table in tables:
            table_name = table['tablename']
            try:
                await conn.execute(f"TRUNCATE TABLE {table_name} CASCADE;")
                print(f"  ✓ Cleared table: {table_name}")
            except Exception as e:
                print(f"  ✗ Failed to clear table {table_name}: {e}")

        # Re-enable foreign key checks
        await conn.execute("SET session_replication_role = 'origin';")

        # Reset sequences
        sequences_query = """
        SELECT sequence_name
        FROM information_schema.sequences
        WHERE sequence_schema = 'public';
        """
        sequences = await conn.fetch(sequences_query)

        for seq in sequences:
            try:
                await conn.execute(f"ALTER SEQUENCE {seq['sequence_name']} RESTART WITH 1;")
                print(f"  ✓ Reset sequence: {seq['sequence_name']}")
            except Exception as e:
                print(f"  ✗ Failed to reset sequence {seq['sequence_name']}: {e}")

        print("\n✅ Database cleared successfully!")

        # Verify by checking row counts again
        print("\nVerifying database is empty:")
        for table in tables:
            count_query = f"SELECT COUNT(*) FROM {table['tablename']}"
            count = await conn.fetchval(count_query)
            if count > 0:
                print(f"  ✗ {table['tablename']}: {count} rows remaining")
            else:
                print(f"  ✓ {table['tablename']}: empty")

        return True

    except asyncpg.PostgresConnectionError as e:
        print(f"❌ Failed to connect to database: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if conn:
            await conn.close()

async def main():
    success = await clear_database()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())