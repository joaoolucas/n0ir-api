#!/usr/bin/env python3
"""Script to check transaction e509fbad-d00c-4f0f-a04f-b962dd6ef07f in Railway database"""

import asyncio
import asyncpg
import json
from datetime import datetime
from decimal import Decimal


DATABASE_URL = "postgresql://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway"


async def main():
    """Check the transaction in the database"""

    tx_hash = "e509fbad-d00c-4f0f-a04f-b962dd6ef07f"

    # Connect to database
    conn = await asyncpg.connect(DATABASE_URL)

    try:
        # Query the transaction
        query = """
        SELECT
            tx_hash,
            user_id,
            tx_type,
            amount_usdc,
            status,
            position_id,
            block_number,
            block_timestamp,
            event_data,
            created_at
        FROM transactions
        WHERE tx_hash = $1
        """

        row = await conn.fetchrow(query, tx_hash)

        if not row:
            print(f"Transaction {tx_hash} not found in database")
            return

        print("=" * 80)
        print(f"Transaction found: {tx_hash}")
        print("=" * 80)

        # Display transaction details
        print(f"User ID: {row['user_id']}")
        print(f"Type: {row['tx_type']}")
        print(f"Amount USDC: {row['amount_usdc']}")
        print(f"Status: {row['status']}")
        print(f"Position ID: {row['position_id']}")
        print(f"Block Number: {row['block_number']}")
        print(f"Block Timestamp: {row['block_timestamp']}")
        print(f"Created At: {row['created_at']}")

        if row['event_data']:
            print("\nEvent Data:")
            print(json.dumps(row['event_data'], indent=2, default=str))

        # Analyze the issue
        print("\n" + "=" * 80)
        print("Analysis:")
        print("=" * 80)

        issues = []

        # Check 1: Zero or negative amount
        if row['amount_usdc'] <= 0:
            issues.append(f"Invalid amount: {row['amount_usdc']} USDC (should be positive)")

        # Check 2: No position linked for POSITION_CREATED
        if row['tx_type'] == "POSITION_CREATED" and not row['position_id']:
            issues.append("POSITION_CREATED transaction has no linked position")

        # Check 3: Check event data for net amount
        if row['event_data']:
            event_data = row['event_data']
            usdc_in = event_data.get('usdc_in', 0)
            usdc_out = event_data.get('usdc_out', 0)

            # Convert to numbers if they're strings
            if isinstance(usdc_in, str):
                usdc_in = float(usdc_in) if usdc_in else 0
            if isinstance(usdc_out, str):
                usdc_out = float(usdc_out) if usdc_out else 0

            # Calculate net amount
            if usdc_in or usdc_out:
                net_amount_raw = usdc_out - usdc_in
                net_amount_usdc = net_amount_raw / 1_000_000 if net_amount_raw else 0

                if net_amount_usdc <= 0:
                    issues.append(f"Net USDC amount is zero or negative: usdc_out({usdc_out}) - usdc_in({usdc_in}) = {net_amount_usdc} USDC")

            # Check for NFT token ID
            if not event_data.get('nft_token_id') and not event_data.get('token_id'):
                issues.append("No NFT token ID found in event data")

        if issues:
            print("Issues found:")
            for issue in issues:
                print(f"  ❌ {issue}")

            print("\n" + "=" * 80)
            print("Recommendation:")
            print("=" * 80)
            print("This transaction appears to be invalid because:")
            print("1. It represents a position interaction with zero net investment")
            print("2. The WalletTransactionService should filter such transactions (line 652-654)")
            print("3. It was likely saved before the filtering logic was implemented")
            print("\nThis transaction should be removed from the database.")

            # Ask for confirmation to delete
            print("\n" + "=" * 80)
            print("DELETE QUERY:")
            print("=" * 80)
            print(f"DELETE FROM transactions WHERE tx_hash = '{tx_hash}';")

        else:
            print("✓ No obvious issues found with this transaction")

        # Check for similar invalid transactions
        print("\n" + "=" * 80)
        print("Checking for other potentially invalid POSITION_CREATED transactions...")
        print("=" * 80)

        query = """
        SELECT
            tx_hash,
            user_id,
            amount_usdc,
            position_id,
            event_data
        FROM transactions
        WHERE tx_type = 'POSITION_CREATED'
        AND (amount_usdc <= 0 OR position_id IS NULL)
        ORDER BY created_at DESC
        LIMIT 10
        """

        invalid_rows = await conn.fetch(query)

        if invalid_rows:
            print(f"Found {len(invalid_rows)} potentially invalid POSITION_CREATED transactions:")
            for row in invalid_rows:
                print(f"  - {row['tx_hash'][:20]}... | Amount: {row['amount_usdc']} | Position: {row['position_id']}")
        else:
            print("No other invalid POSITION_CREATED transactions found")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())