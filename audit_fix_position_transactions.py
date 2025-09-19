#!/usr/bin/env python3
"""Audit and fix POSITION_CREATED and POSITION_CLOSED transactions missing nft_token_id."""

import asyncio
import asyncpg
from datetime import datetime, timedelta
from decimal import Decimal

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def audit_and_fix():
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        print("Auditing POSITION_CREATED and POSITION_CLOSED transactions...")
        print("=" * 80)

        # Find all position transactions without nft_token_id
        query = """
        SELECT
            t.tx_hash,
            t.user_id,
            t.tx_type,
            t.event_data,
            t.created_at,
            t.block_timestamp
        FROM transactions t
        WHERE t.tx_type IN ('POSITION_CREATED', 'POSITION_CLOSED')
        AND (t.event_data->>'nft_token_id' IS NULL OR t.event_data->>'nft_token_id' = '')
        ORDER BY t.created_at DESC
        """

        transactions = await conn.fetch(query)
        print(f"Found {len(transactions)} position transactions missing nft_token_id\n")

        fixed_count = 0

        for tx in transactions:
            print(f"\n{tx['tx_type']} - {tx['tx_hash'][:10]}... at {tx['created_at']}")
            print(f"  User: {tx['user_id']}")

            # Handle event_data that might be string or dict
            event_data = tx['event_data']
            if isinstance(event_data, str):
                import json
                try:
                    event_data = json.loads(event_data)
                except:
                    event_data = {}
            elif event_data is None:
                event_data = {}

            pool = event_data.get('pool', '')
            amount = Decimal(str(event_data.get('amount_usdc', 0)))

            print(f"  Pool: {pool}")
            print(f"  Amount: {amount} USDC")

            # Try to match with a position based on timing and amount
            if tx['tx_type'] == 'POSITION_CREATED':
                # Find position created around the same time with matching amount
                position_query = """
                SELECT token_id, entry_amount_usdc, pool_address, entry_date
                FROM positions
                WHERE user_id = $1
                AND ABS(entry_amount_usdc - $2) < 0.01
                AND (
                    (entry_date IS NOT NULL AND ABS(EXTRACT(EPOCH FROM (entry_date - $3))) < 300)
                    OR (entry_date IS NULL AND ABS(EXTRACT(EPOCH FROM (created_at - $3))) < 300)
                )
                ORDER BY ABS(entry_amount_usdc - $2), ABS(EXTRACT(EPOCH FROM (COALESCE(entry_date, created_at) - $3)))
                LIMIT 1
                """

                timestamp = tx['block_timestamp'] or tx['created_at']
                position = await conn.fetchrow(position_query, tx['user_id'], amount, timestamp)

                if position:
                    print(f"  ✓ Matched with position {position['token_id']}")

                    # Update transaction with nft_token_id
                    update_query = """
                    UPDATE transactions
                    SET event_data = event_data || jsonb_build_object('nft_token_id', $2::text)
                    WHERE tx_hash = $1
                    """
                    await conn.execute(update_query, tx['tx_hash'], str(position['token_id']))
                    fixed_count += 1

                    # Also update position's entry_tx_hash if missing
                    update_pos_query = """
                    UPDATE positions
                    SET entry_tx_hash = $2
                    WHERE token_id = $1 AND entry_tx_hash IS NULL
                    """
                    await conn.execute(update_pos_query, position['token_id'], tx['tx_hash'])
                else:
                    print(f"  ✗ No matching position found")

            elif tx['tx_type'] == 'POSITION_CLOSED':
                # For POSITION_CLOSED, find recently closed position or position that should be closed
                position_query = """
                SELECT p.token_id, p.entry_amount_usdc, p.status, p.exit_date
                FROM positions p
                WHERE p.user_id = $1
                AND (
                    -- Already closed around this time
                    (p.status = 'CLOSED' AND p.exit_date IS NOT NULL
                     AND ABS(EXTRACT(EPOCH FROM (p.exit_date - $2))) < 300)
                    OR
                    -- Still active but created before this close transaction
                    (p.status = 'ACTIVE' AND p.created_at < $2
                     AND NOT EXISTS (
                         SELECT 1 FROM transactions t2
                         WHERE t2.tx_type = 'POSITION_CLOSED'
                         AND t2.event_data->>'nft_token_id' = p.token_id::text
                     ))
                )
                ORDER BY
                    CASE WHEN p.status = 'CLOSED' THEN 0 ELSE 1 END,
                    ABS(EXTRACT(EPOCH FROM (COALESCE(p.exit_date, p.created_at) - $2)))
                LIMIT 1
                """

                timestamp = tx['block_timestamp'] or tx['created_at']
                position = await conn.fetchrow(position_query, tx['user_id'], timestamp)

                if position:
                    print(f"  ✓ Matched with position {position['token_id']} (status: {position['status']})")

                    # Update transaction with nft_token_id
                    update_query = """
                    UPDATE transactions
                    SET event_data = event_data || jsonb_build_object('nft_token_id', $2::text)
                    WHERE tx_hash = $1
                    """
                    await conn.execute(update_query, tx['tx_hash'], str(position['token_id']))
                    fixed_count += 1

                    # If position is still ACTIVE, close it
                    if position['status'] == 'ACTIVE':
                        print(f"    → Closing position {position['token_id']}")

                        realized_pnl = amount - position['entry_amount_usdc']

                        close_query = """
                        UPDATE positions
                        SET
                            status = 'CLOSED',
                            exit_date = $2,
                            exit_tx_hash = $3,
                            realized_pnl_usdc = $4,
                            current_value_usdc = $5,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE token_id = $1
                        """
                        await conn.execute(
                            close_query,
                            position['token_id'],
                            timestamp,
                            tx['tx_hash'],
                            realized_pnl,
                            amount
                        )
                        print(f"    → Position closed with PnL: {realized_pnl} USDC")
                else:
                    print(f"  ✗ No matching position found")

        print(f"\n{'=' * 80}")
        print(f"Summary: Fixed {fixed_count} out of {len(transactions)} transactions")

        # Final check for orphaned positions
        print("\nChecking for positions that should be closed...")
        orphan_query = """
        SELECT p.token_id, p.user_id, p.status, p.entry_amount_usdc
        FROM positions p
        WHERE p.status = 'ACTIVE'
        AND EXISTS (
            SELECT 1 FROM transactions t
            WHERE t.user_id = p.user_id
            AND t.tx_type = 'POSITION_CLOSED'
            AND t.event_data->>'nft_token_id' = p.token_id::text
        )
        """

        orphans = await conn.fetch(orphan_query)
        if orphans:
            print(f"Found {len(orphans)} positions with POSITION_CLOSED transactions but still ACTIVE")
            for orphan in orphans:
                print(f"  Position {orphan['token_id']} for user {orphan['user_id'][:10]}...")
        else:
            print("No orphaned positions found")

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
    await audit_and_fix()

if __name__ == "__main__":
    asyncio.run(main())