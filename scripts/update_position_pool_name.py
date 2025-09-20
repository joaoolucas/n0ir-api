#!/usr/bin/env python3
"""Update pool_name for position."""

import asyncio
import asyncpg

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def update_position_pool_name():
    """Update pool_name for the position."""
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # Update position 26216334 with pool_name
        position_id = 26216334
        pool_name = "cbBTC/USDC"

        update_query = """
        UPDATE positions
        SET pool_name = $1
        WHERE token_id = $2
        """
        await conn.execute(update_query, pool_name, position_id)
        print(f"✅ Updated position {position_id} with pool_name={pool_name}")

        # Also update STAKING transaction
        tx_hash = "0xc033aabc8da21b78e94cc24b4304e6400ebc50ce47c32dbcb20d1bf858bcbf62"
        query = """
        SELECT id, event_data
        FROM transactions
        WHERE tx_hash = $1
        """
        tx = await conn.fetchrow(query, tx_hash)

        if tx:
            import json
            event_data = tx['event_data']
            if isinstance(event_data, str):
                event_data = json.loads(event_data)

            event_data['pool_name'] = pool_name

            update_tx = """
            UPDATE transactions
            SET event_data = $1
            WHERE id = $2
            """
            await conn.execute(update_tx, json.dumps(event_data), tx['id'])
            print(f"✅ Updated STAKING transaction with pool_name={pool_name}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(update_position_pool_name())