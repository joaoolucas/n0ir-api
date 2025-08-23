#!/usr/bin/env python3
"""
Sync the REAL position that was created - token ID 23350297
"""

import asyncio
import os
from datetime import datetime
from decimal import Decimal

# Set up Django-style async context for SQLAlchemy
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.session import get_db


async def sync_real_position():
    """Create the REAL position in database."""
    
    # REAL position data from logs
    user_id = "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51"
    
    print("First, deleting the fake position...")
    
    async for db in get_db():
        try:
            from app.database.models.position import Position, PositionStatus
            from sqlalchemy import select
            
            # First delete the fake position
            result = await db.execute(select(Position).where(Position.nft_token_id == 99999999))
            fake_position = result.scalar_one_or_none()
            if fake_position:
                await db.delete(fake_position)
                await db.commit()
                print("✅ Deleted fake position 99999999")
            
            # Now create the REAL position
            print("\nCreating REAL position 23350297...")
            
            # Directly create the position without balance check since it was already created on-chain
            position = Position(
                user_id=user_id,
                nft_token_id=23350297,  # REAL token ID from logs!
                pool_address="0xF33a96b5932D9E9B9A0eDA447AbD8C9d48d2e0c8",  # Gauge address from logs
                token0_address="0x4200000000000000000000000000000000000006",  # WETH
                token1_address="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC
                tick_lower=-887220,  # Full range position
                tick_upper=887220,
                tick_spacing=100,
                liquidity="1448349575175256",  # From logs
                entry_amount_usdc=Decimal("15.00"),  # Original amount
                current_value_usdc=Decimal("15.06"),  # Current value from logs
                entry_tx_hash="0x0000000000000000000000000000000000000000",
                staked=True,  # Position is staked
                gauge_address="0xF33a96b5932D9E9B9A0eDA447AbD8C9d48d2e0c8",
                pool_name="WETH-USDC",
                status=PositionStatus.ACTIVE
            )
            
            db.add(position)
            await db.commit()
            await db.refresh(position)
            
            print(f"✅ REAL position created successfully!")
            print(f"   Token ID: {position.nft_token_id}")
            print(f"   Pool: {position.pool_name}")
            print(f"   Amount: ${position.entry_amount_usdc}")
            print(f"   Current Value: ${position.current_value_usdc}")
            print(f"   Staked: {position.staked}")
            print(f"   Status: {position.status.value}")
            print("")
            print("The REAL position 23350297 should now appear in the frontend!")
            
            break
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            break


if __name__ == "__main__":
    asyncio.run(sync_real_position())