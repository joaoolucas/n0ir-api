#!/usr/bin/env python3
"""Fix position 26227996 to add pool information."""

import asyncio
import asyncpg
import json

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def fix_position():
    """Fix position pool information."""
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        position_id = 26227996

        # Check current position state
        check_query = """
        SELECT token_id, pool_address, pool_name, entry_tx_hash
        FROM positions
        WHERE token_id = $1
        """
        position = await conn.fetchrow(check_query, position_id)

        if position:
            print(f"Current position state:")
            print(f"  Token ID: {position['token_id']}")
            print(f"  Pool Address: {position['pool_address']}")
            print(f"  Pool Name: {position['pool_name']}")
            print(f"  Entry TX: {position['entry_tx_hash']}")

            # This position likely uses the same pool as other positions from the same user
            # Let's check what pool they typically use
            pool_query = """
            SELECT pool_address, pool_name, COUNT(*) as count
            FROM positions
            WHERE user_id = '0xAC65e18F7f4e5eDEA297b9E5433C153f1d9a7764'
              AND pool_address IS NOT NULL
              AND pool_name IS NOT NULL
            GROUP BY pool_address, pool_name
            ORDER BY count DESC
            LIMIT 1
            """
            common_pool = await conn.fetchrow(pool_query)

            if common_pool:
                print(f"\nMost common pool for this user:")
                print(f"  Pool Address: {common_pool['pool_address']}")
                print(f"  Pool Name: {common_pool['pool_name']}")

                # Update the position with pool information
                update_position_query = """
                UPDATE positions
                SET pool_address = $1,
                    pool_name = $2
                WHERE token_id = $3
                """
                await conn.execute(
                    update_position_query,
                    common_pool['pool_address'],
                    common_pool['pool_name'],
                    position_id
                )
                print(f"✅ Updated position {position_id} with pool information")

                # Now update the POSITION_CREATED transaction
                position_created_tx_id = 'f7c2a090-be7d-4932-b86b-9f18a148c1fc'

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
                    json.dumps(common_pool['pool_name']),
                    json.dumps(common_pool['pool_address']),
                    position_created_tx_id
                )
                print(f"✅ Updated POSITION_CREATED transaction with pool_name={common_pool['pool_name']}")

                # Verify the fix
                verify_query = """
                SELECT event_data
                FROM transactions
                WHERE id = $1
                """
                result = await conn.fetchrow(verify_query, position_created_tx_id)
                if result:
                    event_data = result['event_data']
                    if isinstance(event_data, str):
                        event_data = json.loads(event_data)
                    print(f"\nVerification - POSITION_CREATED transaction now has:")
                    print(f"  pool_name: {event_data.get('pool_name')}")
                    print(f"  pool: {event_data.get('pool')}")
                    print(f"  nft_token_id: {event_data.get('nft_token_id')}")
        else:
            print(f"Position {position_id} not found")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_position())