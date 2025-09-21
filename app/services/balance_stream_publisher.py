"""Alternative balance update publisher using Redis streams for guaranteed delivery."""

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

    if _redis_client is None:
        try:
            _redis_client = await aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=10,
                socket_keepalive=True,
            )
            await _redis_client.ping()
            logger.info(f"Redis stream client connected to {settings.REDIS_URL}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    return _redis_client


async def publish_balance_change_to_stream(
    user_id: str,
    old_balance: Decimal,
    new_balance: Decimal,
    event_type: str,
    has_deposited_50_usdc: bool = False
):
    """Publish balance change event to Redis stream for guaranteed delivery.

    This uses Redis streams instead of pub/sub for better reliability.
    """
    try:
        redis_client = await get_redis_client()

        # Stream key for balance events
        stream_key = "balance:events:stream"

        # Event data
        event_data = {
            "user_id": user_id,
            "balance": str(new_balance),
            "old_balance": str(old_balance),
            "event_type": event_type,
            "has_deposited_50_usdc": str(has_deposited_50_usdc).lower()
        }

        # Add to stream
        message_id = await redis_client.xadd(stream_key, event_data)

        logger.info(
            f"✅ Published balance event to stream: {stream_key}/{message_id} "
            f"- {user_id} {old_balance} -> {new_balance} ({event_type})"
        )

        return message_id

    except Exception as e:
        logger.error(f"Failed to publish to stream: {e}")
        raise