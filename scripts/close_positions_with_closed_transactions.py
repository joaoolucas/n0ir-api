#!/usr/bin/env python3
"""
Script to close positions that have POSITION_CLOSED transactions but are still ACTIVE.
This fixes positions that weren't closed due to the bug in position closing logic.
"""

import asyncio
import asyncpg
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


async def close_positions_with_closed_transactions():
    """Find and close positions that have POSITION_CLOSED transactions."""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        database_url = os.getenv('DATABASE_PRIVATE_URL')

    if not database_url:
        print("❌ No database URL found in environment")
        return

    conn = await asyncpg.connect(database_url)

    try:
        # Find POSITION_CLOSED transactions where the position is still ACTIVE
        query = """
        SELECT
            t.id as transaction_id,
            t.tx_hash,
            t.user_id,
            t.position_id,
            t.event_data,
            t.block_timestamp,
            p.token_id,
            p.status as position_status,
            p.entry_amount_usdc,
            p.pool_name
        FROM transactions t
        INNER JOIN positions p ON p.token_id = t.position_id AND p.user_id = t.user_id
        WHERE t.tx_type = 'POSITION_CLOSED'
        AND p.status = 'ACTIVE'
        AND t.position_id IS NOT NULL
        ORDER BY t.created_at DESC
        """

        mismatched = await conn.fetch(query)

        print(f"\n📊 Found {len(mismatched)} positions that need closing")

        if not mismatched:
            print("✅ All positions with POSITION_CLOSED transactions are properly closed")
            return

        # Process each position
        for row in mismatched:
            position_id = row['token_id']
            user_id = row['user_id']
            tx_hash = row['tx_hash']
            event_data = row['event_data'] or {}

            # Get the return amount from event data
            amount_returned = event_data.get('amount_usdc', 0)
            if isinstance(amount_returned, str):
                amount_returned = float(amount_returned)

            # If no amount in event_data, try other fields
            if not amount_returned:
                amount_returned = event_data.get('usdc_in', 0)

            entry_amount = float(row['entry_amount_usdc'] or 0)
            realized_pnl = amount_returned - entry_amount

            print(f"\n🔧 Closing position {position_id}:")
            print(f"   User: {user_id}")
            print(f"   Pool: {row['pool_name']}")
            print(f"   Entry: {entry_amount:.2f} USDC")
            print(f"   Return: {amount_returned:.2f} USDC")
            print(f"   PnL: {realized_pnl:+.2f} USDC")
            print(f"   TX: {tx_hash[:10]}...")

            # Update the position to CLOSED
            update_query = """
            UPDATE positions
            SET
                status = 'CLOSED',
                exit_date = COALESCE($1, NOW()),
                exit_tx_hash = $2,
                realized_pnl_usdc = $3,
                current_value_usdc = $4,
                updated_at = NOW()
            WHERE token_id = $5 AND user_id = $6 AND status = 'ACTIVE'
            RETURNING token_id
            """

            exit_date = row['block_timestamp'] or datetime.utcnow()

            result = await conn.fetchval(
                update_query,
                exit_date,
                tx_hash,
                realized_pnl,
                amount_returned,
                position_id,
                user_id
            )

            if result:
                print(f"   ✅ Position {position_id} closed successfully")
            else:
                print(f"   ⚠️ Failed to close position {position_id}")

        # Verify the fixes
        print("\n" + "="*60)
        print("VERIFICATION")
        print("="*60)

        verify_query = """
        SELECT
            COUNT(*) as still_active
        FROM transactions t
        INNER JOIN positions p ON p.token_id = t.position_id AND p.user_id = t.user_id
        WHERE t.tx_type = 'POSITION_CLOSED'
        AND p.status = 'ACTIVE'
        AND t.position_id IS NOT NULL
        """

        still_active = await conn.fetchval(verify_query)

        if still_active == 0:
            print("✅ All positions successfully closed!")
        else:
            print(f"⚠️ {still_active} positions still need attention")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()


async def main():
    print("="*60)
    print("POSITION CLOSING FIX")
    print("="*60)
    print("\nThis script closes positions that have POSITION_CLOSED")
    print("transactions but are still marked as ACTIVE.")

    await close_positions_with_closed_transactions()

    print("\n✨ Script completed")


if __name__ == "__main__":
    asyncio.run(main())