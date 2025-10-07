#!/usr/bin/env python3
"""Check for WETH pools in the database."""

import asyncio
import asyncpg
import json

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def check_pools():
    """Check what pools exist for this user."""
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # Check all pools used by this user
        pools_query = """
        SELECT DISTINCT pool_address, pool_name, token_id
        FROM positions
        WHERE user_id = '0xAC65e18F7f4e5eDEA297b9E5433C153f1d9a7764'
        ORDER BY token_id DESC
        """
        pools = await conn.fetch(pools_query)

        print("All positions for user 0xAC65e18F7f4e5eDEA297b9E5433C153f1d9a7764:")
        for pool in pools:
            print(f"  Position {pool['token_id']}: {pool['pool_name']} ({pool['pool_address']})")

        # Check for any WETH pools
        weth_query = """
        SELECT DISTINCT pool_address, pool_name
        FROM positions
        WHERE pool_name LIKE '%WETH%' OR pool_name LIKE '%ETH%'
        ORDER BY pool_name
        """
        weth_pools = await conn.fetch(weth_query)

        print("\nAll WETH/ETH pools in database:")
        for pool in weth_pools:
            print(f"  {pool['pool_name']}: {pool['pool_address']}")

        # Check specific positions
        print("\nSpecific position details:")
        for position_id in [26216334, 26227996]:
            pos_query = """
            SELECT token_id, pool_address, pool_name, status, entry_tx_hash
            FROM positions
            WHERE token_id = $1
            """
            pos = await conn.fetchrow(pos_query, position_id)
            if pos:
                print(f"\nPosition {pos['token_id']}:")
                print(f"  Pool name: {pos['pool_name']}")
                print(f"  Pool address: {pos['pool_address']}")
                print(f"  Status: {pos['status']}")
                print(f"  Entry TX: {pos['entry_tx_hash']}")

        # Since you mentioned WETH/USDC, let me update with that
        print("\nFixing pools to WETH/USDC...")

        # Determine the correct pool address for WETH/USDC
        # Pool address 0xb2cc224c1c9feE385f8ad6a55b4d94E92359DC59 is likely WETH/USDC
        weth_pool_address = "0xb2cc224c1c9feE385f8ad6a55b4d94E92359DC59"
        weth_pool_name = "WETH/USDC"

        # Update position 26227996 (the one with 0xb2cc... address)
        update_pos_query = """
        UPDATE positions
        SET pool_name = $1
        WHERE token_id = $2 AND pool_address = $3
        """
        await conn.execute(update_pos_query, weth_pool_name, 26227996, weth_pool_address)
        print(f"✅ Updated position 26227996 to {weth_pool_name}")

        # The other position (26216334) might actually be on a different pool
        # Let's set it to WETH/USDC as well if that's what you know
        update_pos_query2 = """
        UPDATE positions
        SET pool_name = $1
        WHERE token_id = $2
        """
        await conn.execute(update_pos_query2, weth_pool_name, 26216334)
        print(f"✅ Updated position 26216334 to {weth_pool_name}")

        # Update all related transactions
        transactions = [
            ('fe224899-4323-49d9-aced-86402033d785', 'STAKING', 26216334),
            ('f7c2a090-be7d-4932-b86b-9f18a148c1fc', 'POSITION_CREATED', 26227996),
            ('1b3bf91d-2734-4718-a17f-54aea877cdc8', 'POSITION_CLOSED', 26216334)
        ]

        for tx_id, tx_type, position_id in transactions:
            update_tx_query = """
            UPDATE transactions
            SET event_data = jsonb_set(event_data, '{pool_name}', $1::jsonb)
            WHERE id = $2
            """
            await conn.execute(update_tx_query, json.dumps(weth_pool_name), tx_id)
            print(f"✅ Updated {tx_type} transaction to {weth_pool_name}")

        # Verify the updates
        print("\n📋 Final Verification:")
        for tx_id, tx_type, position_id in transactions:
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
                print(f"\n{tx_type}:")
                print(f"  position_id: {result['position_id']}")
                print(f"  pool_name: {event_data.get('pool_name')}")
                print(f"  nft_token_id: {event_data.get('nft_token_id')}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(check_pools())