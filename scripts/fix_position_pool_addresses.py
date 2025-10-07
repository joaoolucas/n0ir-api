#!/usr/bin/env python3
"""Fix incorrect pool addresses for specific positions."""

import asyncio
import asyncpg
import json

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def fix_position_pools():
    """Fix pool addresses for positions 26216334 and 26227996."""
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # Position corrections
        corrections = [
            {
                'token_id': 26216334,
                'correct_pool': '0x4e962BB3889Bf030368F56810A9c96B83CB3E778',
                'pool_name': 'USDC/cbBTC'
            },
            {
                'token_id': 26227996,
                'correct_pool': '0xb2cc224c1c9feE385f8ad6a55b4d94E92359DC59',
                'pool_name': 'WETH/USDC'
            }
        ]

        for correction in corrections:
            # Update position pool address
            update_query = """
            UPDATE positions
            SET pool_address = $1, pool_name = $2
            WHERE token_id = $3
            """
            await conn.execute(
                update_query,
                correction['correct_pool'],
                correction['pool_name'],
                correction['token_id']
            )
            print(f"✅ Updated position {correction['token_id']} with pool {correction['correct_pool']} ({correction['pool_name']})")

        # Also update any related transactions
        for correction in corrections:
            # Update POSITION_CREATED transactions
            tx_update_query = """
            UPDATE transactions
            SET event_data = jsonb_set(
                jsonb_set(event_data, '{pool}', $1::jsonb),
                '{pool_name}',
                $2::jsonb
            )
            WHERE position_id = $3
            AND tx_type IN ('POSITION_CREATED', 'POSITION_CLOSED', 'STAKING')
            """

            await conn.execute(
                tx_update_query,
                json.dumps(correction['correct_pool']),
                json.dumps(correction['pool_name']),
                correction['token_id']
            )
            print(f"✅ Updated transactions for position {correction['token_id']}")

        # Verify the updates
        print("\n📋 Verification:")
        for correction in corrections:
            verify_query = """
            SELECT token_id, pool_address, pool_name, status
            FROM positions
            WHERE token_id = $1
            """
            result = await conn.fetchrow(verify_query, correction['token_id'])
            if result:
                print(f"\nPosition {result['token_id']} ({result['status']}):")
                print(f"  pool_address: {result['pool_address']}")
                print(f"  pool_name: {result['pool_name']}")

        print("\n🎉 Pool addresses fixed successfully!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_position_pools())