#!/usr/bin/env python3
"""Check the actual pools for positions via API."""

import asyncio
import httpx
import asyncpg
import json

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"
API_URL = "https://n0ir-api-staging.up.railway.app"

async def check_and_fix_positions():
    """Check positions via API and fix them."""

    positions_to_check = [26216334, 26227996]

    async with httpx.AsyncClient(timeout=30.0) as client:
        for position_id in positions_to_check:
            try:
                # Get position details from API
                response = await client.get(f"{API_URL}/api/v1/positions/{position_id}")
                if response.status_code == 200:
                    data = response.json()
                    print(f"\nPosition {position_id}:")
                    print(f"  Pool Name from API: {data.get('pool_name')}")
                    print(f"  Pool Address from API: {data.get('pool_address')}")
                    print(f"  Status: {data.get('status')}")

                    # Now fix in database
                    conn = await asyncpg.connect(DATABASE_URL)
                    try:
                        actual_pool_name = data.get('pool_name')
                        actual_pool_address = data.get('pool_address')

                        if actual_pool_name:
                            # Update position
                            update_position_query = """
                            UPDATE positions
                            SET pool_name = $1,
                                pool_address = $2
                            WHERE token_id = $3
                            """
                            await conn.execute(
                                update_position_query,
                                actual_pool_name,
                                actual_pool_address,
                                position_id
                            )
                            print(f"  ✅ Updated position {position_id} with pool_name={actual_pool_name}")

                            # Find and update related transactions
                            find_tx_query = """
                            SELECT id, tx_type
                            FROM transactions
                            WHERE position_id = $1
                               OR (event_data->>'nft_token_id')::text = $2
                            """
                            transactions = await conn.fetch(find_tx_query, position_id, str(position_id))

                            for tx in transactions:
                                update_tx_query = """
                                UPDATE transactions
                                SET event_data = jsonb_set(
                                        jsonb_set(event_data, '{pool_name}', $1::jsonb),
                                        '{pool}', $2::jsonb
                                    )
                                WHERE id = $3
                                """
                                await conn.execute(
                                    update_tx_query,
                                    json.dumps(actual_pool_name),
                                    json.dumps(actual_pool_address),
                                    tx['id']
                                )
                                print(f"  ✅ Updated {tx['tx_type']} transaction {tx['id'][:8]}...")

                    finally:
                        await conn.close()
                else:
                    print(f"Failed to get position {position_id}: {response.status_code}")

            except Exception as e:
                print(f"Error checking position {position_id}: {e}")

    # Final verification
    print("\n📋 Final Verification:")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        transactions = [
            ('fe224899-4323-49d9-aced-86402033d785', 'STAKING'),
            ('f7c2a090-be7d-4932-b86b-9f18a148c1fc', 'POSITION_CREATED'),
            ('1b3bf91d-2734-4718-a17f-54aea877cdc8', 'POSITION_CLOSED')
        ]

        for tx_id, tx_type in transactions:
            verify_query = """
            SELECT position_id, event_data
            FROM transactions
            WHERE id = $1
            """
            result = await conn.fetchrow(verify_query, tx_id)
            if result:
                print(f"\n{tx_type}:")
                print(f"  position_id: {result['position_id']}")
                event_data = result['event_data']
                if isinstance(event_data, str):
                    event_data = json.loads(event_data)
                print(f"  pool_name: {event_data.get('pool_name')}")
                print(f"  nft_token_id: {event_data.get('nft_token_id')}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_and_fix_positions())