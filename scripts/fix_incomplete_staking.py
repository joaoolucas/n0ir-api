#!/usr/bin/env python3
"""
Fix incomplete STAKING transactions that are missing NFT token ID.
"""

import asyncio
import asyncpg
import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


async def fix_incomplete_staking():
    """Find and mark incomplete STAKING transactions."""

    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        database_url = os.getenv('DATABASE_PRIVATE_URL')

    if not database_url:
        print("❌ No database URL found in environment")
        return

    conn = await asyncpg.connect(database_url)

    try:
        print("="*60)
        print("FIXING INCOMPLETE STAKING TRANSACTIONS")
        print("="*60)

        # Find STAKING transactions without position_id
        query = """
        SELECT
            t.id,
            t.tx_hash,
            t.user_id,
            t.position_id,
            t.event_data,
            t.created_at
        FROM transactions t
        WHERE t.tx_type = 'STAKING'
        AND t.position_id IS NULL
        ORDER BY t.created_at DESC
        """

        incomplete = await conn.fetch(query)

        print(f"\n📊 Found {len(incomplete)} incomplete STAKING transactions")

        for tx in incomplete:
            tx_id = tx['id']
            tx_hash = tx['tx_hash']
            event_data = tx['event_data'] or {}

            # Parse event_data if it's a string
            if isinstance(event_data, str):
                try:
                    event_data = json.loads(event_data)
                except:
                    event_data = {}

            print(f"\n📝 Transaction: {tx_hash[:10]}...")
            print(f"   Created: {tx['created_at']}")
            print(f"   Gauge: {event_data.get('gauge_address', 'Unknown')}")

            # Mark as needs manual review
            update_query = """
            UPDATE transactions
            SET
                event_data = jsonb_set(
                    jsonb_set(
                        event_data,
                        '{needs_manual_review}',
                        'true'
                    ),
                    '{incomplete_reason}',
                    '"No NFT token ID could be determined from transaction"'
                )
            WHERE id = $1
            RETURNING id
            """

            result = await conn.fetchval(update_query, tx_id)

            if result:
                print(f"   ✅ Marked for manual review")
            else:
                print(f"   ❌ Failed to update")

        print(f"\n✅ Processed {len(incomplete)} incomplete STAKING transactions")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()


async def main():
    await fix_incomplete_staking()


if __name__ == "__main__":
    asyncio.run(main())