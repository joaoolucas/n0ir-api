#!/usr/bin/env python3
"""Fix position 26164294 by linking it to the POSITION_CLOSED transaction."""

import asyncio
import asyncpg
from datetime import datetime
from decimal import Decimal

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def fix_position():
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        position_id = 26164294
        user_id = "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51"
        closed_tx_hash = "0x82bc6084d15307986e3fd74991183705bea93e7e98c55d391f1c73cffa0c847d"

        print(f"Fixing position {position_id}...")
        print("=" * 60)

        # Get the POSITION_CLOSED transaction
        tx_query = """
        SELECT tx_hash, event_data, created_at
        FROM transactions
        WHERE tx_hash = $1
        """
        closed_tx = await conn.fetchrow(tx_query, closed_tx_hash)

        if closed_tx:
            print(f"Found POSITION_CLOSED transaction: {closed_tx['tx_hash'][:10]}...")

            # Update the transaction to include the NFT token ID
            update_tx_query = """
            UPDATE transactions
            SET event_data = event_data || jsonb_build_object('nft_token_id', $2::text)
            WHERE tx_hash = $1
            """
            await conn.execute(update_tx_query, closed_tx_hash, str(position_id))
            print(f"  ✓ Added nft_token_id {position_id} to transaction")

            # Get position data
            pos_query = """
            SELECT token_id, status, entry_amount_usdc
            FROM positions
            WHERE token_id = $1 AND user_id = $2
            """
            position = await conn.fetchrow(pos_query, position_id, user_id)

            if position and position['status'] == 'ACTIVE':
                # Calculate realized PnL
                final_value = Decimal("50.059575")  # From the POSITION_CLOSED transaction
                realized_pnl = final_value - position['entry_amount_usdc']

                # Update position to CLOSED
                update_pos_query = """
                UPDATE positions
                SET
                    status = 'CLOSED',
                    exit_date = $3,
                    exit_tx_hash = $4,
                    realized_pnl_usdc = $5,
                    current_value_usdc = $6,
                    updated_at = CURRENT_TIMESTAMP
                WHERE token_id = $1 AND user_id = $2
                """

                await conn.execute(
                    update_pos_query,
                    position_id,
                    user_id,
                    closed_tx['created_at'],
                    closed_tx_hash,
                    realized_pnl,
                    final_value
                )

                print(f"\n✓ Position {position_id} marked as CLOSED")
                print(f"  Entry: {position['entry_amount_usdc']} USDC")
                print(f"  Exit: {final_value} USDC")
                print(f"  Realized PnL: {realized_pnl} USDC")
            else:
                print(f"Position {position_id} not found or already closed")
        else:
            print(f"Transaction {closed_tx_hash} not found")

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
    await fix_position()

if __name__ == "__main__":
    asyncio.run(main())