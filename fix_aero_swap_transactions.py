#!/usr/bin/env python3
"""Fix transactions incorrectly categorized as POSITION_CREATED that should be AERO_SWAP."""

import asyncio
import asyncpg
import json
from decimal import Decimal

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def fix_aero_swaps():
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # Find transactions that should be AERO_SWAP
        # Pattern: aero_out > 0, usdc_in > 0, usdc_out = 0
        query = """
        SELECT id, tx_hash, tx_type, event_data
        FROM transactions
        WHERE tx_type = 'POSITION_CREATED'
        AND event_data IS NOT NULL
        AND (event_data->>'aero_out')::numeric > 0
        AND (event_data->>'usdc_in')::numeric > 0
        AND COALESCE((event_data->>'usdc_out')::numeric, 0) = 0
        """

        transactions = await conn.fetch(query)

        print(f"Found {len(transactions)} transactions to fix")

        fixed_count = 0
        for tx in transactions:
            tx_id = tx['id']
            tx_hash = tx['tx_hash']
            event_data = tx['event_data']

            # Update transaction type
            update_query = """
            UPDATE transactions
            SET tx_type = 'AERO_SWAP',
                event_data = event_data || '{"description": "Swapped AERO for USDC"}'::jsonb
            WHERE id = $1
            """

            await conn.execute(update_query, tx_id)
            fixed_count += 1

            print(f"  Fixed transaction {tx_hash[:10]}...")
            print(f"    AERO out: {event_data.get('aero_out', 0)}")
            print(f"    USDC in: {event_data.get('usdc_in', 0)}")

        print(f"\n✓ Fixed {fixed_count} transactions")

        # Also look for the specific transaction mentioned
        specific_hash = "0x9e09ffc182c258538253064cca4a95bec3a5292b5f21792e75c82df0ebdf649d"
        specific_query = """
        UPDATE transactions
        SET tx_type = 'AERO_SWAP',
            event_data = event_data || '{"description": "Swapped AERO for USDC"}'::jsonb
        WHERE tx_hash = $1
        AND tx_type = 'POSITION_CREATED'
        """

        result = await conn.execute(specific_query, specific_hash)
        if result.split()[-1] != '0':
            print(f"✓ Also fixed specific transaction {specific_hash[:10]}...")

        return True

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if conn:
            await conn.close()

async def main():
    print("Fixing AERO_SWAP transactions...")
    print("=" * 60)
    await fix_aero_swaps()

if __name__ == "__main__":
    asyncio.run(main())