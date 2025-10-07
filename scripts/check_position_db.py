#!/usr/bin/env python3
"""
Check if position exists in database.
"""

import os
import sys
from pathlib import Path

# Add project root to path
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

import asyncio
from sqlalchemy import select
from app.database.session import get_async_session
from app.database.models import Position


async def check():
    async with get_async_session() as db:
        # Check for position 26295138
        stmt = select(Position).where(Position.token_id == 26295138)
        result = await db.execute(stmt)
        position = result.scalar_one_or_none()

        if position:
            print(f'Position 26295138 exists in DB:')
            print(f'  User: {position.user_id}')
            print(f'  Status: {position.status}')
            print(f'  Pool: {position.pool_address}')
            print(f'  Staked: {position.staked}')
            print(f'  Gauge: {position.gauge_address}')
        else:
            print('Position 26295138 NOT found in database')

        # Check all positions for user
        user_stmt = select(Position).where(Position.user_id == '0xAC65e18F7f4e5eDEA297b9E5433C153f1d9a7764')
        result = await db.execute(user_stmt)
        positions = result.scalars().all()
        print(f'\nTotal positions for user: {len(positions)}')
        for p in positions:
            print(f'  Position {p.token_id}: status={p.status}, staked={p.staked}, gauge={p.gauge_address}')


if __name__ == "__main__":
    asyncio.run(check())