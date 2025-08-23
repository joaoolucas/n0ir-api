#!/usr/bin/env python3
"""
Quickest way to sync existing position - run from API directory with venv activated
"""

import asyncio
import json
from datetime import datetime

async def main():
    import redis.asyncio as aioredis
    
    # Connect to Redis (adjust if using Railway Redis)
    redis_url = "redis://localhost:6379"  # Or use your REDIS_URL env var
    redis_client = await aioredis.from_url(redis_url, decode_responses=True)
    
    # Position event for the existing position
    # UPDATE THESE VALUES if you have actual data from logs
    position_event = {
        "event": "position_created",
        "user_id": "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51",
        "nft_token_id": 12345678,  # UPDATE THIS if you know the actual token_id
        "pool_address": "0x4C36388bE6589A5e7C5B8c8F2e5C2fF2b76A1Cc4",  # Common pool
        "lower_tick": -887220,
        "upper_tick": 887220,
        "liquidity": "1000000000000",
        "entry_amount_usdc": 14.25,  # 95% of 15 USDC
        "tx_hash": "0x1234567890abcdef",
        "stake_tx_hash": None,
        "gauge_address": None,
        "staked": False,
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    print("Publishing event:", json.dumps(position_event, indent=2))
    
    # Publish it
    await redis_client.publish("position:created", json.dumps(position_event))
    
    print("✅ Done! Check API logs and database.")
    await redis_client.close()

if __name__ == "__main__":
    asyncio.run(main())