#!/usr/bin/env python3
"""Update existing position transactions to populate pool_name from pool address."""

import asyncio
import asyncpg
import json
import aiohttp

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"
POOLS_SERVICE_URL = "https://n0ir-pools.n0irlabs.workers.dev"

async def fetch_pool_name(session, pool_address):
    """Fetch pool name from pools service."""
    try:
        url = f"{POOLS_SERVICE_URL}/pool/{pool_address}?include_effective_apr=false"
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                symbol = data.get('symbol', '')
                # Symbol format is "TOKEN0/TOKEN1-0.3%"
                # We want to keep "TOKEN0/TOKEN1" format
                if symbol and '-' in symbol:
                    # Remove fee percentage (everything after last dash)
                    pool_name = symbol.rsplit('-', 1)[0]  # Gets "TOKEN0/TOKEN1"
                else:
                    pool_name = symbol
                return pool_name
    except Exception as e:
        print(f"Error fetching pool {pool_address}: {e}")
    return None

async def update_transaction_pool_names():
    """Update pool_name for existing transactions."""
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # Find all position-related transactions without pool_name
        query = """
        SELECT id, tx_hash, tx_type, event_data, position_id
        FROM transactions
        WHERE tx_type IN ('POSITION_CREATED', 'POSITION_CLOSED', 'STAKING')
        """
        transactions = await conn.fetch(query)

        print(f"Found {len(transactions)} position-related transactions")

        # Create aiohttp session for fetching pool data
        async with aiohttp.ClientSession() as session:
            updated_count = 0

            for tx in transactions:
                event_data = tx['event_data']
                if isinstance(event_data, str):
                    try:
                        event_data = json.loads(event_data)
                    except:
                        continue

                # Skip if already has pool_name
                if event_data.get('pool_name'):
                    continue

                # Get pool address from event_data or position
                pool_address = event_data.get('pool')

                # If POSITION_CLOSED and no pool address, look it up from position
                if not pool_address and tx['tx_type'] == 'POSITION_CLOSED' and tx['position_id']:
                    position_query = """
                    SELECT pool_address
                    FROM positions
                    WHERE token_id = $1
                    """
                    position = await conn.fetchrow(position_query, tx['position_id'])
                    if position:
                        pool_address = position['pool_address']

                if pool_address:
                    # Fetch pool name
                    pool_name = await fetch_pool_name(session, pool_address)

                    if pool_name:
                        # Update event_data with pool_name
                        event_data['pool_name'] = pool_name
                        if not event_data.get('pool'):
                            event_data['pool'] = pool_address

                        update_query = """
                        UPDATE transactions
                        SET event_data = $1
                        WHERE id = $2
                        """
                        await conn.execute(update_query, json.dumps(event_data), tx['id'])
                        updated_count += 1
                        print(f"✅ Updated {tx['tx_type']} transaction {tx['tx_hash'][:10]}... with pool_name={pool_name}")
                    else:
                        print(f"⚠️  Could not fetch pool name for {pool_address} in tx {tx['tx_hash'][:10]}...")

        print(f"\n✅ Updated {updated_count} transactions with pool_name")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(update_transaction_pool_names())