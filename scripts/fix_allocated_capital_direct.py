#!/usr/bin/env python3
"""Fix allocated capital by directly connecting to database."""

import asyncpg
import asyncio

async def fix_allocated_capital():
    """Fix allocated capital for user."""
    database_url = "postgresql://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway"
    user_id = "0x42dda1966E04021cE096172F3cd4fAaC0cDfeccf"

    conn = await asyncpg.connect(database_url)

    try:
        # Get user's current USDC balance
        user = await conn.fetchrow(
            "SELECT user_id, usdc_balance FROM users WHERE user_id = $1",
            user_id
        )

        if not user:
            print(f"User {user_id} not found")
            return

        # Calculate total portfolio value (usdc_balance + active positions value)
        positions_value = await conn.fetchval(
            """
            SELECT COALESCE(SUM(current_value_usdc), 0)
            FROM positions
            WHERE user_id = $1 AND status = 'ACTIVE'
            """,
            user_id
        )

        total_portfolio_value = user['usdc_balance'] + (positions_value or 0)

        # Get closed positions PnL
        closed_positions = await conn.fetch(
            """
            SELECT token_id, entry_amount_usdc, realized_pnl_usdc, exit_date
            FROM positions
            WHERE user_id = $1 AND status = 'CLOSED'
            ORDER BY exit_date DESC
            LIMIT 5
            """,
            user_id
        )

        print(f"User: {user['user_id']}")
        print(f"USDC balance in DB: ${user['usdc_balance']}")
        print(f"Active positions value: ${positions_value or 0}")
        print(f"Total portfolio value: ${total_portfolio_value}")

        if closed_positions:
            print(f"\nRecent closed positions:")
            for pos in closed_positions:
                print(f"  Token {pos['token_id']}: Entry=${pos['entry_amount_usdc']}, PnL=${pos['realized_pnl_usdc']}, Exited={pos['exit_date']}")

        # Get current strategy
        strategy = await conn.fetchrow(
            """
            SELECT strategy_type, allocated_capital_usd, deployed_capital_usd
            FROM user_strategies
            WHERE user_id = $1 AND status = 'active'
            """,
            user_id
        )

        if not strategy:
            print("No active strategy found")
            return

        print(f"\nCurrent strategy: {strategy['strategy_type']}")
        print(f"Current allocated capital: ${strategy['allocated_capital_usd']}")
        print(f"Deployed capital: ${strategy['deployed_capital_usd']}")

        # The correct balance is $1000 based on the actual wallet
        # Update both usdc_balance and allocated_capital
        correct_balance = 1000.0
        print(f"\n⚠️  Database shows ${user['usdc_balance']}, but actual wallet has ${correct_balance}")
        print(f"Updating usdc_balance to: ${correct_balance}")

        await conn.execute(
            """
            UPDATE users
            SET usdc_balance = $1
            WHERE user_id = $2
            """,
            correct_balance,
            user_id
        )

        await conn.execute(
            """
            UPDATE user_strategies
            SET allocated_capital_usd = $1, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = $2 AND status = 'active'
            """,
            correct_balance,
            user_id
        )

        # Verify
        updated = await conn.fetchrow(
            """
            SELECT strategy_type, allocated_capital_usd, deployed_capital_usd
            FROM user_strategies
            WHERE user_id = $1 AND status = 'active'
            """,
            user_id
        )

        print(f"\n✓ Updated!")
        print(f"New allocated capital: ${updated['allocated_capital_usd']}")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_allocated_capital())
