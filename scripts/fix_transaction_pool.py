#!/usr/bin/env python3
"""Fix pool address for transaction a4f94390-e785-4139-961b-70cf88dc40ca."""

import asyncio
import asyncpg
import json

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def fix_transaction_pool():
    """Fix pool address for specific transaction."""
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        tx_id = 'a4f94390-e785-4139-961b-70cf88dc40ca'
        correct_pool = '0xb2cc224c1c9feE385f8ad6a55b4d94E92359DC59'
        pool_name = 'WETH/USDC'

        # Check current data
        check_query = """
        SELECT id, tx_type, position_id, event_data
        FROM transactions
        WHERE id = $1
        """
        result = await conn.fetchrow(check_query, tx_id)

        if result:
            event_data = result['event_data']
            if isinstance(event_data, str):
                event_data = json.loads(event_data)

            print(f"Current transaction data:")
            print(f"  ID: {str(result['id'])[:8]}...")
            print(f"  Type: {result['tx_type']}")
            print(f"  Position ID: {result['position_id']}")
            print(f"  Current pool: {event_data.get('pool')}")
            print(f"  Current pool_name: {event_data.get('pool_name')}")

            # Update the transaction
            update_query = """
            UPDATE transactions
            SET event_data = jsonb_set(
                jsonb_set(event_data, '{pool}', $1::jsonb),
                '{pool_name}',
                $2::jsonb
            )
            WHERE id = $3
            """
            await conn.execute(
                update_query,
                json.dumps(correct_pool),
                json.dumps(pool_name),
                tx_id
            )
            print(f"\n✅ Updated transaction {tx_id[:8]}... with pool {correct_pool}")

            # Verify the update
            verify = await conn.fetchrow(check_query, tx_id)
            if verify:
                event_data = verify['event_data']
                if isinstance(event_data, str):
                    event_data = json.loads(event_data)

                print(f"\nUpdated transaction data:")
                print(f"  Pool: {event_data.get('pool')}")
                print(f"  Pool name: {event_data.get('pool_name')}")

        else:
            print(f"❌ Transaction {tx_id} not found")

        print("\n🎉 Transaction pool address fixed successfully!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_transaction_pool())