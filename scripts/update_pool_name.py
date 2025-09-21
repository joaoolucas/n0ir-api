#!/usr/bin/env python3
"""
Update pool name to WETH/USDC.
"""

import asyncio
import asyncpg

async def update_pool_name():
    """Update the pool name."""
    
    database_url = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"
    
    position_id = 26256789
    
    print("UPDATING POOL NAME")
    print("="*60)
    
    conn = await asyncpg.connect(database_url)
    
    try:
        # Update pool name
        updated = await conn.fetchval(
            """
            UPDATE positions 
            SET pool_name = 'WETH/USDC',
                updated_at = NOW()
            WHERE token_id = $1
            RETURNING token_id
            """,
            position_id
        )
        
        if updated:
            print(f"✅ Updated position {updated}")
            print(f"  Pool name: → WETH/USDC")
            
            # Verify
            pool_name = await conn.fetchval(
                "SELECT pool_name FROM positions WHERE token_id = $1",
                position_id
            )
            print(f"\nVerified: Pool name is now '{pool_name}'")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(update_pool_name())
