#!/usr/bin/env python3
"""
Find the transaction that created a specific position NFT.
"""

import asyncio
import asyncpg
import os
import json
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


async def find_position_creation(position_id: int):
    """Find transactions related to a position."""

    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        database_url = os.getenv('DATABASE_PRIVATE_URL')

    if not database_url:
        print("❌ No database URL found in environment")
        return

    conn = await asyncpg.connect(database_url)

    try:
        print(f"\n{'='*60}")
        print(f"SEARCHING FOR POSITION {position_id}")
        print(f"{'='*60}")

        # 1. Check if position exists in positions table
        position_query = """
        SELECT
            token_id,
            user_id,
            pool_address,
            pool_name,
            entry_amount_usdc,
            status,
            entry_date,
            entry_tx_hash
        FROM positions
        WHERE token_id = $1
        """

        position = await conn.fetchrow(position_query, position_id)

        if position:
            print(f"\n✅ Position found in database:")
            print(f"   User: {position['user_id']}")
            print(f"   Pool: {position['pool_name'] or position['pool_address']}")
            print(f"   Entry Amount: {position['entry_amount_usdc']} USDC")
            print(f"   Status: {position['status']}")
            print(f"   Entry TX: {position['entry_tx_hash'] or 'Not recorded'}")

            user_id = position['user_id']
        else:
            print(f"\n❌ Position {position_id} not found in positions table")
            # Try to find user from transactions
            user_query = """
            SELECT DISTINCT user_id
            FROM transactions
            WHERE event_data::text LIKE $1
            OR position_id = $2
            LIMIT 1
            """
            user_result = await conn.fetchrow(user_query, f'%{position_id}%', position_id)
            user_id = user_result['user_id'] if user_result else None

        if not user_id:
            print("❌ Could not determine user_id")
            return

        # 2. Find all transactions mentioning this position
        print(f"\n📊 Searching transactions for position {position_id}...")

        tx_query = """
        SELECT
            id,
            tx_hash,
            tx_type,
            position_id,
            event_data,
            created_at,
            block_timestamp
        FROM transactions
        WHERE user_id = $1
        AND (
            position_id = $2
            OR event_data->>'nft_token_id' = $3
            OR event_data->>'token_id' = $3
            OR event_data->>'position_id' = $3
            OR event_data::text LIKE $4
        )
        ORDER BY created_at ASC
        """

        position_id_str = str(position_id)
        transactions = await conn.fetch(
            tx_query,
            user_id,
            position_id,
            position_id_str,
            f'%{position_id}%'
        )

        print(f"\nFound {len(transactions)} related transactions:")

        for tx in transactions:
            event_data = tx['event_data']
            if isinstance(event_data, str):
                try:
                    event_data = json.loads(event_data)
                except:
                    event_data = {}

            print(f"\n📝 {tx['tx_type']} - {tx['tx_hash'][:10]}...")
            print(f"   Created: {tx['created_at']}")
            print(f"   Position ID (column): {tx['position_id']}")

            # Check event_data for position references
            for key in ['nft_token_id', 'token_id', 'position_id']:
                if key in event_data:
                    print(f"   {key} (event_data): {event_data[key]}")

            if 'pool_name' in event_data:
                print(f"   Pool: {event_data['pool_name']}")
            if 'amount_usdc' in event_data:
                print(f"   Amount: {event_data['amount_usdc']} USDC")
            if 'description' in event_data:
                print(f"   Description: {event_data['description']}")

        # 3. Check for UNKNOWN transactions that might be position creations
        print(f"\n🔍 Checking for UNKNOWN transactions that might be position creation...")

        unknown_query = """
        SELECT
            id,
            tx_hash,
            event_data,
            created_at
        FROM transactions
        WHERE user_id = $1
        AND tx_type = 'UNKNOWN'
        AND event_data::text LIKE $2
        ORDER BY created_at DESC
        LIMIT 10
        """

        unknown_txs = await conn.fetch(unknown_query, user_id, f'%{position_id}%')

        if unknown_txs:
            print(f"\nFound {len(unknown_txs)} UNKNOWN transactions mentioning position {position_id}:")
            for tx in unknown_txs:
                print(f"   - {tx['tx_hash'][:10]}... at {tx['created_at']}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()


async def main():
    if len(sys.argv) < 2:
        position_id = 26241258  # Default to the position in question
        print(f"Using default position ID: {position_id}")
    else:
        position_id = int(sys.argv[1])

    await find_position_creation(position_id)


if __name__ == "__main__":
    asyncio.run(main())