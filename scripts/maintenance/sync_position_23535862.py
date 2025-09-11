#!/usr/bin/env python3
"""Script to sync position 23535862 to the database for user 0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51"""

import asyncio
import os
import sys
from decimal import Decimal
from datetime import datetime, timezone

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.database.models.user import User, UserStatus
from app.database.models.position import Position, PositionStatus
from app.database.models.transaction import Transaction, TransactionType, TransactionStatus
from app.core.logger import logger


async def sync_position():
    """Sync position 23531609 to the database."""
    
    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return
    
    # Convert postgres:// to postgresql+asyncpg:// for async support
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    # Create async engine
    engine = create_async_engine(database_url, echo=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        try:
            # User and CDP wallet data
            user_id = "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51"
            cdp_wallet_address = "0xa449F944aD033D8083564556Fd918C45B716f79c"
            cdp_wallet_name = "n0ir-agent-0xdBE4e3"
            
            # Check if user exists, create if not
            stmt = select(User).where(User.user_id == user_id)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                logger.info(f"Creating user {user_id}...")
                user = User(
                    user_id=user_id,
                    cdp_wallet_address=cdp_wallet_address,
                    cdp_wallet_name=cdp_wallet_name,
                    status=UserStatus.ACTIVE
                )
                db.add(user)
                await db.flush()  # Flush to ensure user exists before adding position
                logger.info(f"Created user {user_id}")
            
            # Position data from blockchain
            nft_token_id = 23535862
            pool_address = "0xb2cc224c1c9feE385f8ad6a55b4d94E92359DC59"
            token0_address = "0x4200000000000000000000000000000000000006"  # WETH
            token1_address = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # USDC
            tick_lower = -192100
            tick_upper = -191700
            tick_spacing = 100
            liquidity = "4555068875525"
            current_value = Decimal("6.17")  # Current value in USD
            entry_amount = Decimal("6.15")  # Entry amount estimate
            gauge_address = "0xF33a96b5932D9E9B9A0eDA447AbD8C9d48d2e0c8"
            staked = True
            
            # Check if position already exists
            stmt = select(Position).where(Position.nft_token_id == nft_token_id)
            result = await db.execute(stmt)
            existing_position = result.scalar_one_or_none()
            
            if existing_position:
                logger.info(f"Position {nft_token_id} already exists, updating values...")
                # Update existing position
                existing_position.current_value_usdc = current_value
                existing_position.status = PositionStatus.ACTIVE
                existing_position.last_updated = datetime.now(timezone.utc)
                existing_position.staked = staked
                existing_position.gauge_address = gauge_address
                
                await db.commit()
                logger.info(f"Updated position {nft_token_id}")
            else:
                logger.info(f"Creating new position {nft_token_id}...")
                
                # Create new position
                position = Position(
                    nft_token_id=nft_token_id,
                    user_id=user_id,
                    pool_address=pool_address,
                    pool_name="WETH-USDC",
                    token0_address=token0_address,
                    token1_address=token1_address,
                    tick_lower=tick_lower,
                    tick_upper=tick_upper,
                    tick_spacing=tick_spacing,
                    liquidity=liquidity,
                    entry_amount_usdc=entry_amount,
                    current_value_usdc=current_value,
                    staked=staked,
                    gauge_address=gauge_address,
                    status=PositionStatus.ACTIVE,
                    entry_date=datetime.now(timezone.utc),
                    last_updated=datetime.now(timezone.utc)
                )
                
                db.add(position)
                
                # Create position entry transaction
                transaction = Transaction(
                    user_id=user_id,
                    transaction_type=TransactionType.POSITION_ENTRY,
                    amount_usdc=entry_amount,
                    pool_name="WETH-USDC",
                    status=TransactionStatus.CONFIRMED,
                    tx_metadata='{"nft_token_id": 23535862, "pool_address": "0xb2cc224c1c9feE385f8ad6a55b4d94E92359DC59", "action": "position_opened"}',
                    confirmed_at=datetime.now(timezone.utc)
                )
                
                db.add(transaction)
                
                await db.commit()
                logger.info(f"Created position {nft_token_id} and transaction record")
            
            logger.info("Position sync completed successfully!")
            
        except Exception as e:
            logger.error(f"Error syncing position: {e}")
            await db.rollback()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(sync_position())