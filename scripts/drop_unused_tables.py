#!/usr/bin/env python3
"""Drop unused tables from the staging database to keep only 3 core tables."""

import psycopg2
from psycopg2 import sql
import sys

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

# Tables to drop (non-core tables)
TABLES_TO_DROP = [
    'daily_metrics',
    'pool_metrics', 
    'executor_stats',
    'blockchain_sync',
    'wallet_transactions',
    'liquidity_events',
    'strategy_decisions'
]

# Core tables to keep
CORE_TABLES = ['users', 'positions', 'transactions']

def main():
    try:
        # Connect to database
        print(f"Connecting to staging database...")
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # List all current tables
        print("\nCurrent tables in database:")
        cur.execute("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public' 
            ORDER BY tablename
        """)
        current_tables = [row[0] for row in cur.fetchall()]
        for table in current_tables:
            status = "✅ KEEP" if table in CORE_TABLES else "❌ DROP" if table in TABLES_TO_DROP else "⚠️  OTHER"
            print(f"  {status} - {table}")
        
        # Drop unused tables
        print(f"\nDropping {len(TABLES_TO_DROP)} non-core tables...")
        dropped = []
        skipped = []
        
        for table in TABLES_TO_DROP:
            if table in current_tables:
                try:
                    print(f"  Dropping {table}...")
                    cur.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(sql.Identifier(table)))
                    dropped.append(table)
                    print(f"    ✅ Dropped {table}")
                except Exception as e:
                    print(f"    ❌ Error dropping {table}: {e}")
            else:
                skipped.append(table)
                print(f"  ⏭️  Skipped {table} (doesn't exist)")
        
        # Commit changes
        conn.commit()
        
        # List remaining tables
        print("\nRemaining tables after cleanup:")
        cur.execute("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public' 
            ORDER BY tablename
        """)
        remaining_tables = [row[0] for row in cur.fetchall()]
        for table in remaining_tables:
            status = "✅" if table in CORE_TABLES else "⚠️"
            print(f"  {status} {table}")
        
        # Summary
        print("\n" + "="*50)
        print("SUMMARY:")
        print(f"  Tables dropped: {len(dropped)}")
        if dropped:
            for t in dropped:
                print(f"    - {t}")
        print(f"  Tables skipped: {len(skipped)}")
        if skipped:
            for t in skipped:
                print(f"    - {t}")
        print(f"  Core tables remaining: {len([t for t in remaining_tables if t in CORE_TABLES])}/3")
        print(f"  Total tables remaining: {len(remaining_tables)}")
        
        # Close connection
        cur.close()
        conn.close()
        
        print("\n✅ Database cleanup completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()