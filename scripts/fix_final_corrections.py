#!/usr/bin/env python3
"""Fix the final corrections for transactions."""

import asyncio
import asyncpg
import json

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def fix_final_corrections():
    """Fix the final corrections."""
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        print("Applying final corrections...")

        # 1. Fix POSITION_CLOSED transaction (1b3bf91d-2734-4718-a17f-54aea877cdc8)
        # This was for position 26216334 which is USDC/cbBTC, not WETH/USDC
        position_closed_tx_id = '1b3bf91d-2734-4718-a17f-54aea877cdc8'

        # Get the correct pool info for position 26216334
        pos_query = """
        SELECT pool_address
        FROM positions
        WHERE token_id = 26216334
        """
        pos = await conn.fetchrow(pos_query)

        update_closed_query = """
        UPDATE transactions
        SET event_data = jsonb_set(event_data, '{pool_name}', $1::jsonb)
        WHERE id = $2
        """
        await conn.execute(update_closed_query, json.dumps("USDC/cbBTC"), position_closed_tx_id)
        print(f"✅ Updated POSITION_CLOSED transaction to USDC/cbBTC (position 26216334)")

        # Also update position 26216334 back to USDC/cbBTC
        update_pos_query = """
        UPDATE positions
        SET pool_name = $1
        WHERE token_id = $2
        """
        await conn.execute(update_pos_query, "USDC/cbBTC", 26216334)
        print(f"✅ Updated position 26216334 pool_name to USDC/cbBTC")

        # 2. Fix STAKING transaction (fe224899-4323-49d9-aced-86402033d785)
        # This should be for position 26227996 (WETH/USDC), not 26216334
        staking_tx_id = 'fe224899-4323-49d9-aced-86402033d785'

        # Update to position 26227996 with WETH/USDC pool
        update_staking_query = """
        UPDATE transactions
        SET position_id = $1,
            event_data = jsonb_set(
                jsonb_set(event_data, '{pool_name}', $2::jsonb),
                '{nft_token_id}', $3::jsonb
            )
        WHERE id = $4
        """
        await conn.execute(
            update_staking_query,
            26227996,
            json.dumps("WETH/USDC"),
            json.dumps(26227996),
            staking_tx_id
        )
        print(f"✅ Updated STAKING transaction to position 26227996 with WETH/USDC")

        # Make sure position 26227996 is WETH/USDC
        await conn.execute(update_pos_query, "WETH/USDC", 26227996)
        print(f"✅ Confirmed position 26227996 pool_name is WETH/USDC")

        # Final verification
        print("\n📋 Final Verification:")

        transactions = [
            ('fe224899-4323-49d9-aced-86402033d785', 'STAKING', 26227996, 'WETH/USDC'),
            ('f7c2a090-be7d-4932-b86b-9f18a148c1fc', 'POSITION_CREATED', 26227996, 'WETH/USDC'),
            ('1b3bf91d-2734-4718-a17f-54aea877cdc8', 'POSITION_CLOSED', 26216334, 'USDC/cbBTC')
        ]

        for tx_id, tx_type, expected_position, expected_pool in transactions:
            verify_query = """
            SELECT position_id, event_data
            FROM transactions
            WHERE id = $1
            """
            result = await conn.fetchrow(verify_query, tx_id)
            if result:
                event_data = result['event_data']
                if isinstance(event_data, str):
                    event_data = json.loads(event_data)

                position_ok = "✅" if result['position_id'] == expected_position else "❌"
                pool_ok = "✅" if event_data.get('pool_name') == expected_pool else "❌"

                print(f"\n{tx_type}:")
                print(f"  position_id: {result['position_id']} (expected: {expected_position}) {position_ok}")
                print(f"  pool_name: {event_data.get('pool_name')} (expected: {expected_pool}) {pool_ok}")
                print(f"  nft_token_id: {event_data.get('nft_token_id')}")

        # Also verify the positions
        print("\n📋 Position Verification:")
        for position_id, expected_pool in [(26216334, 'USDC/cbBTC'), (26227996, 'WETH/USDC')]:
            pos_verify_query = """
            SELECT token_id, pool_name, pool_address
            FROM positions
            WHERE token_id = $1
            """
            pos = await conn.fetchrow(pos_verify_query, position_id)
            if pos:
                pool_ok = "✅" if pos['pool_name'] == expected_pool else "❌"
                print(f"\nPosition {pos['token_id']}:")
                print(f"  pool_name: {pos['pool_name']} (expected: {expected_pool}) {pool_ok}")
                print(f"  pool_address: {pos['pool_address']}")

        print("\n🎉 All corrections applied successfully!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_final_corrections())