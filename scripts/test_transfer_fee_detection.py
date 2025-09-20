#!/usr/bin/env python3
"""Test FEE_TRANSFER transaction type detection."""

import asyncio
import asyncpg
import json
from datetime import datetime

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def test_transfer_fee_detection():
    """Test if FEE_TRANSFER transactions are properly detected."""
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # Fee recipient address
        fee_recipient = '0xfD75350A7e2C4914908fF7E3082c45Af5762f5FE'

        # Check for existing FEE_TRANSFER transactions
        check_query = """
        SELECT id, tx_type, user_id, amount_usdc, event_data, created_at, tx_hash
        FROM transactions
        WHERE tx_type = 'FEE_TRANSFER'
        ORDER BY created_at DESC
        LIMIT 10
        """

        transfer_fee_txs = await conn.fetch(check_query)

        if transfer_fee_txs:
            print(f"✅ Found {len(transfer_fee_txs)} FEE_TRANSFER transactions:\n")

            for tx in transfer_fee_txs:
                event_data = tx['event_data']
                if isinstance(event_data, str):
                    event_data = json.loads(event_data)

                print(f"Transaction {str(tx['id'])[:8]}...:")
                print(f"  User: {tx['user_id']}")
                print(f"  Amount: {tx['amount_usdc']} USDC")
                print(f"  Created: {tx['created_at']}")
                print(f"  TX Hash: {tx['tx_hash'][:10] if tx['tx_hash'] else 'None'}...")
                print(f"  Fee Recipient: {event_data.get('fee_recipient', 'Not specified')}")
                print()
        else:
            print(f"⚠️ No FEE_TRANSFER transactions found yet")
            print(f"   Transactions to {fee_recipient} will be categorized as FEE_TRANSFER")
            print("\n   Looking for potential fee transfers that might not be categorized yet...")

            # Look for transfers to the fee recipient address in event_data
            search_query = """
            SELECT id, tx_type, user_id, amount_usdc, event_data, created_at
            FROM transactions
            WHERE event_data::text ILIKE $1
            ORDER BY created_at DESC
            LIMIT 10
            """

            potential_fee_txs = await conn.fetch(
                search_query,
                f'%{fee_recipient.lower()}%'
            )

            if potential_fee_txs:
                print(f"\n   Found {len(potential_fee_txs)} transactions involving fee recipient address:")
                for tx in potential_fee_txs:
                    print(f"   - {str(tx['id'])[:8]}... (type: {tx['tx_type']}, amount: {tx['amount_usdc']} USDC)")
            else:
                print("   No existing transactions found involving the fee recipient address")

        # Summary of transaction types
        print("\n📊 Transaction Type Summary:")
        summary_query = """
        SELECT tx_type, COUNT(*) as count
        FROM transactions
        GROUP BY tx_type
        ORDER BY count DESC
        """

        summary = await conn.fetch(summary_query)
        for row in summary:
            print(f"  {row['tx_type']}: {row['count']} transactions")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(test_transfer_fee_detection())