#!/usr/bin/env python3
"""Check transaction amount fields."""

import asyncio
import asyncpg
import json

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def check_transactions():
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        user_id = "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51"

        # Get a sample transaction
        query = """
        SELECT id, tx_hash, tx_type, event_data
        FROM transactions
        WHERE user_id = $1
        AND tx_type IN ('DEPOSIT', 'WITHDRAW')
        LIMIT 5
        """
        transactions = await conn.fetch(query, user_id)

        for tx in transactions:
            print(f"\nTransaction {str(tx['id'])[:8]}...")
            print(f"  Type: {tx['tx_type']}")
            print(f"  Hash: {tx['tx_hash'][:10]}...")

            event_data = tx['event_data']
            if isinstance(event_data, str):
                event_data = json.loads(event_data)

            if event_data:
                print(f"  Event Data:")
                for key, value in event_data.items():
                    if 'amount' in key.lower() or 'usdc' in key.lower():
                        print(f"    {key}: {value}")

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
    print("Checking transaction amounts...")
    print("=" * 60)
    await check_transactions()

if __name__ == "__main__":
    asyncio.run(main())