#!/usr/bin/env python3
"""Check the actual schema of the transactions table"""

import asyncio
import asyncpg

DATABASE_URL = "postgresql://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway"

async def main():
    conn = await asyncpg.connect(DATABASE_URL)

    try:
        # Get table columns
        query = """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'transactions'
        ORDER BY ordinal_position;
        """

        rows = await conn.fetch(query)

        print("Transactions table schema:")
        print("-" * 50)
        for row in rows:
            print(f"{row['column_name']:20} {row['data_type']:20} {row['is_nullable']}")

        # Now check if the transaction exists using correct column names
        print("\n" + "=" * 50)
        print("Checking for transaction e509fbad-d00c-4f0f-a04f-b962dd6ef07f")
        print("=" * 50)

        tx_query = """
        SELECT * FROM transactions
        WHERE tx_hash = $1
        """

        tx_row = await conn.fetchrow(tx_query, "e509fbad-d00c-4f0f-a04f-b962dd6ef07f")

        if tx_row:
            print("Transaction found!")
            for key, value in tx_row.items():
                print(f"{key}: {value}")
        else:
            print("Transaction not found in database")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())