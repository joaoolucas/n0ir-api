#!/usr/bin/env python3
"""Fix positions that should be closed but are still marked as ACTIVE."""

import asyncio
import asyncpg
from datetime import datetime
from decimal import Decimal

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def fix_positions():
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # Positions that need to be closed
        positions_to_close = [
            (26163662, "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51"),
            (26162528, "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51")
        ]

        for token_id, user_id in positions_to_close:
            print(f"\nFixing position {token_id}...")

            # Get current position data
            query = """
            SELECT token_id, status, entry_amount_usdc, current_value_usdc
            FROM positions
            WHERE token_id = $1 AND user_id = $2
            """
            position = await conn.fetchrow(query, token_id, user_id)

            if position:
                if position['status'] == 'ACTIVE':
                    # Get the POSITION_CLOSED transaction for this NFT
                    tx_query = """
                    SELECT tx_hash, event_data, created_at
                    FROM transactions
                    WHERE tx_type = 'POSITION_CLOSED'
                    AND event_data->>'nft_token_id' = $1
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                    closed_tx = await conn.fetchrow(tx_query, str(token_id))

                    exit_hash = closed_tx['tx_hash'] if closed_tx else None
                    exit_date = closed_tx['created_at'] if closed_tx else datetime.utcnow()

                    # Get final value from transaction or use current value
                    final_value = Decimal(0)
                    if closed_tx and closed_tx['event_data'] and 'amount_usdc' in closed_tx['event_data']:
                        final_value = Decimal(str(closed_tx['event_data']['amount_usdc']))
                    elif position['current_value_usdc']:
                        final_value = position['current_value_usdc']

                    # Calculate realized PnL
                    realized_pnl = final_value - position['entry_amount_usdc']

                    # Update position to CLOSED
                    update_query = """
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
                        update_query,
                        token_id,
                        user_id,
                        exit_date,
                        exit_hash,
                        realized_pnl,
                        final_value
                    )

                    print(f"  ✓ Position {token_id} marked as CLOSED")
                    print(f"    Entry: {position['entry_amount_usdc']} USDC")
                    print(f"    Exit: {final_value} USDC")
                    print(f"    Realized PnL: {realized_pnl} USDC")
                    if closed_tx:
                        print(f"    Exit TX: {exit_hash[:10]}...")
                else:
                    print(f"  → Position {token_id} already {position['status']}")
            else:
                print(f"  → Position {token_id} not found")

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
    print("Fixing closed positions...")
    print("=" * 60)
    success = await fix_positions()
    if success:
        print("\n✅ Positions fixed successfully!")
    else:
        print("\n❌ Failed to fix positions")

if __name__ == "__main__":
    asyncio.run(main())