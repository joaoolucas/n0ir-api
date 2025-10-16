#!/usr/bin/env python3
"""Fix allocated_capital and deployed_capital for all active users."""

import asyncpg
import asyncio
from decimal import Decimal

async def fix_all_active_users():
    """Fix all active users with mismatched balances."""
    database_url = "postgresql://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway"

    conn = await asyncpg.connect(database_url)

    try:
        # Get all users with active strategies
        users_with_strategies = await conn.fetch(
            """
            SELECT DISTINCT u.user_id, u.usdc_balance, u.cdp_wallet_address
            FROM users u
            JOIN user_strategies us ON u.user_id = us.user_id
            WHERE us.status = 'active'
            ORDER BY u.user_id
            """
        )

        print(f"Found {len(users_with_strategies)} active users with strategies\n")
        print("="*80)

        for user in users_with_strategies:
            user_id = user['user_id']
            usdc_balance = user['usdc_balance']

            print(f"\n👤 User: {user_id}")
            print(f"   Wallet: {user['cdp_wallet_address']}")
            print(f"   USDC Balance: ${usdc_balance}")

            # Get active positions and their values
            active_positions = await conn.fetch(
                """
                SELECT token_id, entry_amount_usdc, current_value_usdc, strategy_type
                FROM positions
                WHERE user_id = $1 AND status = 'ACTIVE'
                """,
                user_id
            )

            # Calculate total deployed capital (sum of entry amounts)
            total_deployed = sum(Decimal(str(p['entry_amount_usdc'])) for p in active_positions)

            # Calculate total positions current value
            positions_value = sum(
                Decimal(str(p['current_value_usdc'])) if p['current_value_usdc'] else Decimal('0')
                for p in active_positions
            )

            # Total portfolio value
            total_portfolio = usdc_balance + positions_value

            print(f"   Active Positions: {len(active_positions)}")
            if active_positions:
                for pos in active_positions:
                    print(f"     - Token {pos['token_id']}: Entry=${pos['entry_amount_usdc']}, Current=${pos['current_value_usdc']}, Strategy={pos['strategy_type']}")
                print(f"   Total Deployed Capital: ${total_deployed}")
                print(f"   Positions Current Value: ${positions_value}")
            print(f"   Total Portfolio Value: ${total_portfolio}")

            # Get user's strategies
            strategies = await conn.fetch(
                """
                SELECT strategy_type, allocated_capital_usd, deployed_capital_usd
                FROM user_strategies
                WHERE user_id = $1 AND status = 'active'
                """,
                user_id
            )

            for strategy in strategies:
                print(f"\n   📊 Strategy: {strategy['strategy_type']}")
                print(f"      Current Allocated: ${strategy['allocated_capital_usd']}")
                print(f"      Current Deployed: ${strategy['deployed_capital_usd']}")

                # Calculate correct deployed capital for this strategy
                strategy_deployed = sum(
                    Decimal(str(p['entry_amount_usdc']))
                    for p in active_positions
                    if p['strategy_type'] == strategy['strategy_type']
                )

                # Update deployed_capital_usd
                if strategy_deployed != strategy['deployed_capital_usd']:
                    print(f"      ⚠️  Fixing deployed_capital: ${strategy['deployed_capital_usd']} → ${strategy_deployed}")
                    await conn.execute(
                        """
                        UPDATE user_strategies
                        SET deployed_capital_usd = $1, updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = $2 AND strategy_type = $3 AND status = 'active'
                        """,
                        strategy_deployed,
                        user_id,
                        strategy['strategy_type']
                    )

                # Update allocated_capital_usd to match portfolio value
                # (only if this is the user's only strategy, otherwise split proportionally)
                if len(strategies) == 1:
                    if total_portfolio != strategy['allocated_capital_usd']:
                        print(f"      ⚠️  Fixing allocated_capital: ${strategy['allocated_capital_usd']} → ${total_portfolio}")
                        await conn.execute(
                            """
                            UPDATE user_strategies
                            SET allocated_capital_usd = $1, updated_at = CURRENT_TIMESTAMP
                            WHERE user_id = $2 AND strategy_type = $3 AND status = 'active'
                            """,
                            total_portfolio,
                            user_id,
                            strategy['strategy_type']
                        )
                else:
                    print(f"      ℹ️  User has {len(strategies)} strategies, skipping allocated_capital update")

            # Also update user's usdc_balance if it doesn't match calculated balance
            calculated_usdc_balance = total_portfolio - positions_value
            if abs(usdc_balance - calculated_usdc_balance) > Decimal('0.01'):
                print(f"\n   ⚠️  Fixing usdc_balance: ${usdc_balance} → ${calculated_usdc_balance}")
                await conn.execute(
                    """
                    UPDATE users
                    SET usdc_balance = $1
                    WHERE user_id = $2
                    """,
                    calculated_usdc_balance,
                    user_id
                )

            print(f"   ✅ Fixed user {user_id}")
            print("-"*80)

        print(f"\n{'='*80}")
        print("✅ All active users fixed!")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_all_active_users())
