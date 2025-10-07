#!/usr/bin/env python3
"""Remove duplicate POSITION_CLOSED transaction."""

import asyncio
import asyncpg

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def remove_duplicate_transaction():
    """Remove the incorrect duplicate POSITION_CLOSED transaction."""
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # Transaction to remove
        tx_to_remove = 'a4f94390-e785-4139-961b-70cf88dc40ca'

        # First, verify both transactions exist and show their details
        check_query = """
        SELECT id, tx_type, position_id, amount_usdc, created_at, tx_hash
        FROM transactions
        WHERE position_id = 26227996
        AND tx_type = 'POSITION_CLOSED'
        ORDER BY created_at DESC
        """

        duplicates = await conn.fetch(check_query)

        print(f"Found {len(duplicates)} POSITION_CLOSED transactions for position 26227996:\n")

        for tx in duplicates:
            print(f"Transaction {str(tx['id'])[:8]}...:")
            print(f"  Created: {tx['created_at']}")
            print(f"  Amount: {tx['amount_usdc']} USDC")
            print(f"  TX Hash: {tx['tx_hash'][:10] if tx['tx_hash'] else 'None'}...")
            print()

        if len(duplicates) > 1:
            # Delete the duplicate transaction
            delete_query = """
            DELETE FROM transactions
            WHERE id = $1
            """

            await conn.execute(delete_query, tx_to_remove)
            print(f"❌ Deleted duplicate transaction {tx_to_remove[:8]}...")

            # Verify deletion
            verify_query = """
            SELECT COUNT(*) as count
            FROM transactions
            WHERE id = $1
            """
            result = await conn.fetchrow(verify_query, tx_to_remove)

            if result['count'] == 0:
                print(f"✅ Transaction {tx_to_remove[:8]}... successfully removed")
            else:
                print(f"⚠️ Transaction still exists in database")

            # Show remaining transactions
            remaining = await conn.fetch(check_query)
            print(f"\n📋 Remaining POSITION_CLOSED transactions for position 26227996: {len(remaining)}")

            for tx in remaining:
                print(f"  - {str(tx['id'])[:8]}... created at {tx['created_at']} ({tx['amount_usdc']} USDC)")

        else:
            print("✅ No duplicates found - only one POSITION_CLOSED transaction exists")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(remove_duplicate_transaction())