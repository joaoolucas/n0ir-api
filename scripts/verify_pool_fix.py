#!/usr/bin/env python3
"""Verify that pool addresses are correctly set for position transactions."""

import asyncio
import asyncpg
import json
from datetime import datetime, timedelta

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def verify_pool_addresses():
    """Check recent position transactions for pool address correctness."""
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # Get recent POSITION_CLOSED transactions
        query = """
        SELECT
            t.id,
            t.tx_hash,
            t.tx_type,
            t.event_data,
            t.position_id,
            t.created_at,
            p.pool_address as actual_pool_address,
            p.pool_name
        FROM transactions t
        LEFT JOIN positions p ON t.position_id = p.token_id
        WHERE t.tx_type IN ('POSITION_CLOSED', 'POSITION_CREATED')
            AND t.created_at > NOW() - INTERVAL '2 hours'
        ORDER BY t.created_at DESC
        LIMIT 10
        """

        rows = await conn.fetch(query)

        print(f"\nFound {len(rows)} recent position transactions\n")
        print("=" * 80)

        issues_found = 0

        for row in rows:
            event_data = row['event_data']
            if isinstance(event_data, str):
                event_data = json.loads(event_data)

            pool_in_event = event_data.get('pool')
            actual_pool = row['actual_pool_address']

            print(f"Transaction: {str(row['id'])[:8]}...")
            print(f"  Type: {row['tx_type']}")
            print(f"  Position ID: {row['position_id']}")
            print(f"  Pool Name: {row['pool_name']}")
            print(f"  Pool in event_data: {pool_in_event}")
            print(f"  Actual pool address: {actual_pool}")
            print(f"  Created: {row['created_at']}")

            # Check if pool addresses match (when both are present)
            if pool_in_event and actual_pool:
                if pool_in_event.lower() != actual_pool.lower():
                    print(f"  ⚠️  MISMATCH DETECTED!")
                    issues_found += 1
                else:
                    print(f"  ✅ Pool addresses match")
            elif pool_in_event is None and actual_pool:
                print(f"  ℹ️  Pool will be fetched from position data (correct behavior)")
            elif pool_in_event and not actual_pool:
                print(f"  ⚠️  Position not found for validation")

            print("-" * 40)

        print(f"\nSummary: Found {issues_found} mismatched pool addresses")

        # Also check if there are any NULL pool addresses in recent transactions
        null_pool_query = """
        SELECT COUNT(*) as count
        FROM transactions t
        WHERE t.tx_type IN ('POSITION_CLOSED', 'POSITION_CREATED')
            AND t.created_at > NOW() - INTERVAL '30 minutes'
            AND (t.event_data->>'pool') IS NULL
        """

        null_count = await conn.fetchval(null_pool_query)
        print(f"\nTransactions with NULL pool in last 30 min: {null_count}")
        print("(NULL pools are expected with the fix - they'll be fetched from position data)")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(verify_pool_addresses())