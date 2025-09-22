#!/usr/bin/env python3
"""Check specific transaction details."""

import asyncio
import asyncpg
import json

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def check_transaction():
    """Check transaction details."""
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # Get the transaction
        query = """
        SELECT id, tx_hash, tx_type, event_data, position_id, created_at, confirmed_at, block_timestamp
        FROM transactions
        WHERE id = 'd8348383-f4b4-45f0-9630-a7369cc47201'
        """
        tx = await conn.fetchrow(query)

        if tx:
            print(f"Transaction ID: {tx['id']}")
            print(f"TX Hash: {tx['tx_hash']}")
            print(f"Type: {tx['tx_type']}")
            print(f"Position ID: {tx['position_id']}")
            print(f"Created at: {tx['created_at']}")
            print(f"Confirmed at: {tx['confirmed_at']}")
            print(f"Block timestamp: {tx['block_timestamp']}")

            event_data = tx['event_data']
            if isinstance(event_data, str):
                event_data = json.loads(event_data)

            print(f"\nEvent Data:")
            print(json.dumps(event_data, indent=2))

            # Check the pool address specifically
            pool = event_data.get('pool')
            print(f"\nPool address from event_data: {pool}")

            # If it's a POSITION_CLOSED, check the related position
            if tx['tx_type'] == 'POSITION_CLOSED' and tx['position_id']:
                position_query = """
                SELECT token_id, pool_address, pool_name
                FROM positions
                WHERE token_id = $1
                """
                position = await conn.fetchrow(position_query, tx['position_id'])
                if position:
                    print(f"\nRelated Position:")
                    print(f"  Token ID: {position['token_id']}")
                    print(f"  Pool Address: {position['pool_address']}")
                    print(f"  Pool Name: {position['pool_name']}")
        else:
            print("Transaction not found")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(check_transaction())