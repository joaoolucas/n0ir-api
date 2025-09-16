#!/usr/bin/env python3
"""Fix WITHDRAWAL -> WITHDRAW in transactions table."""

import psycopg2
from psycopg2 import sql

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

def main():
    try:
        # Connect to database
        print(f"Connecting to staging database...")
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # Check current transaction types
        print("\nChecking current transaction types...")
        cur.execute("""
            SELECT DISTINCT tx_type, COUNT(*) 
            FROM transactions 
            GROUP BY tx_type 
            ORDER BY tx_type
        """)
        types = cur.fetchall()
        print("Current transaction types:")
        for tx_type, count in types:
            print(f"  - {tx_type}: {count} records")
        
        # Update WITHDRAWAL to WITHDRAW
        print("\nUpdating WITHDRAWAL to WITHDRAW...")
        cur.execute("""
            UPDATE transactions 
            SET tx_type = 'WITHDRAW' 
            WHERE tx_type = 'WITHDRAWAL'
        """)
        updated = cur.rowcount
        print(f"  Updated {updated} records")
        
        # Commit changes
        conn.commit()
        
        # Verify the update
        print("\nVerifying transaction types after update...")
        cur.execute("""
            SELECT DISTINCT tx_type, COUNT(*) 
            FROM transactions 
            GROUP BY tx_type 
            ORDER BY tx_type
        """)
        types = cur.fetchall()
        print("Updated transaction types:")
        for tx_type, count in types:
            print(f"  - {tx_type}: {count} records")
        
        # Close connection
        cur.close()
        conn.close()
        
        print("\n✅ Database fix completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        exit(1)

if __name__ == "__main__":
    main()