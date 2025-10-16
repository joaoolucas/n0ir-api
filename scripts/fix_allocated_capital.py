#!/usr/bin/env python3
"""Fix allocated capital for user with mismatched balance."""

import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv
from decimal import Decimal
from sqlalchemy import select, and_

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')

from app.database.session import init_db, async_session_maker
from app.database.models.user_strategy import UserStrategy
from app.database.models.user import User

async def fix_user_allocated_capital():
    """Fix allocated capital for specific user."""
    user_id = "0xa388Ed18DAE0DA9d16BAF9f57Eb9dE03512dBAF4"

    # Initialize database
    init_db()

    async with async_session_maker() as db:
        # Get user
        user_stmt = select(User).where(User.user_id == user_id)
        result = await db.execute(user_stmt)
        user = result.scalar_one_or_none()

        if not user:
            print(f"User {user_id} not found")
            return

        print(f"User: {user_id}")
        print(f"Total portfolio value: ${user.total_portfolio_value}")

        # Get active strategy
        strategy_stmt = select(UserStrategy).where(
            and_(
                UserStrategy.user_id == user_id,
                UserStrategy.status == 'active'
            )
        )
        result = await db.execute(strategy_stmt)
        strategies = result.scalars().all()

        if not strategies:
            print("No active strategies found")
            return

        for strategy in strategies:
            print(f"\nStrategy: {strategy.strategy_type}")
            print(f"Current allocated capital: ${strategy.allocated_capital_usd}")
            print(f"Deployed capital: ${strategy.deployed_capital_usd}")

            # Update allocated capital to match portfolio value
            new_allocated = Decimal(str(user.total_portfolio_value))
            print(f"Updating allocated capital to: ${new_allocated}")

            strategy.allocated_capital_usd = new_allocated

        await db.commit()
        print("\n✓ Fixed allocated capital")

if __name__ == "__main__":
    asyncio.run(fix_user_allocated_capital())
