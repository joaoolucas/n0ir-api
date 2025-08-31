#!/usr/bin/env python3
"""Recalculate deposits/withdrawals and last blocks for all users from transactions."""

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import os

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+asyncpg://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway')


async def recalc():
    engine = create_async_engine(DATABASE_URL, echo=False)
    AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSessionLocal() as session:
        # Totals per user
        await session.execute(text(
            """
            WITH totals AS (
                SELECT 
                    user_id,
                    SUM(CASE WHEN tx_type = 'DEPOSIT' THEN COALESCE((event_data->>'amount_usdc')::numeric, 0) ELSE 0 END) AS deposits,
                    SUM(CASE WHEN tx_type IN ('WITHDRAWAL','WITHDRAW') THEN COALESCE((event_data->>'amount_usdc')::numeric, 0) ELSE 0 END) AS withdrawals
                FROM transactions
                WHERE status = 'CONFIRMED'
                GROUP BY user_id
            ),
            last_blocks AS (
                SELECT 
                    user_id,
                    MAX(CASE WHEN tx_type = 'DEPOSIT' THEN block_number ELSE NULL END) AS last_deposit_block,
                    MAX(CASE WHEN tx_type IN ('WITHDRAWAL','WITHDRAW') THEN block_number ELSE NULL END) AS last_withdrawal_block
                FROM transactions
                WHERE status = 'CONFIRMED'
                GROUP BY user_id
            )
            UPDATE users u
            SET 
                total_deposits_usdc = COALESCE(t.deposits, 0),
                total_withdrawals_usdc = COALESCE(t.withdrawals, 0),
                last_deposit_block = lb.last_deposit_block,
                last_withdrawal_block = lb.last_withdrawal_block
            FROM totals t
            JOIN last_blocks lb USING (user_id)
            WHERE u.user_id = t.user_id
            """
        ))

        # has_deposited_50_usdc flag
        await session.execute(text(
            """
            UPDATE users
            SET has_deposited_50_usdc = (COALESCE(total_deposits_usdc,0) - COALESCE(total_withdrawals_usdc,0)) >= 50
            """
        ))

        await session.commit()
    await engine.dispose()


if __name__ == '__main__':
    asyncio.run(recalc())

