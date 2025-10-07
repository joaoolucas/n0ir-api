#!/usr/bin/env python3
"""Manually update pool_name for the POSITION_CLOSED transaction."""

import asyncio
import asyncpg
import json

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def fix_pool_name():
    """Fix pool_name for the specific transaction."""
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # Get the transaction
        tx_hash = "0xf362a1b777cae6f2584a3909dce51b75d51e4c2e5585dd2eb73fa3e1df2e9087"
        query = """
        SELECT id, event_data, position_id
        FROM transactions
        WHERE tx_hash = $1
        """
        tx = await conn.fetchrow(query, tx_hash)

        if not tx:
            print(f"Transaction {tx_hash} not found")
            return

        print(f"Found transaction with position_id={tx['position_id']}")

        # Get the position to find pool_name
        if tx['position_id']:
            position_query = """
            SELECT pool_name, pool_address
            FROM positions
            WHERE token_id = $1
            """
            position = await conn.fetchrow(position_query, tx['position_id'])

            if position:
                pool_name = position['pool_name']
                pool_address = position['pool_address']
                print(f"Found position with pool_name={pool_name}, pool_address={pool_address}")

                # Parse event_data
                event_data = tx['event_data']
                if isinstance(event_data, str):
                    event_data = json.loads(event_data)

                # Update event_data with pool_name
                event_data['pool_name'] = pool_name if pool_name else "cbBTC/USDC"  # Use the known pool name
                if pool_address and not event_data.get('pool'):
                    event_data['pool'] = pool_address

                # Update the transaction
                update_query = """
                UPDATE transactions
                SET event_data = $1
                WHERE id = $2
                """
                await conn.execute(update_query, json.dumps(event_data), tx['id'])
                print(f"✅ Updated transaction with pool_name={event_data['pool_name']}")
            else:
                print(f"Position {tx['position_id']} not found")

                # Update with known pool name anyway
                event_data = tx['event_data']
                if isinstance(event_data, str):
                    event_data = json.loads(event_data)

                # We know this is cbBTC/USDC pool from the pool address
                event_data['pool_name'] = "cbBTC/USDC"

                # Update the transaction
                update_query = """
                UPDATE transactions
                SET event_data = $1
                WHERE id = $2
                """
                await conn.execute(update_query, json.dumps(event_data), tx['id'])
                print(f"✅ Updated transaction with pool_name=cbBTC/USDC")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_pool_name())