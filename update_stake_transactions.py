#!/usr/bin/env python3
"""Update existing transactions to STAKE type based on transaction hash."""

import asyncio
import asyncpg
import json

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

# Known stake transaction hash from the user
STAKE_TX_HASH = "0xc033aabc8da21b78e94cc24b4304e6400ebc50ce47c32dbcb20d1bf858bcbf62"

async def update_stake_transactions():
    """Find and update transactions that should be STAKE type."""
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # First, find the transaction
        query = """
        SELECT id, tx_hash, tx_type, event_data
        FROM transactions
        WHERE tx_hash = $1
        """
        tx = await conn.fetchrow(query, STAKE_TX_HASH)

        if not tx:
            print(f"Transaction {STAKE_TX_HASH} not found")

            # Let's search for it without the 0x prefix or case-insensitive
            alt_query = """
            SELECT id, tx_hash, tx_type, event_data
            FROM transactions
            WHERE LOWER(tx_hash) = LOWER($1) OR LOWER(tx_hash) = LOWER($2)
            """
            tx = await conn.fetchrow(alt_query, STAKE_TX_HASH, STAKE_TX_HASH[2:])

            if not tx:
                print("Transaction still not found. Checking all transactions for the user...")

                # List all transactions for the user
                user_query = """
                SELECT id, tx_hash, tx_type, event_data
                FROM transactions
                WHERE user_id = '0xAC65e18F7f4e5eDEA297b9E5433C153f1d9a7764'
                ORDER BY created_at DESC
                LIMIT 20
                """
                txs = await conn.fetch(user_query)
                print(f"\nFound {len(txs)} recent transactions for the user:")
                for t in txs:
                    print(f"  - {t['tx_hash'][:10]}... Type: {t['tx_type']}")
                return

        print(f"\nFound transaction:")
        print(f"  ID: {tx['id']}")
        print(f"  Hash: {tx['tx_hash']}")
        print(f"  Current Type: {tx['tx_type']}")

        # Parse event_data
        event_data = tx['event_data']
        if isinstance(event_data, str):
            event_data = json.loads(event_data)

        print(f"  Event Data: {json.dumps(event_data, indent=2)}")

        # Check if this looks like a stake transaction
        # It should have an NFT token ID and possibly be marked as STAKING
        if tx['tx_type'] in ['STAKING', 'UNKNOWN'] or 'nft_token_id' in event_data:
            print(f"\n✅ This appears to be a stake transaction")

            # Update to STAKE type
            update_query = """
            UPDATE transactions
            SET tx_type = 'STAKE',
                event_data = event_data || '{"transaction_type": "STAKE"}'::jsonb
            WHERE id = $1
            """
            await conn.execute(update_query, tx['id'])

            print(f"✅ Updated transaction to STAKE type")

            # Verify the update
            verify = await conn.fetchrow("SELECT tx_type FROM transactions WHERE id = $1", tx['id'])
            print(f"  Verified type: {verify['tx_type']}")
        else:
            print(f"\n⚠️  Transaction type is {tx['tx_type']}, not updating")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(update_stake_transactions())