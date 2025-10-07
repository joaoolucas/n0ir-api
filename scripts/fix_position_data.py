#!/usr/bin/env python3
"""
Fix pool name and liquidity for position.
"""

import asyncio
import asyncpg

async def fix_position_data():
    """Fix the position data."""
    
    database_url = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"
    
    position_id = 26256789
    
    print("FIXING POSITION DATA")
    print("="*60)
    
    conn = await asyncpg.connect(database_url)
    
    try:
        # Update pool name and liquidity
        updated = await conn.fetchval(
            """
            UPDATE positions 
            SET pool_name = 'WETH/USDC',
                liquidity = '49961398751505',
                updated_at = NOW()
            WHERE token_id = $1
            RETURNING token_id
            """,
            position_id
        )
        
        if updated:
            print(f"✅ Fixed position {updated}")
            print(f"  - Pool name: → WETH/USDC")
            print(f"  - Liquidity: 0 → 49961398751505")
            
            # Verify the update
            position = await conn.fetchrow(
                """
                SELECT pool_name, liquidity, status, entry_amount_usdc
                FROM positions 
                WHERE token_id = $1
                """,
                position_id
            )
            
            print(f"\nVerification:")
            print(f"  - Pool name: {position['pool_name']}")
            print(f"  - Liquidity: {position['liquidity']}")
            print(f"  - Status: {position['status']}")
            print(f"  - Entry amount: {position['entry_amount_usdc']} USDC")
        else:
            print(f"Position {position_id} not found")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_position_data())
