#!/usr/bin/env python3
"""
Check position in database.
"""

import asyncio
import asyncpg

async def check_position():
    """Check the position."""
    
    database_url = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"
    
    position_id = 26256789
    user_id = '0xAC65e18F7f4e5eDEA297b9E5433C153f1d9a7764'
    
    print("CHECKING POSITION IN DATABASE")
    print("="*60)
    
    conn = await asyncpg.connect(database_url)
    
    try:
        # Check position details
        position = await conn.fetchrow(
            """
            SELECT token_id, user_id, pool_address, status, staked, 
                   entry_amount_usdc, current_value_usdc, created_at
            FROM positions 
            WHERE token_id = $1
            """,
            position_id
        )
        
        if position:
            print(f"Position found:")
            print(f"  Token ID: {position['token_id']}")
            print(f"  User ID: {position['user_id']}")
            print(f"  Pool: {position['pool_address']}")
            print(f"  Status: {position['status']}")
            print(f"  Staked: {position['staked']}")
            print(f"  Entry Amount: {position['entry_amount_usdc']}")
            print(f"  Current Value: {position['current_value_usdc']}")
            print(f"  Created: {position['created_at']}")
            
            # Check if user_id matches
            if position['user_id'].lower() != user_id.lower():
                print(f"\n❌ USER ID MISMATCH!")
                print(f"  Expected: {user_id}")
                print(f"  Actual: {position['user_id']}")
        else:
            print(f"Position {position_id} not found")
        
        # Check what the API query would return
        print(f"\n\nChecking API query for user {user_id}:")
        api_result = await conn.fetch(
            """
            SELECT token_id, user_id, status
            FROM positions 
            WHERE user_id = $1 AND status = 'ACTIVE'
            """,
            user_id
        )
        
        print(f"API would return {len(api_result)} positions")
        for row in api_result:
            print(f"  - Position {row['token_id']}, user {row['user_id']}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_position())
