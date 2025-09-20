#!/usr/bin/env python3
"""Fix transactions with missing CDP wallet in event_data."""

import asyncio
import asyncpg
import json

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def fix_missing_cdp_wallets():
    """Update transactions with missing or empty CDP wallet addresses."""
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # First, get all users with their CDP wallets
        users_query = """
        SELECT user_id, cdp_wallet_address
        FROM users
        WHERE cdp_wallet_address IS NOT NULL
        """
        users = await conn.fetch(users_query)
        user_cdp_map = {user['user_id']: user['cdp_wallet_address'] for user in users}
        print(f"Found {len(user_cdp_map)} users with CDP wallets")

        # Find transactions with missing or empty CDP wallet
        find_query = """
        SELECT id, user_id, tx_type, event_data, position_id
        FROM transactions
        WHERE (
            event_data->>'cdp_wallet' = ''
            OR event_data->>'cdp_wallet' IS NULL
        )
        AND tx_type IN ('POSITION_CREATED', 'POSITION_CLOSED', 'STAKING')
        ORDER BY created_at DESC
        """

        transactions = await conn.fetch(find_query)
        print(f"Found {len(transactions)} transactions with missing CDP wallet")

        fixed_count = 0
        for tx in transactions:
            user_id = tx['user_id']
            if user_id in user_cdp_map:
                cdp_wallet = user_cdp_map[user_id]

                # Update event_data with CDP wallet
                update_query = """
                UPDATE transactions
                SET event_data = jsonb_set(event_data, '{cdp_wallet}', $1::jsonb)
                WHERE id = $2
                """

                await conn.execute(update_query, json.dumps(cdp_wallet), tx['id'])
                fixed_count += 1

                print(f"✅ Fixed tx {str(tx['id'])[:8]}... ({tx['tx_type']}) - added CDP wallet {cdp_wallet}")

        print(f"\n🎉 Fixed {fixed_count} transactions")

        # Now fix position_id and pool_name for these transactions
        print("\n📋 Attempting to fix position_id and pool_name...")

        # For POSITION_CREATED and POSITION_CLOSED, try to match with positions
        position_fix_query = """
        SELECT t.id, t.user_id, t.tx_type, t.event_data, t.position_id, t.tx_hash,
               p.token_id, p.pool_address, p.pool_name
        FROM transactions t
        LEFT JOIN positions p ON p.user_id = t.user_id
        WHERE t.tx_type IN ('POSITION_CREATED', 'POSITION_CLOSED', 'STAKING')
        AND (t.position_id IS NULL OR (t.event_data->>'pool_name') IS NULL)
        ORDER BY t.created_at DESC
        """

        tx_to_fix = await conn.fetch(position_fix_query)
        print(f"Found {len(tx_to_fix)} transactions that might need position data")

        # For now, just report what we found - manual matching would be needed
        for tx in tx_to_fix[:5]:  # Show first 5
            print(f"\nTransaction {str(tx['id'])[:8]}...:")
            print(f"  Type: {tx['tx_type']}")
            print(f"  User: {tx['user_id']}")
            print(f"  Position ID: {tx['position_id']}")
            print(f"  TX Hash: {tx['tx_hash'][:10]}..." if tx['tx_hash'] else "  TX Hash: None")

        print("\n💡 To fully fix position_id and pool_name, transactions need to be re-synced from blockchain")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_missing_cdp_wallets())