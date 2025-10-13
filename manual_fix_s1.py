#!/usr/bin/env python3
"""Manual script to remove s1 from user's active_strategies"""
import asyncio
from sqlalchemy import text
from app.database.session import async_session_maker

async def fix_active_strategies():
    async with async_session_maker() as db:
        user_id = '0xC2952cc28EDf37B053188D89e6ac888B9855d132'

        # Check current state
        result = await db.execute(
            text("SELECT active_strategies FROM users WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        current = result.scalar()
        print(f"Current active_strategies: {current}")

        # Remove s1 using PostgreSQL JSONB operator
        await db.execute(
            text("UPDATE users SET active_strategies = active_strategies - 's1' WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        await db.commit()

        # Verify
        result = await db.execute(
            text("SELECT active_strategies FROM users WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        new_value = result.scalar()
        print(f"New active_strategies: {new_value}")
        print("✓ Successfully removed s1")

if __name__ == "__main__":
    asyncio.run(fix_active_strategies())
