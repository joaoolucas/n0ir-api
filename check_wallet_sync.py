#!/usr/bin/env python3
"""Check which wallets are associated with the user."""

import asyncio
import asyncpg

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def check_wallets():
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        user_id = "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51"

        # Get user info
        query = """
        SELECT user_id, cdp_wallet_address, created_at
        FROM users
        WHERE user_id = $1
        """
        user = await conn.fetchrow(query, user_id)

        if user:
            print(f"User: {user['user_id']}")
            print(f"CDP Wallet: {user['cdp_wallet_address']}")
            print(f"Created: {user['created_at']}")

            # The transaction is from this address
            tx_from = "0x1278C1E48e3c9548A5D9F2b16dC27Ed311B0697C"
            print(f"\nTransaction from: {tx_from}")

            if user['cdp_wallet_address']:
                if user['cdp_wallet_address'].lower() == tx_from.lower():
                    print("✓ Transaction is from CDP wallet")
                else:
                    print("✗ Transaction is NOT from CDP wallet")
                    print(f"  CDP wallet: {user['cdp_wallet_address']}")
                    print(f"  TX from:    {tx_from}")

            # Check if tx_from belongs to another user
            print("\nChecking if tx_from wallet belongs to another user...")
            other_user_query = """
            SELECT user_id, cdp_wallet_address
            FROM users
            WHERE cdp_wallet_address = $1
            """
            other_user = await conn.fetchrow(other_user_query, tx_from)
            if other_user:
                print(f"✓ Found user for wallet {tx_from}:")
                print(f"  User: {other_user['user_id']}")
            else:
                print(f"✗ No user found with CDP wallet {tx_from}")

        return True

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if conn:
            await conn.close()

async def main():
    print("Checking wallet addresses...")
    print("=" * 60)
    await check_wallets()

if __name__ == "__main__":
    asyncio.run(main())