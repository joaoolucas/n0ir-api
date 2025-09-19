#!/usr/bin/env python3
"""Check user deposits and PNL calculation."""

import asyncio
import asyncpg
from decimal import Decimal

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def check_user_pnl():
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        user_id = "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51"

        # Get deposits
        deposits_query = """
        SELECT tx_hash, amount_usdc, created_at
        FROM transactions
        WHERE user_id = $1
        AND tx_type = 'DEPOSIT'
        AND status = 'CONFIRMED'
        ORDER BY created_at DESC
        """
        deposits = await conn.fetch(deposits_query, user_id)

        total_deposits = sum(Decimal(str(row['amount_usdc'])) if row['amount_usdc'] is not None else Decimal(0) for row in deposits)
        print(f"Total Deposits: ${total_deposits}")
        for row in deposits[:5]:  # Show first 5
            print(f"  - ${row['amount_usdc']} on {row['created_at']}")

        # Get withdrawals
        withdrawals_query = """
        SELECT tx_hash, amount_usdc, created_at
        FROM transactions
        WHERE user_id = $1
        AND tx_type IN ('WITHDRAW', 'WITHDRAWAL')
        AND status = 'CONFIRMED'
        ORDER BY created_at DESC
        """
        withdrawals = await conn.fetch(withdrawals_query, user_id)

        total_withdrawals = sum(Decimal(str(row['amount_usdc'])) if row['amount_usdc'] is not None else Decimal(0) for row in withdrawals)
        print(f"\nTotal Withdrawals: ${total_withdrawals}")
        for row in withdrawals[:5]:  # Show first 5
            print(f"  - ${row['amount_usdc']} on {row['created_at']}")

        net_deposits = total_deposits - total_withdrawals
        print(f"\nNet Deposits: ${net_deposits}")

        # Get current balance and positions value
        user_query = """
        SELECT usdc_balance
        FROM users
        WHERE user_id = $1
        """
        user = await conn.fetchrow(user_query, user_id)
        wallet_balance = Decimal(str(user['usdc_balance'])) if user else Decimal(0)

        positions_query = """
        SELECT token_id, current_value_usdc, entry_amount_usdc, realized_pnl_usdc, status
        FROM positions
        WHERE user_id = $1
        """
        positions = await conn.fetch(positions_query, user_id)

        active_positions_value = Decimal(0)
        total_entry_amount = Decimal(0)
        total_realized_pnl = Decimal(0)

        for pos in positions:
            if pos['status'] == 'ACTIVE':
                active_positions_value += Decimal(str(pos['current_value_usdc'] or 0))
                total_entry_amount += Decimal(str(pos['entry_amount_usdc'] or 0))
            total_realized_pnl += Decimal(str(pos['realized_pnl_usdc'] or 0))

        print(f"\nWallet Balance: ${wallet_balance}")
        print(f"Active Positions Value: ${active_positions_value}")
        print(f"Total Portfolio: ${wallet_balance + active_positions_value}")

        print(f"\nTotal Entry Amount: ${total_entry_amount}")
        print(f"Total Realized PNL: ${total_realized_pnl}")

        # Calculate PNL
        current_portfolio = wallet_balance + active_positions_value
        pnl_usdc = current_portfolio - net_deposits

        print(f"\nPNL Calculation:")
        print(f"  Current Portfolio: ${current_portfolio}")
        print(f"  - Net Deposits: ${net_deposits}")
        print(f"  = PNL: ${pnl_usdc}")

        # Calculate percentage
        if net_deposits > 0:
            pnl_pct = (pnl_usdc / net_deposits) * 100
            print(f"  PNL %: {pnl_pct:.2f}%")
        else:
            print(f"  PNL %: Cannot calculate (net deposits = ${net_deposits})")

            # Alternative calculation based on total deposits
            if total_deposits > 0:
                pnl_pct_alt = (pnl_usdc / total_deposits) * 100
                print(f"  PNL % (based on total deposits): {pnl_pct_alt:.2f}%")

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
    print("Checking user PNL calculation...")
    print("=" * 60)
    await check_user_pnl()

if __name__ == "__main__":
    asyncio.run(main())