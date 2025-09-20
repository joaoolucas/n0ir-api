#!/usr/bin/env python3
"""Fix specific transactions with missing position_id and pool information."""

import asyncio
import asyncpg
import json

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def fix_specific_transactions():
    """Fix two specific transactions with missing data."""
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # Transaction 1: STAKING transaction
        # This is staking position 26235169 to gauge 0x827922686190790b37229fd06084350e74485b72
        # Pool: cbBTC/WETH at 0x827922686190790b37229fd06084350e74485b72
        staking_tx_id = 'e5f90a9f-2190-493b-9718-58096cb46a0c'
        staking_position_id = 26235169  # The position being staked
        staking_pool = '0x827922686190790b37229fd06084350e74485b72'
        staking_pool_name = 'cbBTC/WETH'

        print(f"Fixing STAKING transaction {staking_tx_id[:8]}...")

        # Update STAKING transaction
        update_staking = """
        UPDATE transactions
        SET position_id = $1,
            event_data = jsonb_set(
                jsonb_set(
                    jsonb_set(event_data, '{nft_token_id}', $2::jsonb),
                    '{pool}', $3::jsonb
                ),
                '{pool_name}', $4::jsonb
            )
        WHERE id = $5
        """

        await conn.execute(
            update_staking,
            staking_position_id,
            json.dumps(staking_position_id),
            json.dumps(staking_pool),
            json.dumps(staking_pool_name),
            staking_tx_id
        )
        print(f"✅ Updated STAKING transaction with position_id={staking_position_id}, pool={staking_pool_name}")

        # Transaction 2: POSITION_CREATED transaction
        # This created position 26235169
        # Pool: cbBTC/WETH at 0x827922686190790b37229fd06084350e74485b72
        position_tx_id = 'd1e9429d-d21a-4844-9d75-2d6a5fa0d8ac'
        position_pool = '0x827922686190790b37229fd06084350e74485b72'
        position_pool_name = 'cbBTC/WETH'

        print(f"Fixing POSITION_CREATED transaction {position_tx_id[:8]}...")

        # Update POSITION_CREATED transaction
        update_position = """
        UPDATE transactions
        SET event_data = jsonb_set(
                jsonb_set(
                    jsonb_set(event_data, '{nft_token_id}', $1::jsonb),
                    '{pool}', $2::jsonb
                ),
                '{pool_name}', $3::jsonb
            )
        WHERE id = $4
        """

        await conn.execute(
            update_position,
            json.dumps(staking_position_id),  # Same position ID
            json.dumps(position_pool),
            json.dumps(position_pool_name),
            position_tx_id
        )
        print(f"✅ Updated POSITION_CREATED transaction with pool={position_pool_name}")

        # Verify the updates
        print("\n📋 Verification:")

        for tx_id, tx_type in [(staking_tx_id, 'STAKING'), (position_tx_id, 'POSITION_CREATED')]:
            verify_query = """
            SELECT id, tx_type, position_id, event_data
            FROM transactions
            WHERE id = $1
            """
            result = await conn.fetchrow(verify_query, tx_id)

            if result:
                event_data = result['event_data']
                if isinstance(event_data, str):
                    event_data = json.loads(event_data)

                print(f"\n{tx_type} transaction {str(result['id'])[:8]}...:")
                print(f"  position_id: {result['position_id']}")
                print(f"  pool: {event_data.get('pool')}")
                print(f"  pool_name: {event_data.get('pool_name')}")
                print(f"  nft_token_id: {event_data.get('nft_token_id')}")

        print("\n🎉 Transactions fixed successfully!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_specific_transactions())