#!/usr/bin/env python3
"""Check actual columns in staging positions table."""

import asyncio
import asyncpg

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@postgres.railway.internal:5432/railway"

# Convert internal URL to external for local connection
DATABASE_URL = DATABASE_URL.replace("postgres.railway.internal", "centerbeam.proxy.rlwy.net").replace("5432", "24644")

async def check_columns():
    """Check what columns actually exist in positions table."""
    conn = await asyncpg.connect(DATABASE_URL, ssl='prefer')
    
    try:
        # Get column information
        query = """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'positions'
        ORDER BY ordinal_position;
        """
        
        rows = await conn.fetch(query)
        
        print("Columns in positions table:")
        print("-" * 60)
        for row in rows:
            print(f"{row['column_name']:<30} {row['data_type']:<20} nullable={row['is_nullable']}")
        
        # Check specifically for PnL columns
        print("\n" + "=" * 60)
        print("PnL-related columns:")
        print("-" * 60)
        pnl_columns = []
        for row in rows:
            if 'pnl' in row['column_name'].lower():
                pnl_columns.append(row['column_name'])
                print(f"  - {row['column_name']}")
        
        print("\n" + "=" * 60)
        print("Summary:")
        print("-" * 60)
        
        # Check for expected old column names
        old_columns = ['unrealized_pnl_usd', 'unrealized_pnl_pct', 'realized_pnl_usd', 'realized_pnl_pct']
        new_columns = ['pnl_usdc', 'pnl_pct', 'realized_pnl_usdc']
        
        existing_old = [col for col in old_columns if col in [row['column_name'] for row in rows]]
        existing_new = [col for col in new_columns if col in [row['column_name'] for row in rows]]
        
        if existing_old:
            print(f"✗ OLD columns still exist: {', '.join(existing_old)}")
        else:
            print("✓ OLD columns have been removed")
            
        if existing_new:
            print(f"✓ NEW columns exist: {', '.join(existing_new)}")
        else:
            print("✗ NEW columns are missing")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_columns())