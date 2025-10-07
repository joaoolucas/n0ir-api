#!/usr/bin/env python3
"""Fix pool information for position 26235169 transactions."""

import asyncio
import asyncpg
import json

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def fix_transactions():
    """Fix pool address and name for position 26235169 transactions."""
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # Correct pool information from positions endpoint
        correct_pool = '0x4e962BB3889Bf030368F56810A9c96B83CB3E778'
        correct_pool_name = 'USDC/cbBTC'
        correct_gauge = '0x6399ed6725cC163D019aA64FF55b22149D7179A8'
        position_id = 26235169

        # Transactions to fix
        transactions = [
            {
                'id': 'e5f90a9f-2190-493b-9718-58096cb46a0c',
                'type': 'STAKING'
            },
            {
                'id': 'd1e9429d-d21a-4844-9d75-2d6a5fa0d8ac',
                'type': 'POSITION_CREATED'
            }
        ]

        for tx in transactions:
            print(f"Fixing {tx['type']} transaction {tx['id'][:8]}...")

            if tx['type'] == 'STAKING':
                # For STAKING, keep gauge_address but fix pool
                update_query = """
                UPDATE transactions
                SET event_data = jsonb_set(
                        jsonb_set(
                            jsonb_set(event_data, '{pool}', $1::jsonb),
                            '{pool_name}', $2::jsonb
                        ),
                        '{gauge_address}', $3::jsonb
                    )
                WHERE id = $4
                """

                await conn.execute(
                    update_query,
                    json.dumps(correct_pool),
                    json.dumps(correct_pool_name),
                    json.dumps(correct_gauge),
                    tx['id']
                )
            else:
                # For POSITION_CREATED, just fix pool
                update_query = """
                UPDATE transactions
                SET event_data = jsonb_set(
                        jsonb_set(event_data, '{pool}', $1::jsonb),
                        '{pool_name}', $2::jsonb
                    )
                WHERE id = $3
                """

                await conn.execute(
                    update_query,
                    json.dumps(correct_pool),
                    json.dumps(correct_pool_name),
                    tx['id']
                )

            print(f"✅ Updated {tx['type']} with correct pool: {correct_pool} ({correct_pool_name})")

        # Also update the position record to ensure consistency
        position_update = """
        UPDATE positions
        SET pool_address = $1,
            pool_name = $2,
            gauge_address = $3
        WHERE token_id = $4
        """

        await conn.execute(
            position_update,
            correct_pool,
            correct_pool_name,
            correct_gauge,
            position_id
        )
        print(f"✅ Updated position {position_id} with correct pool information")

        # Verify the updates
        print("\n📋 Verification:")

        for tx in transactions:
            verify_query = """
            SELECT id, tx_type, position_id, event_data
            FROM transactions
            WHERE id = $1
            """
            result = await conn.fetchrow(verify_query, tx['id'])

            if result:
                event_data = result['event_data']
                if isinstance(event_data, str):
                    event_data = json.loads(event_data)

                print(f"\n{tx['type']} transaction {str(result['id'])[:8]}...:")
                print(f"  pool: {event_data.get('pool')}")
                print(f"  pool_name: {event_data.get('pool_name')}")
                if tx['type'] == 'STAKING':
                    print(f"  gauge_address: {event_data.get('gauge_address')}")

        # Verify position
        position_query = """
        SELECT token_id, pool_address, pool_name, gauge_address
        FROM positions
        WHERE token_id = $1
        """
        pos_result = await conn.fetchrow(position_query, position_id)

        if pos_result:
            print(f"\nPosition {pos_result['token_id']}:")
            print(f"  pool_address: {pos_result['pool_address']}")
            print(f"  pool_name: {pos_result['pool_name']}")
            print(f"  gauge_address: {pos_result['gauge_address']}")

        print("\n🎉 All records fixed successfully!")
        print("\n📝 Note: The gauge address (0x6399ed6725cC163D019aA64FF55b22149D7179A8) is where the position is staked,")
        print("      while the pool address (0x4e962BB3889Bf030368F56810A9c96B83CB3E778) is the actual liquidity pool.")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_transactions())