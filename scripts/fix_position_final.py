#!/usr/bin/env python3
"""
Final fixes for position.
"""

import asyncio
import asyncpg

async def fix_position_final():
    """Fix the position final issues."""
    
    database_url = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"
    
    position_id = 26256789
    
    print("FINAL POSITION FIXES")
    print("="*60)
    
    conn = await asyncpg.connect(database_url)
    
    try:
        # Fix exit_date, realized_pnl, and pool_name
        updated = await conn.fetchval(
            """
            UPDATE positions 
            SET exit_date = NULL,
                realized_pnl_usdc = 0.0,
                pool_name = 'WETH/USDC',
                updated_at = NOW()
            WHERE token_id = $1
            RETURNING token_id
            """,
            position_id
        )
        
        if updated:
            print(f"✅ Fixed position {updated}")
            print(f"  - exit_date: → NULL (position is ACTIVE)")
            print(f"  - realized_pnl_usdc: → 0.0 (not closed yet)")
            print(f"  - pool_name: → WETH/USDC")
            
            # Verify the update
            position = await conn.fetchrow(
                """
                SELECT pool_name, exit_date, realized_pnl_usdc, status
                FROM positions 
                WHERE token_id = $1
                """,
                position_id
            )
            
            print(f"\nVerification:")
            print(f"  - Pool name: {position['pool_name']}")
            print(f"  - Exit date: {position['exit_date']}")
            print(f"  - Realized PnL: {position['realized_pnl_usdc']} USDC")
            print(f"  - Status: {position['status']}")
        else:
            print(f"Position {position_id} not found")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_position_final())
