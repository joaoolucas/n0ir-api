#!/usr/bin/env python3
"""
Publish position:created event to Railway Redis for proper sync
"""

import asyncio
import json
from datetime import datetime
import redis.asyncio as aioredis


async def publish_position_event():
    """Publish the position:created event to Railway Redis."""
    
    # Railway Redis URL
    redis_url = "redis://default:oqqCbIhdjpNzhvlEBTXYXgfVGaxujADn@switchback.proxy.rlwy.net:54405"
    
    # Connect to Redis
    redis_client = await aioredis.from_url(redis_url, decode_responses=True)
    
    # Position event for the REAL position
    position_event = {
        "event": "position_created",
        "user_id": "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51",
        "nft_token_id": 23350297,  # REAL token ID
        "pool_address": "0xF33a96b5932D9E9B9A0eDA447AbD8C9d48d2e0c8",
        "lower_tick": -887220,
        "upper_tick": 887220,
        "liquidity": "1448349575175256",
        "entry_amount_usdc": 15.00,
        "tx_hash": "0x0000000000000000000000000000000000000000",
        "stake_tx_hash": "0x0000000000000000000000000000000000000001",
        "gauge_address": "0xF33a96b5932D9E9B9A0eDA447AbD8C9d48d2e0c8",
        "staked": True,
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    print("Publishing position:created event to Railway Redis...")
    print(f"Event: {json.dumps(position_event, indent=2)}")
    
    # Publish it
    subscribers = await redis_client.publish("position:created", json.dumps(position_event))
    
    print(f"✅ Event published to {subscribers} subscribers!")
    print("The API should process this event if it's listening.")
    
    await redis_client.close()


if __name__ == "__main__":
    asyncio.run(publish_position_event())