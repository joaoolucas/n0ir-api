#!/usr/bin/env python3
"""Update existing transactions to populate the position_id column from event_data."""

import asyncio
import asyncpg
import json

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def update_transaction_position_ids():
    """Update position_id column for existing transactions."""
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # First, find all transactions with position-related types
        query = """
        SELECT id, tx_hash, tx_type, event_data, position_id
        FROM transactions
        WHERE tx_type IN ('POSITION_CREATED', 'POSITION_CLOSED', 'STAKING')
        AND position_id IS NULL
        """
        transactions = await conn.fetch(query)

        print(f"Found {len(transactions)} transactions without position_id")

        updated_count = 0
        for tx in transactions:
            event_data = tx['event_data']
            if isinstance(event_data, str):
                try:
                    event_data = json.loads(event_data)
                except:
                    continue

            # Look for nft_token_id in event_data
            nft_token_id = None
            if isinstance(event_data, dict):
                nft_token_id = event_data.get('nft_token_id') or event_data.get('tokenId') or event_data.get('token_id')

            if nft_token_id:
                # Update the position_id column
                update_query = """
                UPDATE transactions
                SET position_id = $1
                WHERE id = $2
                """
                await conn.execute(update_query, int(nft_token_id), tx['id'])
                updated_count += 1
                print(f"✅ Updated transaction {tx['tx_hash'][:10]}... with position_id={nft_token_id}")

        print(f"\n✅ Updated {updated_count} transactions with position_id")

        # Also ensure positions are closed for POSITION_CLOSED transactions
        close_query = """
        SELECT t.tx_hash, t.position_id, t.event_data, t.user_id
        FROM transactions t
        WHERE t.tx_type = 'POSITION_CLOSED'
        AND t.position_id IS NOT NULL
        """
        closed_txs = await conn.fetch(close_query)

        closed_count = 0
        for tx in closed_txs:
            # Check if position is still ACTIVE
            position_check = """
            SELECT token_id, status
            FROM positions
            WHERE token_id = $1
            """
            position = await conn.fetchrow(position_check, tx['position_id'])

            if position and position['status'] == 'ACTIVE':
                # Parse event_data for final value
                event_data = tx['event_data']
                if isinstance(event_data, str):
                    try:
                        event_data = json.loads(event_data)
                    except:
                        event_data = {}

                amount_usdc = event_data.get('amount_usdc', 0)

                # Close the position
                update_position = """
                UPDATE positions
                SET status = 'CLOSED',
                    exit_date = NOW(),
                    exit_tx_hash = $1,
                    current_value_usdc = $2,
                    realized_pnl_usdc = $2 - entry_amount_usdc
                WHERE token_id = $3
                """
                await conn.execute(update_position, tx['tx_hash'], amount_usdc, tx['position_id'])
                closed_count += 1
                print(f"✅ Closed position {tx['position_id']} for POSITION_CLOSED tx {tx['tx_hash'][:10]}...")

        if closed_count > 0:
            print(f"\n✅ Closed {closed_count} positions")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(update_transaction_position_ids())