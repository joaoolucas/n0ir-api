"""Balance update service for publishing balance change events to Redis."""

import json
from decimal import Decimal
from loguru import logger
import redis.asyncio as aioredis
from app.core.config import settings


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
        # Create Redis client
        redis_client = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )

        event_data = {
            "user_id": user_id,
            "balance": float(new_balance),
            "old_balance": float(old_balance),
            "event_type": event_type,
            "has_deposited_50_usdc": has_deposited_50_usdc
        }

        # Publish to the channel that BalanceMonitor listens to
        await redis_client.publish("user:balance:changed", json.dumps(event_data))

        logger.info(f"Published balance change: {user_id} {old_balance} -> {new_balance} ({event_type})")

        await redis_client.close()

    except Exception as e:
        logger.error(f"Failed to publish balance change event: {e}")