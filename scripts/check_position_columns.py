#!/usr/bin/env python3
"""Check actual columns in positions table."""

import asyncio
import os
from dotenv import load_dotenv
import asyncpg

load_dotenv()

async def check_columns():
    """Check what columns actually exist in positions table."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not set")
        return
    
    conn = await asyncpg.connect(database_url)
    
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
        for row in rows:
            if 'pnl' in row['column_name'].lower():
                print(f"  - {row['column_name']}")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_columns())