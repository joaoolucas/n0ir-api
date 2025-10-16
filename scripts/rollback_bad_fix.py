#!/usr/bin/env python3
"""Rollback the incorrect fixes and apply correct ones."""

import asyncpg
import asyncio
from decimal import Decimal

async def rollback_and_fix():
    """Rollback bad fixes and apply correct ones."""
    database_url = "postgresql://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway"

    # Original values before the bad fix
    original_values = {
        "0x0c4989CfB77FC28355eA49388759dA07A743C1e5": {"allocated": 50, "deployed": 0},
        "0x1eC0047Cc9461330A0368EA30c9312267127ab44": {"allocated": 50, "deployed": 49.982339},
        "0x3fEd03F336782e2C5344A04B86f19fa9df07892d": {"allocated": 1200, "deployed": 0},
        "0x42dda1966E04021cE096172F3cd4fAaC0cDfeccf": {"allocated": 1000, "deployed": 999.745117},
        "0xa388Ed18DAE0DA9d16BAF9f57Eb9dE03512dBAF4": {"allocated": 48.732195, "deployed": 48.711737},
        "0xa66aF15b150F54cd09Db3483cC790Ff43EB8F32D": {"allocated": 176.609134, "deployed": 0},
        "0xB656D6634128c1583909136deF5E560aadA5fFF7": {"allocated": 100, "deployed": 0},
        "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51": {"allocated": 823.31, "deployed": 823.099381},
    }

    conn = await asyncpg.connect(database_url)

    try:
        print("Rollback incorrect fixes and apply correct ones\n")
        print("="*80)

        for user_id, original in original_values.items():
            print(f"\n👤 User: {user_id}")

            # Get current state
            user = await conn.fetchrow(
                "SELECT usdc_balance FROM users WHERE user_id = $1",
                user_id
            )

            # Get active positions
            positions = await conn.fetch(
                """
                SELECT token_id, entry_amount_usdc, current_value_usdc, strategy_type
                FROM positions
                WHERE user_id = $1 AND status = 'ACTIVE'
                """,
                user_id
            )

            total_deployed = sum(Decimal(str(p['entry_amount_usdc'])) for p in positions)
            positions_current_value = sum(
                Decimal(str(p['current_value_usdc'])) if p['current_value_usdc'] else Decimal('0')
                for p in positions
            )

            # CORRECT calculation:
            # Total portfolio = usdc_balance - deployed_capital + current_position_values
            # Because usdc_balance was never decremented when positions were opened (old bug)
            correct_total_portfolio = user['usdc_balance'] - total_deployed + positions_current_value

            print(f"   USDC Balance (DB): ${user['usdc_balance']}")
            print(f"   Deployed Capital: ${total_deployed}")
            print(f"   Positions Current Value: ${positions_current_value}")
            print(f"   Correct Total Portfolio: ${user['usdc_balance']} - ${total_deployed} + ${positions_current_value} = ${correct_total_portfolio}")

            # Update strategy
            strategy = await conn.fetchrow(
                """
                SELECT strategy_type, allocated_capital_usd, deployed_capital_usd
                FROM user_strategies
                WHERE user_id = $1 AND status = 'active'
                LIMIT 1
                """,
                user_id
            )

            if strategy:
                print(f"\n   📊 Strategy: {strategy['strategy_type']}")
                print(f"      Current: allocated=${strategy['allocated_capital_usd']}, deployed=${strategy['deployed_capital_usd']}")
                print(f"      Correct: allocated=${correct_total_portfolio}, deployed=${total_deployed}")

                await conn.execute(
                    """
                    UPDATE user_strategies
                    SET allocated_capital_usd = $1,
                        deployed_capital_usd = $2,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = $3 AND strategy_type = $4 AND status = 'active'
                    """,
                    correct_total_portfolio,
                    total_deployed,
                    user_id,
                    strategy['strategy_type']
                )

                print(f"      ✅ Fixed strategy")

            print("-"*80)

        print(f"\n{'='*80}")
        print("✅ All users fixed correctly!")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(rollback_and_fix())
