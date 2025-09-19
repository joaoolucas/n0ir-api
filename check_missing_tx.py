#!/usr/bin/env python3
"""Check why a position closed transaction is missing."""

import asyncio
import asyncpg

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def check_transaction():
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        tx_hash = "0x63f8cc21dd3ecf759a533a608836cb942c3a9d61178d6c7fe4f7fd824abb43ca"

        # Check if transaction exists
        query = """
        SELECT id, tx_hash, tx_type, event_data, created_at
        FROM transactions
        WHERE tx_hash = $1
        """
        tx = await conn.fetchrow(query, tx_hash)

        if tx:
            print(f"Transaction found:")
            print(f"  ID: {tx['id']}")
            print(f"  Type: {tx['tx_type']}")
            print(f"  Event data: {tx['event_data']}")
            print(f"  Created: {tx['created_at']}")
        else:
            print(f"Transaction {tx_hash} NOT found in database")

            # Check if there are any similar transactions from around the same time
            print("\nChecking recent POSITION_CLOSED transactions...")
            recent_query = """
            SELECT tx_hash, tx_type, event_data, created_at
            FROM transactions
            WHERE tx_type IN ('POSITION_CLOSED', 'POSITION_CREATED')
            AND created_at >= '2025-09-19 20:00:00'
            ORDER BY created_at DESC
            LIMIT 10
            """
            recent = await conn.fetch(recent_query)

            for r in recent:
                print(f"\n  {r['tx_hash'][:10]}... - {r['tx_type']} at {r['created_at']}")
                event_data = r['event_data']
                if event_data:
                    if isinstance(event_data, str):
                        import json
                        event_data = json.loads(event_data)
                    if 'nft_token_id' in event_data:
                        print(f"    NFT: {event_data.get('nft_token_id')}")
                    if 'pool' in event_data:
                        print(f"    Pool: {event_data.get('pool')}")

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
    print("Checking missing transaction...")
    print("=" * 60)
    await check_transaction()

if __name__ == "__main__":
    asyncio.run(main())