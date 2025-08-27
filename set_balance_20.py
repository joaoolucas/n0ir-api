#!/usr/bin/env python3
"""Set the user balance to exactly 20 USDC."""

import asyncio
import asyncpg
from decimal import Decimal

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def set_balance():
    conn = await asyncpg.connect(DATABASE_URL, ssl='require')
    
    try:
        # Get user data
        user = await conn.fetchrow("""
            SELECT user_id, cdp_wallet_address, usdc_balance
            FROM users
            WHERE cdp_wallet_address IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 1
        """)
        
        if user:
            print(f"👤 User: {user['user_id']}")
            print(f"💳 CDP Wallet: {user['cdp_wallet_address']}")
            print(f"\nCurrent Balance: {user['usdc_balance']} USDC")
            
            # Set balance to exactly 20
            new_balance = Decimal('20.000000')
            
            # Update the balance
            await conn.execute("""
                UPDATE users
                SET usdc_balance = $1,
                    updated_at = NOW()
                WHERE user_id = $2
            """, new_balance, user['user_id'])
            
            print(f"✅ Balance updated to exactly {new_balance} USDC")
            
            # Verify the update
            updated = await conn.fetchrow("""
                SELECT usdc_balance, updated_at FROM users WHERE user_id = $1
            """, user['user_id'])
            
            print(f"\n✅ Verified:")
            print(f"   New balance: {updated['usdc_balance']} USDC")
            print(f"   Updated at: {updated['updated_at']}")
            
    finally:
        await conn.close()

if __name__ == "__main__":
    print("💰 Setting user balance to exactly 20 USDC...\n")
    asyncio.run(set_balance())