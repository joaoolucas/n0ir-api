#!/usr/bin/env python3
"""Verify the transaction fix."""

import asyncio
import asyncpg
import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


async def verify_fix():
    """Verify the transaction was fixed."""

    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        database_url = os.getenv('DATABASE_PRIVATE_URL')

    if not database_url:
        print("❌ No database URL found in environment")
        return

    conn = await asyncpg.connect(database_url)

    try:
        # Check the specific transaction
        query = """
        SELECT
            id,
            tx_hash,
            tx_type,
            position_id,
            event_data
        FROM transactions
        WHERE tx_hash = '0xf725a10996cdba4ea34962fd5f5db9ef52c4d59d37cb17350dd4d8721cffb053'
        """

        result = await conn.fetchrow(query)

        if result:
            print("✅ Transaction found!")
            print(f"   TX Type: {result['tx_type']}")
            print(f"   Position ID: {result['position_id']}")

            # Parse event_data to check description
            event_data = result['event_data']
            if isinstance(event_data, str):
                event_data = json.loads(event_data)

            if 'description' in event_data:
                print(f"   Description: {event_data['description']}")
            if 'corrected_from' in event_data:
                print(f"   Corrected from: {event_data['corrected_from']}")

            if result['tx_type'] == 'DEPOSIT':
                print("\n✅ Transaction successfully fixed to DEPOSIT!")
            else:
                print(f"\n⚠️ Transaction still shows as {result['tx_type']}")
        else:
            print("❌ Transaction not found")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(verify_fix())