#!/usr/bin/env python3
"""Fix withdrawal state in staging database."""

import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = "postgresql+asyncpg://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def fix_database():
    """Fix the database state."""
    engine = create_async_engine(DATABASE_URL)
    
    async with engine.begin() as conn:
        # Fix position status (position is closed on-chain)
        result = await conn.execute(text("""
            UPDATE positions 
            SET status = 'CLOSED'
            WHERE nft_token_id = 23474351
        """))
        print(f"Updated position: {result.rowcount} rows")
        
        # Fix user balance
        result = await conn.execute(text("""
            UPDATE users 
            SET available_balance = 10.150495
            WHERE user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
        """))
        print(f"Updated user balance: {result.rowcount} rows")
        
        # Clean up pending transactions
        result = await conn.execute(text("""
            DELETE FROM transactions 
            WHERE user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
            AND transaction_type = 'POSITION_EXIT'
            AND created_at > NOW() - INTERVAL '2 hours'
            AND tx_hash IS NULL
        """))
        print(f"Deleted pending transactions: {result.rowcount} rows")
        
    await engine.dispose()
    print("Database fixed!")

if __name__ == "__main__":
    asyncio.run(fix_database())