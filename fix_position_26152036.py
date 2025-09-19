#!/usr/bin/env python3
"""Fix position 26152036 - mark as closed."""

import asyncio
import asyncpg
from datetime import datetime, timezone

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def fix_position():
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        position_id = 26152036
        user_id = "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51"

        # Check current status
        query = """
        SELECT token_id, status, entry_amount_usdc, current_value_usdc, exit_date
        FROM positions
        WHERE token_id = $1 AND user_id = $2
        """
        position = await conn.fetchrow(query, position_id, user_id)

        if position:
            print(f"Current status: {position['status']}")
            print(f"Entry amount: {position['entry_amount_usdc']}")
            print(f"Current value: {position['current_value_usdc']}")
            print(f"Exit date: {position['exit_date']}")

            if position['status'] == 'ACTIVE':
                # Update position to CLOSED
                update_query = """
                UPDATE positions
                SET status = 'CLOSED',
                    exit_date = $1,
                    current_value_usdc = 0,
                    realized_pnl_usdc = entry_amount_usdc * -1,
                    updated_at = $1
                WHERE token_id = $2 AND user_id = $3
                """

                exit_date = datetime.utcnow()  # Use naive datetime for PostgreSQL
                await conn.execute(update_query, exit_date, position_id, user_id)
                print(f"\n✓ Position {position_id} marked as CLOSED")
                print(f"  Exit date: {exit_date}")
                print(f"  Realized PNL: -{position['entry_amount_usdc']}")
            else:
                print(f"\nPosition is already {position['status']}")
        else:
            print(f"Position {position_id} not found for user {user_id}")

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
    print("Fixing position 26152036...")
    print("=" * 60)
    await fix_position()

if __name__ == "__main__":
    asyncio.run(main())