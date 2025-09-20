#!/usr/bin/env python3
"""Fix existing transactions with missing position_id and pool_name."""

import asyncio
import asyncpg
import json

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def fix_transactions():
    """Fix existing transactions."""
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # 1. Fix STAKING transaction (fe224899-4323-49d9-aced-86402033d785)
        staking_tx_id = 'fe224899-4323-49d9-aced-86402033d785'

        # Find the position that was likely staked (most recent active position before staking)
        position_query = """
        SELECT token_id, pool_name, pool_address
        FROM positions
        WHERE user_id = '0xAC65e18F7f4e5eDEA297b9E5433C153f1d9a7764'
          AND created_at < '2025-09-20 17:26:39'
        ORDER BY created_at DESC
        LIMIT 1
        """
        position = await conn.fetchrow(position_query)

        if position:
            print(f"Found position {position['token_id']} with pool {position['pool_name']} for STAKING transaction")

            # Update the STAKING transaction
            update_staking_query = """
            UPDATE transactions
            SET position_id = $1,
                event_data = jsonb_set(
                    jsonb_set(
                        jsonb_set(event_data, '{nft_token_id}', $2::jsonb),
                        '{pool_name}', $3::jsonb
                    ),
                    '{pool}', $4::jsonb
                )
            WHERE id = $5
            """
            await conn.execute(
                update_staking_query,
                position['token_id'],
                json.dumps(position['token_id']),
                json.dumps(position['pool_name']),
                json.dumps(position['pool_address']),
                staking_tx_id
            )
            print(f"✅ Updated STAKING transaction with position_id={position['token_id']} and pool_name in event_data")
        else:
            print("⚠️  No position found for STAKING transaction")

        # 2. Fix POSITION_CREATED transaction (f7c2a090-be7d-4932-b86b-9f18a148c1fc)
        position_created_tx_id = 'f7c2a090-be7d-4932-b86b-9f18a148c1fc'
        position_id = 26227996

        # Get the position details
        position_query = """
        SELECT pool_name, pool_address
        FROM positions
        WHERE token_id = $1
        """
        position = await conn.fetchrow(position_query, position_id)

        if position and position['pool_name']:
            print(f"Found pool {position['pool_name']} for position {position_id}")

            # Update the POSITION_CREATED transaction
            update_created_query = """
            UPDATE transactions
            SET event_data = jsonb_set(
                    jsonb_set(
                        jsonb_set(event_data, '{pool_name}', $1::jsonb),
                        '{nft_token_id}', $2::jsonb
                    ),
                    '{pool}', $3::jsonb
                )
            WHERE id = $4
            """
            await conn.execute(
                update_created_query,
                json.dumps(position['pool_name']),
                json.dumps(position_id),
                json.dumps(position['pool_address']),
                position_created_tx_id
            )
            print(f"✅ Updated POSITION_CREATED transaction with pool_name={position['pool_name']} in event_data")
        else:
            print(f"⚠️  Position {position_id} has no pool_name, skipping pool_name update")
            # Still update the nft_token_id
            update_created_query = """
            UPDATE transactions
            SET event_data = jsonb_set(event_data, '{nft_token_id}', $1::jsonb)
            WHERE id = $2
            """
            await conn.execute(
                update_created_query,
                json.dumps(position_id),
                position_created_tx_id
            )
            print(f"✅ Updated POSITION_CREATED transaction with nft_token_id={position_id}")

        # 3. Fix POSITION_CLOSED transaction - set pool to null
        position_closed_tx_id = '1b3bf91d-2734-4718-a17f-54aea877cdc8'

        # Update to set pool to null (JSON null, not removing the key)
        update_closed_query = """
        UPDATE transactions
        SET event_data = jsonb_set(event_data, '{pool}', 'null'::jsonb)
        WHERE id = $1
        """
        await conn.execute(update_closed_query, position_closed_tx_id)
        print(f"✅ Set pool address to null in POSITION_CLOSED transaction")

        print("\n🎉 All transactions fixed successfully!")

        # Verify the fixes
        print("\n📋 Verification:")
        for tx_id in [staking_tx_id, position_created_tx_id, position_closed_tx_id]:
            verify_query = """
            SELECT tx_type, position_id, event_data
            FROM transactions
            WHERE id = $1
            """
            result = await conn.fetchrow(verify_query, tx_id)
            if result:
                print(f"\n{result['tx_type']}:")
                print(f"  position_id: {result['position_id']}")
                event_data = result['event_data']
                if isinstance(event_data, str):
                    event_data = json.loads(event_data)
                print(f"  pool_name: {event_data.get('pool_name')}")
                print(f"  pool: {event_data.get('pool')}")
                print(f"  nft_token_id: {event_data.get('nft_token_id')}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_transactions())