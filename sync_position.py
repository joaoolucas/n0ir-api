#!/usr/bin/env python3
"""
Quick script to manually create a position:created event to sync existing position
"""

import asyncio
import json
from datetime import datetime
import sys
import os

# Add the app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.redis_client import get_redis_client


async def sync_position():
    """Publish position:created event for existing position."""
    
    # THE POSITION THAT WAS ALREADY CREATED
    # Update these values if you have the actual data from logs/blockchain
    position_event = {
        "event": "position_created",
        "user_id": "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51",
        "nft_token_id": 999999,  # PLACEHOLDER - Update if you know the actual token_id
        "pool_address": "0x4C36388bE6589A5e7C5B8c8F2e5C2fF2b76A1Cc4",  # WETH/USDC pool
        "lower_tick": -887220,  # Full range position
        "upper_tick": 887220,
        "liquidity": "1000000000000",
        "entry_amount_usdc": 14.25,  # 95% of 15 USDC
        "tx_hash": "0x0000000000000000000000000000000000000000",
        "stake_tx_hash": None,
        "gauge_address": None,
        "staked": False,
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    print("=" * 60)
    print("Publishing position:created event with:")
    print(json.dumps(position_event, indent=2))
    print("=" * 60)
    
    # Get Redis client
    redis_client = await get_redis_client()
    
    try:
        # Publish the event
        await redis_client._redis.publish("position:created", json.dumps(position_event))
        print("✅ Event published successfully!")
        print("Check the API logs to see if it was processed.")
        print("The position should now appear in the database and frontend.")
    except Exception as e:
        print(f"❌ Error publishing event: {e}")
    finally:
        await redis_client.close()


if __name__ == "__main__":
    asyncio.run(sync_position())