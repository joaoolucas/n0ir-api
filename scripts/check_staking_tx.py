#!/usr/bin/env python3
"""Check the STAKING transaction details."""

import asyncio
import asyncpg
import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


async def check_staking():
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        database_url = os.getenv('DATABASE_PRIVATE_URL')

    conn = await asyncpg.connect(database_url)

    try:
        # Check the STAKING transaction
        query = """
        SELECT
            tx_hash,
            tx_type,
            position_id,
            event_data
        FROM transactions
        WHERE tx_hash = '0xc0a86e089b66af75094f83a2dad6680801ef5e8efefb5ba25e24654e41d5a5be'
        """

        result = await conn.fetchrow(query)

        if result:
            print("✅ STAKING Transaction found!")
            print(f"   TX Type: {result['tx_type']}")
            print(f"   Position ID (column): {result['position_id']}")

            event_data = result['event_data']
            if isinstance(event_data, str):
                event_data = json.loads(event_data)

            print(f"\n📊 Event Data:")
            for key, value in event_data.items():
                print(f"   {key}: {value}")

            # Check what NFT token ID should be
            if 'gauge_address' in event_data:
                gauge = event_data['gauge_address']
                print(f"\n🔍 Looking for NFT transfers to gauge {gauge}...")

                # Find NFT transfers in same time period
                nft_query = """
                SELECT
                    tx_hash,
                    event_data
                FROM transactions
                WHERE user_id = '0xAC65e18F7f4e5eDEA297b9E5433C153f1d9a7764'
                AND created_at > '2025-09-21 03:30:00'
                AND created_at < '2025-09-21 03:40:00'
                AND event_data::text LIKE '%26241258%'
                ORDER BY created_at
                """

                nfts = await conn.fetch(nft_query)
                print(f"\nFound {len(nfts)} transactions mentioning NFT 26241258 in same timeframe")
                for tx in nfts:
                    print(f"   - {tx['tx_hash'][:10]}...")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(check_staking())