#!/usr/bin/env python3
"""Remove transaction 78a83b2d-1c6d-4006-b903-802df3d6c8ab from database."""

import asyncio
import asyncpg

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def remove_transaction():
    """Remove the specified transaction."""
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        tx_to_remove = '78a83b2d-1c6d-4006-b903-802df3d6c8ab'

        # First check if the transaction exists and show its details
        check_query = """
        SELECT id, tx_type, position_id, amount_usdc, created_at, tx_hash, user_id
        FROM transactions
        WHERE id = $1
        """

        transaction = await conn.fetchrow(check_query, tx_to_remove)

        if transaction:
            print(f"Found transaction {tx_to_remove[:8]}...:")
            print(f"  Type: {transaction['tx_type']}")
            print(f"  User: {transaction['user_id']}")
            print(f"  Position ID: {transaction['position_id']}")
            print(f"  Amount: {transaction['amount_usdc']} USDC")
            print(f"  Created: {transaction['created_at']}")
            print(f"  TX Hash: {transaction['tx_hash'][:10] if transaction['tx_hash'] else 'None'}...")
            print()

            # Delete the transaction
            delete_query = """
            DELETE FROM transactions
            WHERE id = $1
            """

            await conn.execute(delete_query, tx_to_remove)
            print(f"❌ Deleted transaction {tx_to_remove[:8]}...")

            # Verify deletion
            verify_query = """
            SELECT COUNT(*) as count
            FROM transactions
            WHERE id = $1
            """
            result = await conn.fetchrow(verify_query, tx_to_remove)

            if result['count'] == 0:
                print(f"✅ Transaction {tx_to_remove[:8]}... successfully removed from database")
            else:
                print(f"⚠️ Transaction still exists in database")

        else:
            print(f"❌ Transaction {tx_to_remove} not found in database")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(remove_transaction())