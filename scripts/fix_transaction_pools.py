#!/usr/bin/env python3
"""Fix pool addresses for specific transactions."""

import asyncio
import asyncpg
import json

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def fix_transaction_pools():
    """Fix pool addresses for specific transactions."""
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # 1. Fix transaction c80e44f4-c469-4830-8393-8ebc5b8f79c3
        # Set pool to 0x4e962BB3889Bf030368F56810A9c96B83CB3E778
        tx1_id = 'c80e44f4-c469-4830-8393-8ebc5b8f79c3'
        correct_pool = '0x4e962BB3889Bf030368F56810A9c96B83CB3E778'

        update_tx1_query = """
        UPDATE transactions
        SET event_data = jsonb_set(event_data, '{pool}', $1::jsonb)
        WHERE id = $2
        """
        await conn.execute(update_tx1_query, json.dumps(correct_pool), tx1_id)
        print(f"✅ Updated transaction {tx1_id[:8]}... with pool {correct_pool}")

        # 2. Fix transaction fe224899-4323-49d9-aced-86402033d785 (STAKING)
        # Set pool to null
        tx2_id = 'fe224899-4323-49d9-aced-86402033d785'

        update_tx2_query = """
        UPDATE transactions
        SET event_data = jsonb_set(event_data, '{pool}', 'null'::jsonb)
        WHERE id = $1
        """
        await conn.execute(update_tx2_query, tx2_id)
        print(f"✅ Updated transaction {tx2_id[:8]}... with pool = null")

        # Verify the updates
        print("\n📋 Verification:")

        for tx_id in [tx1_id, tx2_id]:
            verify_query = """
            SELECT tx_type, position_id, event_data
            FROM transactions
            WHERE id = $1
            """
            result = await conn.fetchrow(verify_query, tx_id)
            if result:
                event_data = result['event_data']
                if isinstance(event_data, str):
                    event_data = json.loads(event_data)

                print(f"\nTransaction {tx_id[:8]}... ({result['tx_type']}):")
                print(f"  position_id: {result['position_id']}")
                print(f"  pool: {event_data.get('pool')}")
                print(f"  pool_name: {event_data.get('pool_name')}")

        print("\n🎉 Both transactions fixed successfully!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_transaction_pools())