#!/usr/bin/env python3
"""
Fix position status.
"""

import asyncio
import asyncpg

async def fix_position():
    """Fix the position status."""
    
    database_url = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"
    
    position_id = 26256789
    
    print("FIXING POSITION STATUS")
    print("="*60)
    
    conn = await asyncpg.connect(database_url)
    
    try:
        # Update position status to ACTIVE and fix entry amount
        updated = await conn.fetchval(
            """
            UPDATE positions 
            SET status = 'ACTIVE',
                entry_amount_usdc = 49.98,
                updated_at = NOW()
            WHERE token_id = $1
            RETURNING token_id
            """,
            position_id
        )
        
        if updated:
            print(f"✅ Fixed position {updated}")
            print(f"  - Status: CLOSED → ACTIVE")
            print(f"  - Entry amount: 0.0 → 49.98 USDC")
        else:
            print(f"Position {position_id} not found")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_position())
