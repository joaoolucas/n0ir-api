#!/usr/bin/env python3
"""Fix status for position 26227996 which should be ACTIVE."""

import asyncio
import asyncpg

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def fix_position_status():
    """Fix status for position 26227996."""
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # First check current status
        check_query = """
        SELECT token_id, status, exit_date, realized_pnl_usdc
        FROM positions
        WHERE token_id = 26227996
        """
        result = await conn.fetchrow(check_query)

        if result:
            print(f"Current status for position 26227996:")
            print(f"  status: {result['status']}")
            print(f"  exit_date: {result['exit_date']}")
            print(f"  realized_pnl_usdc: {result['realized_pnl_usdc']}")

            if result['status'] != 'ACTIVE':
                # Update to ACTIVE status
                update_query = """
                UPDATE positions
                SET status = 'ACTIVE',
                    exit_date = NULL,
                    exit_tx_hash = NULL,
                    realized_pnl_usdc = 0
                WHERE token_id = 26227996
                """
                await conn.execute(update_query)
                print("\n✅ Updated position 26227996 to ACTIVE status")

                # Verify the update
                verify = await conn.fetchrow(check_query)
                print(f"\nUpdated status for position 26227996:")
                print(f"  status: {verify['status']}")
                print(f"  exit_date: {verify['exit_date']}")
                print(f"  realized_pnl_usdc: {verify['realized_pnl_usdc']}")
            else:
                print("\n✅ Position already has ACTIVE status")
        else:
            print("❌ Position 26227996 not found")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_position_status())