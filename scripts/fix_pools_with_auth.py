#!/usr/bin/env python3
"""Fix pool names using authenticated API calls."""

import asyncio
import httpx
import asyncpg
import json

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"
API_URL = "https://n0ir-api-staging.up.railway.app"
AUTH_TOKEN = "5RRJ8kHdu5M6HL91hY5bUI0abWtbANwjqVKtmjq4BMk="

async def fix_pools():
    """Fix pool names with correct data from API."""

    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {AUTH_TOKEN}"
    }

    positions_to_check = [26216334, 26227996]
    position_data = {}

    async with httpx.AsyncClient(timeout=30.0) as client:
        for position_id in positions_to_check:
            try:
                response = await client.get(
                    f"{API_URL}/api/v1/positions/{position_id}",
                    headers=headers
                )

                if response.status_code == 200:
                    data = response.json()
                    position_data[position_id] = {
                        'pool_name': data.get('pool_name'),
                        'pool_address': data.get('pool_address')
                    }
                    print(f"Position {position_id}:")
                    print(f"  Actual pool name: {data.get('pool_name')}")
                    print(f"  Pool address: {data.get('pool_address')}")
                    print(f"  Status: {data.get('status')}")
                    print()
                else:
                    print(f"Failed to get position {position_id}: {response.status_code}")

            except Exception as e:
                print(f"Error fetching position {position_id}: {e}")

    # Now update database with correct information
    if position_data:
        conn = await asyncpg.connect(DATABASE_URL)
        try:
            for position_id, pool_info in position_data.items():
                if pool_info['pool_name']:
                    # Update position
                    update_pos_query = """
                    UPDATE positions
                    SET pool_name = $1,
                        pool_address = $2
                    WHERE token_id = $3
                    """
                    await conn.execute(
                        update_pos_query,
                        pool_info['pool_name'],
                        pool_info['pool_address'],
                        position_id
                    )
                    print(f"✅ Updated position {position_id} with {pool_info['pool_name']}")

                    # Update all transactions for this position
                    update_tx_query = """
                    UPDATE transactions
                    SET event_data = jsonb_set(
                            jsonb_set(event_data, '{pool_name}', $1::jsonb),
                            '{pool}', $2::jsonb
                        )
                    WHERE position_id = $3
                       OR (event_data->>'nft_token_id')::text = $4
                    """
                    await conn.execute(
                        update_tx_query,
                        json.dumps(pool_info['pool_name']),
                        json.dumps(pool_info['pool_address']),
                        position_id,
                        str(position_id)
                    )
                    print(f"✅ Updated transactions for position {position_id}")

            # Special case: POSITION_CLOSED should have pool=null as requested
            update_closed_query = """
            UPDATE transactions
            SET event_data = jsonb_set(event_data, '{pool}', 'null'::jsonb)
            WHERE id = '1b3bf91d-2734-4718-a17f-54aea877cdc8'
            """
            await conn.execute(update_closed_query)
            print("✅ Set pool=null for POSITION_CLOSED transaction")

            print("\n📋 Final Verification:")

            transactions = [
                ('fe224899-4323-49d9-aced-86402033d785', 'STAKING', 26216334),
                ('f7c2a090-be7d-4932-b86b-9f18a148c1fc', 'POSITION_CREATED', 26227996),
                ('1b3bf91d-2734-4718-a17f-54aea877cdc8', 'POSITION_CLOSED', 26216334)
            ]

            for tx_id, tx_type, expected_position in transactions:
                verify_query = """
                SELECT position_id, event_data
                FROM transactions
                WHERE id = $1
                """
                result = await conn.fetchrow(verify_query, tx_id)
                if result:
                    print(f"\n{tx_type} (position {expected_position}):")
                    print(f"  position_id: {result['position_id']}")
                    event_data = result['event_data']
                    if isinstance(event_data, str):
                        event_data = json.loads(event_data)

                    expected_pool_name = position_data.get(expected_position, {}).get('pool_name', 'Unknown')
                    print(f"  pool_name: {event_data.get('pool_name')} (should be: {expected_pool_name})")
                    print(f"  pool: {event_data.get('pool')}")
                    print(f"  nft_token_id: {event_data.get('nft_token_id')}")

        finally:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_pools())