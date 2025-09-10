#!/usr/bin/env python3
"""Fix position status to use uppercase values for consistency."""

import asyncio
import asyncpg

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def fix_position_status():
    conn = await asyncpg.connect(DATABASE_URL, ssl='require')
    
    try:
        print("🔧 Fixing position status to uppercase...")
        
        # Check current status values
        print("\n📊 Current status distribution:")
        rows = await conn.fetch("""
            SELECT status, COUNT(*) as count
            FROM positions
            GROUP BY status
            ORDER BY status
        """)
        
        for row in rows:
            print(f"  {row['status']}: {row['count']} positions")
        
        # Fix lowercase 'active' to 'ACTIVE'
        result = await conn.execute("""
            UPDATE positions 
            SET status = 'ACTIVE'
            WHERE status = 'active'
        """)
        count = int(result.split()[-1]) if result else 0
        
        if count:
            print(f"\n✅ Updated {count} positions from 'active' to 'ACTIVE'")
        
        # Fix lowercase 'closed' to 'CLOSED'
        result = await conn.execute("""
            UPDATE positions 
            SET status = 'CLOSED'
            WHERE status = 'closed'
        """)
        count = int(result.split()[-1]) if result else 0
        
        if count:
            print(f"✅ Updated {count} positions from 'closed' to 'CLOSED'")
        
        # Fix lowercase 'liquidated' to 'LIQUIDATED'
        result = await conn.execute("""
            UPDATE positions 
            SET status = 'LIQUIDATED'
            WHERE status = 'liquidated'
        """)
        count = int(result.split()[-1]) if result else 0
        
        if count:
            print(f"✅ Updated {count} positions from 'liquidated' to 'LIQUIDATED'")
        
        # Verify the fix
        print("\n📊 Status distribution after fix:")
        rows = await conn.fetch("""
            SELECT status, COUNT(*) as count
            FROM positions
            GROUP BY status
            ORDER BY status
        """)
        
        for row in rows:
            print(f"  {row['status']}: {row['count']} positions")
        
        # Check for any non-uppercase values
        bad_rows = await conn.fetch("""
            SELECT token_id, status
            FROM positions
            WHERE status != UPPER(status)
        """)
        
        if bad_rows:
            print(f"\n⚠️  Warning: {len(bad_rows)} positions still have non-uppercase status:")
            for row in bad_rows:
                print(f"  Token {row['token_id']}: {row['status']}")
        else:
            print("\n✅ All position statuses are now uppercase!")
            
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_position_status())