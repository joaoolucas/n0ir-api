#!/usr/bin/env python3
"""Fix the user balance calculation issue."""

import asyncio
import asyncpg
from decimal import Decimal

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def fix_balance():
    conn = await asyncpg.connect(DATABASE_URL, ssl='require')
    
    try:
        # Get user data
        user = await conn.fetchrow("""
            SELECT user_id, cdp_wallet_address, usdc_balance,
                   total_deposits_usdc, total_withdrawals_usdc
            FROM users
            WHERE cdp_wallet_address IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 1
        """)
        
        if user:
            print(f"👤 User: {user['user_id']}")
            print(f"💳 CDP Wallet: {user['cdp_wallet_address']}")
            print(f"\nCurrent State:")
            print(f"  Balance: {user['usdc_balance']} USDC ❌")
            print(f"  Total Deposits: {user['total_deposits_usdc']} USDC")
            print(f"  Total Withdrawals: {user['total_withdrawals_usdc']} USDC")
            
            # Calculate correct balance
            correct_balance = Decimal(str(user['total_deposits_usdc'])) - Decimal(str(user['total_withdrawals_usdc']))
            
            print(f"\n📊 Correct Calculation:")
            print(f"  {user['total_deposits_usdc']} - {user['total_withdrawals_usdc']} = {correct_balance} USDC")
            
            # Update the balance
            await conn.execute("""
                UPDATE users
                SET usdc_balance = $1
                WHERE user_id = $2
            """, correct_balance, user['user_id'])
            
            print(f"\n✅ Balance updated from {user['usdc_balance']} to {correct_balance} USDC")
            
            # Verify the update
            updated = await conn.fetchrow("""
                SELECT usdc_balance FROM users WHERE user_id = $1
            """, user['user_id'])
            
            print(f"\n✅ Verified new balance: {updated['usdc_balance']} USDC")
            
    finally:
        await conn.close()

if __name__ == "__main__":
    print("🔧 Fixing user balance calculation...\n")
    asyncio.run(fix_balance())