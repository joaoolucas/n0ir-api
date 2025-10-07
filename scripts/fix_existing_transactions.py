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
        # Need to find the position_id from the transaction hash
        staking_tx_id = 'fe224899-4323-49d9-aced-86402033d785'

        # First, let's find the most recent position for this user that was created before this staking
        position_query = """
        SELECT token_id, pool_name, pool_address
        FROM positions
        WHERE user_id = '0xAC65e18F7f4e5eDEA297b9E5433C153f1d9a7764'
          AND created_at < '2025-09-20T17:26:39'
          AND status = 'ACTIVE'
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
                pool_name = $2,
                event_data = jsonb_set(
                    jsonb_set(event_data, '{nft_token_id}', $3::jsonb),
                    '{pool_name}', $4::jsonb
                )
            WHERE id = $5
            """
            await conn.execute(
                update_staking_query,
                position['token_id'],
                position['pool_name'],
                json.dumps(position['token_id']),
                json.dumps(position['pool_name']),
                staking_tx_id
            )
            print(f"✅ Updated STAKING transaction with position_id={position['token_id']} and pool_name={position['pool_name']}")

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

        if position:
            print(f"Found pool {position['pool_name']} for position {position_id}")

            # Update the POSITION_CREATED transaction
            update_created_query = """
            UPDATE transactions
            SET pool_name = $1,
                event_data = jsonb_set(
                    jsonb_set(event_data, '{pool_name}', $2::jsonb),
                    '{nft_token_id}', $3::jsonb
                )
            WHERE id = $4
            """
            await conn.execute(
                update_created_query,
                position['pool_name'],
                json.dumps(position['pool_name']),
                json.dumps(position_id),
                position_created_tx_id
            )
            print(f"✅ Updated POSITION_CREATED transaction with pool_name={position['pool_name']}")

        # 3. Fix POSITION_CLOSED transaction - remove incorrect pool address
        position_closed_tx_id = '1b3bf91d-2734-4718-a17f-54aea877cdc8'

        # Update to remove the incorrect pool address (set to null)
        update_closed_query = """
        UPDATE transactions
        SET event_data = event_data - 'pool'
        WHERE id = $1
        """
        await conn.execute(update_closed_query, position_closed_tx_id)
        print(f"✅ Removed incorrect pool address from POSITION_CLOSED transaction")

        print("\n🎉 All transactions fixed successfully!")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_transactions())