#!/usr/bin/env python3
"""Check actual columns in staging positions table."""

import psycopg2

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@centerbeam.proxy.rlwy.net:24644/railway?sslmode=disable"

def check_columns():
    """Check what columns actually exist in positions table."""
    conn = psycopg2.connect(DATABASE_URL)
    
    try:
        with conn.cursor() as cur:
            # Get column information
            query = """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'positions'
            ORDER BY ordinal_position;
            """
            
            cur.execute(query)
            rows = cur.fetchall()
            
            print("Columns in positions table:")
            print("-" * 60)
            column_names = []
            for row in rows:
                column_names.append(row[0])
                print(f"{row[0]:<30} {row[1]:<20} nullable={row[2]}")
            
            # Check specifically for PnL columns
            print("\n" + "=" * 60)
            print("PnL-related columns:")
            print("-" * 60)
            pnl_columns = []
            for name in column_names:
                if 'pnl' in name.lower():
                    pnl_columns.append(name)
                    print(f"  - {name}")
            
            if not pnl_columns:
                print("  No PnL columns found!")
            
            print("\n" + "=" * 60)
            print("Summary:")
            print("-" * 60)
            
            # Check for expected old column names
            old_columns = ['unrealized_pnl_usd', 'unrealized_pnl_pct', 'realized_pnl_usd', 'realized_pnl_pct']
            new_columns = ['pnl_usdc', 'pnl_pct', 'realized_pnl_usdc']
            
            existing_old = [col for col in old_columns if col in column_names]
            existing_new = [col for col in new_columns if col in column_names]
            missing_old = [col for col in old_columns if col not in column_names]
            
            if existing_old:
                print(f"✗ OLD columns still exist: {', '.join(existing_old)}")
            else:
                print(f"✓ OLD columns have been removed: {', '.join(missing_old)}")
                
            if existing_new:
                print(f"✓ NEW columns exist: {', '.join(existing_new)}")
            else:
                print(f"✗ NEW columns are missing: {', '.join([c for c in new_columns if c not in column_names])}")
        
    finally:
        conn.close()

if __name__ == "__main__":
    check_columns()