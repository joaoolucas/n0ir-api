#!/usr/bin/env python3
"""
Check and fix pool name issue.
"""

import asyncio
import asyncpg

async def check_and_fix():
    """Check what's wrong and fix it."""
    
    database_url = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"
    
    position_id = 26256789
    
    print("CHECKING AND FIXING POOL NAME")
    print("="*60)
    
    conn = await asyncpg.connect(database_url)
    
    try:
        # First check current values
        position = await conn.fetchrow(
            """
            SELECT token_id, pool_name, pool_address, token0_address, token1_address
            FROM positions 
            WHERE token_id = $1
            """,
            position_id
        )
        
        if position:
            print(f"Current data:")
            print(f"  Token ID: {position['token_id']}")
            print(f"  Pool name: '{position['pool_name']}'")
            print(f"  Pool address: {position['pool_address']}")
            print(f"  Token0: {position['token0_address']}")
            print(f"  Token1: {position['token1_address']}")
            
            # The issue might be that token0 and token1 are swapped
            # WETH should be token0: 0x4200000000000000000000000000000000000006
            # USDC should be token1: 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
            
            print(f"\nFixing pool name AND token order...")
            
            # Update pool name and ensure correct token order
            updated = await conn.execute(
                """
                UPDATE positions 
                SET pool_name = 'WETH/USDC',
                    token0_address = '0x4200000000000000000000000000000000000006',
                    token1_address = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',
                    updated_at = NOW()
                WHERE token_id = $1
                """,
                position_id
            )
            
            print(f"✅ Updated position")
            
            # Verify the fix
            fixed = await conn.fetchrow(
                """
                SELECT pool_name, token0_address, token1_address
                FROM positions 
                WHERE token_id = $1
                """,
                position_id
            )
            
            print(f"\nAfter fix:")
            print(f"  Pool name: '{fixed['pool_name']}'")
            print(f"  Token0 (WETH): {fixed['token0_address']}")
            print(f"  Token1 (USDC): {fixed['token1_address']}")
            
        else:
            print(f"Position {position_id} not found")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_and_fix())
