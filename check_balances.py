#!/usr/bin/env python3
"""Check wallet balances in staging database."""

import asyncio
import asyncpg
from urllib.parse import urlparse

# Database URL from Railway staging
DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"


async def check_balances():
    """Check wallet balances."""
    
    # Parse database URL
    parsed = urlparse(DATABASE_URL)
    
    # Connect to database
    conn = await asyncpg.connect(
        host=parsed.hostname,
        port=parsed.port,
        user=parsed.username,
        password=parsed.password,
        database=parsed.path.lstrip('/'),
        ssl='require'
    )
    
    print("Connected to staging database")
    
    try:
        # Check users with balances
        users_with_balances = await conn.fetch("""
            SELECT 
                user_id,
                cdp_wallet_address,
                usdc_balance,
                total_deposits_usdc,
                total_withdrawals_usdc,
                last_deposit_block,
                last_withdrawal_block,
                last_scanned_block
            FROM users 
            WHERE cdp_wallet_address IS NOT NULL
            ORDER BY usdc_balance DESC
            LIMIT 10
        """)
        
        print("\n=== Users with CDP Wallets ===")
        for user in users_with_balances:
            print(f"\nUser: {user['user_id']}")
            print(f"  CDP Wallet: {user['cdp_wallet_address']}")
            print(f"  Balance: {user['usdc_balance']} USDC")
            print(f"  Total Deposits: {user['total_deposits_usdc']} USDC")
            print(f"  Total Withdrawals: {user['total_withdrawals_usdc']} USDC")
            print(f"  Last Deposit Block: {user['last_deposit_block']}")
            print(f"  Last Withdrawal Block: {user['last_withdrawal_block']}")
            print(f"  Last Scanned Block: {user['last_scanned_block']}")
        
        # Check recent transactions
        recent_txs = await conn.fetch("""
            SELECT 
                user_id,
                tx_type,
                event_data->>'amount_usdc' as amount,
                block_number,
                created_at
            FROM transactions 
            WHERE tx_type IN ('DEPOSIT', 'WITHDRAWAL')
            ORDER BY created_at DESC
            LIMIT 10
        """)
        
        print("\n=== Recent Deposit/Withdrawal Transactions ===")
        for tx in recent_txs:
            print(f"  {tx['tx_type']}: {tx['amount']} USDC by {tx['user_id']} at block {tx['block_number']}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise
    finally:
        await conn.close()
        print("\nDisconnected from database")


if __name__ == "__main__":
    print("🔍 Checking wallet balances in Railway staging database")
    asyncio.run(check_balances())