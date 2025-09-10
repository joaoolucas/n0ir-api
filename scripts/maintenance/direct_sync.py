#!/usr/bin/env python3
"""
Direct database insertion for existing position - quickest way!
"""

import asyncio
import os
from datetime import datetime
from decimal import Decimal

# Set up Django-style async context for SQLAlchemy
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.session import get_db
from app.services.user_service import UserService


async def sync_position_directly():
    """Directly create position in database."""
    
    # Position data for the existing position
    user_id = "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51"
    
    print("Creating position directly in database...")
    
    async for db in get_db():
        try:
            user_service = UserService(db)
            
            # Create the position
            # UPDATE THESE VALUES if you have actual data
            position = await user_service.create_position(
                user_id=user_id,
                nft_token_id=99999999,  # UPDATE with actual token_id if known
                pool_address="0x4C36388bE6589A5e7C5B8c8F2e5C2fF2b76A1Cc4",  # WETH/USDC pool
                token0_address="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC
                token1_address="0x4200000000000000000000000000000000000006",  # WETH
                tick_lower=-887220,  # Full range
                tick_upper=887220,
                tick_spacing=100,
                liquidity="1000000000000",
                entry_amount_usdc=Decimal("14.25"),  # 95% of 15 USDC
                entry_tx_hash="0x0000000000000000000000000000000000000000",
                staked=False,
                gauge_address=None,
                pool_name="WETH-USDC"
            )
            
            print(f"✅ Position created successfully!")
            print(f"   Token ID: {position.nft_token_id}")
            print(f"   Pool: {position.pool_name}")
            print(f"   Amount: ${position.entry_amount_usdc}")
            print("")
            print("The position should now appear in the frontend!")
            
            break
            
        except Exception as e:
            print(f"❌ Error creating position: {e}")
            import traceback
            traceback.print_exc()
            break


if __name__ == "__main__":
    asyncio.run(sync_position_directly())