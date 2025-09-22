"""Balance update service for publishing balance change events to Redis."""

import json
from decimal import Decimal
from typing import Optional
from loguru import logger
import redis.asyncio as aioredis
from app.core.config import settings


# Global Redis client for persistent connection
_redis_client: Optional[aioredis.Redis] = None


async def get_redis_client() -> aioredis.Redis:
    """Get or create a persistent Redis client."""
    global _redis_client

    if _redis_client is None or not await _redis_client.ping():
        logger.info(f"Creating new Redis connection to {settings.redis_url}")
        _redis_client = await aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=10
        )
        # Test the connection
        await _redis_client.ping()
        logger.info("Redis connection established for balance updates")

    return _redis_client


async def publish_balance_change_event(
    user_id: str,
    old_balance: Decimal,
    new_balance: Decimal,
    event_type: str,
    has_deposited_50_usdc: bool = False
):
    """Publish balance change event to Redis for agent manager consumption.

    Args:
        user_id: User ID whose balance changed
        old_balance: Previous balance
        new_balance: New balance
        event_type: Type of event (DEPOSIT, WITHDRAWAL, etc.)
        has_deposited_50_usdc: Whether user has ever deposited 50+ USDC
    """
    try:
        # Use persistent Redis client
        redis_client = await get_redis_client()

        event_data = {
            "user_id": user_id,
            "balance": float(new_balance),
            "old_balance": float(old_balance),
            "event_type": event_type,
            "has_deposited_50_usdc": has_deposited_50_usdc
        }

        # Publish to the channel that BalanceMonitor listens to
        channel = "user:balance:changed"
        message = json.dumps(event_data)

        # Publish and get the number of subscribers
        num_subscribers = await redis_client.publish(channel, message)

        if num_subscribers > 0:
            logger.info(
                f"✅ Published balance change to {num_subscribers} subscribers: "
                f"{user_id} {old_balance} -> {new_balance} ({event_type})"
            )
        else:
            logger.warning(
                f"⚠️ Published balance change but NO SUBSCRIBERS on channel '{channel}': "
                f"{user_id} {old_balance} -> {new_balance} ({event_type})"
            )
            # This is the issue - agent manager is not subscribed!

        # Don't close the persistent connection
        # await redis_client.close()

    except Exception as e:
        logger.error(f"Failed to publish balance change event: {e}")
        # Reset connection on error
        global _redis_client
        _redis_client = None
        # Re-raise to make the error visible
        raise