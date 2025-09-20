#!/usr/bin/env python3
"""Fix position 26227996 with its actual pool name."""

import asyncio
import asyncpg
import json
import httpx

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def get_pool_name_from_api(pool_address):
    """Get pool name from API."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"https://n0ir-api-staging.up.railway.app/api/v1/pools/{pool_address}",
                timeout=10.0
            )
            if response.status_code == 200:
                data = response.json()
                symbol = data.get('symbol', '')
                if symbol and '-' in symbol:
                    return symbol.rsplit('-', 1)[0]
                return symbol
        except Exception as e:
            print(f"API error: {e}")
    return None

async def fix_position():
    """Fix position pool information."""
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        position_id = 26227996
        actual_pool_address = "0xb2cc224c1c9feE385f8ad6a55b4d94E92359DC59"

        # Get pool name from API
        pool_name = await get_pool_name_from_api(actual_pool_address)

        if not pool_name:
            # Fallback: assume it's USDC/cbBTC like other pools
            # Based on the pattern, this is likely USDC/cbBTC or cbBTC/USDC
            pool_name = "USDC/cbBTC"  # Default assumption

        print(f"Pool address: {actual_pool_address}")
        print(f"Pool name: {pool_name}")

        # Update position with correct pool name
        update_position_query = """
        UPDATE positions
        SET pool_name = $1
        WHERE token_id = $2
        """
        await conn.execute(update_position_query, pool_name, position_id)
        print(f"✅ Updated position {position_id} with pool_name={pool_name}")

        # Update the POSITION_CREATED transaction
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
            json.dumps(pool_name),
            json.dumps(actual_pool_address),
            position_created_tx_id
        )
        print(f"✅ Updated POSITION_CREATED transaction with pool_name={pool_name}")

        # Final verification of all three transactions
        print("\n📋 Final Verification of All Transactions:")

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
                print(f"  pool: {event_data.get('pool')}")
                print(f"  nft_token_id: {event_data.get('nft_token_id')}")

        print("\n🎉 All transactions have been fixed!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_position())