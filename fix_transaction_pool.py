#!/usr/bin/env python3
"""Fix pool name for specific transaction."""

import asyncio
import asyncpg
import json
from loguru import logger

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def fix_transaction_pool():
    """Fix pool name for transaction c80e44f4-c469-4830-8393-8ebc5b8f79c3."""
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # First, check the transaction
        tx_id = "c80e44f4-c469-4830-8393-8ebc5b8f79c3"
        query = """
        SELECT id, tx_hash, event_data, event_data->>'pool_name' as pool_name
        FROM transactions
        WHERE id = $1
        """
        tx = await conn.fetchrow(query, tx_id)

        if not tx:
            print(f"Transaction {tx_id} not found")
            return

        print(f"Found transaction: {tx['tx_hash']}")
        print(f"Current pool_name in event_data: {tx['pool_name']}")

        # Parse event_data if it's a string
        event_data = tx['event_data']
        if isinstance(event_data, str):
            event_data = json.loads(event_data)

        print(f"Event data pool address: {event_data.get('pool')}")

        # Get pool address from event_data
        pool_address = event_data.get('pool')
        if not pool_address:
            print("No pool address found in event_data")
            return

        # Fetch pool info from pools API
        import aiohttp
        async with aiohttp.ClientSession() as session:
            url = f"https://api.geckoterminal.com/api/v2/networks/base/pools/{pool_address}"
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    pool_data = data.get('data', {})
                    attributes = pool_data.get('attributes', {})

                    # Try to extract pool name from the API response
                    name = attributes.get('name', '')
                    if name:
                        # Extract token pair (e.g., "AERO / USDC 0.30%" -> "AERO-USDC")
                        if '/' in name:
                            parts = name.split('/')
                            if len(parts) == 2:
                                token1 = parts[0].strip()
                                token2_parts = parts[1].strip().split()
                                token2 = token2_parts[0] if token2_parts else parts[1].strip()
                                pool_name = f"{token1}-{token2}"
                        else:
                            pool_name = name.split()[0] if name else name
                    else:
                        # Fallback: use token symbols
                        token0 = attributes.get('token0', {}).get('symbol', '')
                        token1 = attributes.get('token1', {}).get('symbol', '')
                        if token0 and token1:
                            pool_name = f"{token0}-{token1}"
                        else:
                            pool_name = "AERO-USDC"  # Default fallback

                    print(f"\nFound pool name: {pool_name}")
                else:
                    # Fallback to AERO-USDC since that's the most common pool
                    pool_name = "AERO-USDC"
                    print(f"\nUsing default pool name: {pool_name}")

        # Update the transaction - only update event_data since pool_name column doesn't exist
        update_query = """
        UPDATE transactions
        SET event_data = event_data || jsonb_build_object('pool_name', $1::text)
        WHERE id = $2
        """
        await conn.execute(update_query, pool_name, tx_id)

        # Verify the update
        verify_query = """
        SELECT id, event_data->>'pool_name' as pool_name
        FROM transactions
        WHERE id = $1
        """
        updated = await conn.fetchrow(verify_query, tx_id)

        print(f"\n✅ Transaction updated:")
        print(f"   Pool name in event_data: {updated['pool_name']}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_transaction_pool())