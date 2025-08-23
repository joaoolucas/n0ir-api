"""Debug endpoints for testing Redis communication."""

from fastapi import APIRouter, HTTPException
from loguru import logger
import redis
import json
import asyncio
from datetime import datetime
from app.core.config import settings

router = APIRouter(prefix="/debug", tags=["debug"])


@router.post("/test-redis-publish")
async def test_redis_publish(channel: str = "test_channel", message: str = "test_message"):
    """Test publishing a message to Redis."""
    try:
        # Create Redis client
        client = redis.from_url(settings.redis_url, decode_responses=True)
        
        # Test connection
        client.ping()
        logger.info(f"Redis connected at: {settings.redis_url}")
        
        # Publish message
        test_data = {
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
            "source": "n0ir-api"
        }
        
        subscribers = client.publish(channel, json.dumps(test_data))
        logger.info(f"Published to {channel}: {test_data}, {subscribers} subscribers")
        
        return {
            "success": True,
            "channel": channel,
            "message": test_data,
            "subscribers": subscribers,
            "redis_url": settings.redis_url[:50] + "..."
        }
        
    except Exception as e:
        logger.error(f"Redis publish test failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-agent-command")
async def test_agent_command(user_id: str = "0xTEST"):
    """Test sending a command through agent_commands channel."""
    try:
        client = redis.from_url(settings.redis_url, decode_responses=True)
        
        # Send same format as AgentManagementService
        command = {
            "action": "start",
            "user_id": user_id,
            "metadata": {"test": True},
            "timestamp": datetime.utcnow().isoformat()
        }
        
        subscribers = client.publish("agent_commands", json.dumps(command))
        logger.info(f"Published test command for {user_id} to agent_commands: {subscribers} subscribers")
        
        # Also check if we can subscribe and receive
        pubsub = client.pubsub()
        pubsub.subscribe("agent_responses")
        
        # Wait briefly for response
        await asyncio.sleep(0.5)
        
        response = None
        message = pubsub.get_message(ignore_subscribe_messages=True)
        if message and message['type'] == 'message':
            response = json.loads(message['data'])
            logger.info(f"Received response: {response}")
        
        pubsub.unsubscribe("agent_responses")
        pubsub.close()
        
        return {
            "success": True,
            "command_sent": command,
            "subscribers": subscribers,
            "response_received": response,
            "redis_url": settings.redis_url[:50] + "..."
        }
        
    except Exception as e:
        logger.error(f"Agent command test failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/redis-info")
async def get_redis_info():
    """Get Redis connection information."""
    try:
        client = redis.from_url(settings.redis_url, decode_responses=True)
        
        # Get Redis info
        info = client.info()
        
        # Get all channels with subscribers
        channels = client.pubsub_channels()
        
        # Count keys
        key_count = client.dbsize()
        
        return {
            "connected": True,
            "redis_url": settings.redis_url[:50] + "...",
            "redis_version": info.get("redis_version"),
            "connected_clients": info.get("connected_clients"),
            "channels": list(channels) if channels else [],
            "total_keys": key_count,
            "memory_used": info.get("used_memory_human")
        }
        
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
            "redis_url": settings.redis_url[:50] + "..." if settings.redis_url else None
        }