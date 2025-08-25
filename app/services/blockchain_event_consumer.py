"""Consumer for blockchain events from n0ir-watcher.

Consumes events from the blockchain:events Redis stream and updates business tables.
"""

import json
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
import redis.asyncio as aioredis
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import get_db


class BlockchainEventConsumer:
    """Consumes blockchain events from Redis streams."""
    
    def __init__(self):
        self.redis_client: Optional[aioredis.Redis] = None
        self.stream_key = "blockchain:events"
        self.consumer_group = "n0ir-api"
        # Use Railway environment variable or default
        import os
        env = os.getenv("RAILWAY_ENVIRONMENT", "development")
        self.consumer_name = f"api-{env}"
        self.running = False
        self._consumer_task = None
        
    async def initialize(self):
        """Initialize Redis connection and consumer group."""
        try:
            # Parse Redis URL
            redis_url = settings.redis_url
            if not redis_url or redis_url.startswith('${{'):
                logger.warning("Redis URL not configured, blockchain event consumer disabled")
                return
            
            self.redis_client = await aioredis.from_url(
                redis_url,
                decode_responses=False  # We'll handle decoding
            )
            await self.redis_client.ping()
            
            # Create consumer group (ignore if exists)
            try:
                await self.redis_client.xgroup_create(
                    self.stream_key,
                    self.consumer_group,
                    id="0"  # Start from beginning
                )
                logger.info(f"Created consumer group {self.consumer_group}")
            except Exception:
                # Group already exists
                pass
                
            logger.info(f"Blockchain event consumer initialized for stream {self.stream_key}")
            
        except Exception as e:
            logger.error(f"Failed to initialize blockchain event consumer: {e}")
            self.redis_client = None
    
    async def start(self):
        """Start consuming events."""
        if not self.redis_client:
            logger.warning("Cannot start consumer - Redis not connected")
            return
        
        self.running = True
        self._consumer_task = asyncio.create_task(self._consume_events())
        logger.info("Started blockchain event consumer")
    
    async def stop(self):
        """Stop consuming events."""
        self.running = False
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
        
        if self.redis_client:
            await self.redis_client.close()
        
        logger.info("Stopped blockchain event consumer")
    
    async def _consume_events(self):
        """Main consumer loop."""
        while self.running:
            try:
                # Read pending messages
                messages = await self.redis_client.xreadgroup(
                    self.consumer_group,
                    self.consumer_name,
                    {self.stream_key: ">"},  # Read new messages
                    count=10,
                    block=5000  # Block for 5 seconds
                )
                
                if messages:
                    for stream_name, stream_messages in messages:
                        for message_id, data in stream_messages:
                            try:
                                # Process the event
                                await self._process_event(message_id, data)
                                
                                # Acknowledge the message
                                await self.redis_client.xack(
                                    self.stream_key,
                                    self.consumer_group,
                                    message_id
                                )
                            except Exception as e:
                                logger.error(f"Error processing message {message_id}: {e}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in consumer loop: {e}")
                await asyncio.sleep(5)
    
    async def _process_event(self, message_id: bytes, data: Dict[bytes, bytes]):
        """Process a single event from the stream."""
        try:
            # Decode the event
            event = {
                k.decode() if isinstance(k, bytes) else k: 
                v.decode() if isinstance(v, bytes) else v
                for k, v in data.items()
            }
            
            # Parse JSON fields
            event_type = event.get("type", "")
            event_data = json.loads(event.get("data", "{}"))
            metadata = json.loads(event.get("metadata", "{}"))
            
            logger.debug(f"Processing {event_type} event from blockchain")
            
            # Route to appropriate handler
            if event_type.startswith("position."):
                await self._handle_position_event(event_type, event_data, metadata)
            elif event_type.startswith("operation."):
                await self._handle_operation_event(event_type, event_data, metadata)
            elif event_type.startswith("reward."):
                await self._handle_reward_event(event_type, event_data, metadata)
            elif event_type.startswith("gauge."):
                await self._handle_gauge_event(event_type, event_data, metadata)
            else:
                logger.debug(f"Unhandled event type: {event_type}")
                
        except Exception as e:
            logger.error(f"Failed to process event {message_id}: {e}")
    
    async def _handle_position_event(
        self, 
        event_type: str, 
        data: Dict[str, Any], 
        metadata: Dict[str, Any]
    ):
        """Handle position-related events."""
        user_id = metadata.get("user_id")
        if not user_id:
            return
        
        try:
            async for db in get_db():
                if event_type == "position.created":
                    # Check if user exists and update position count
                    from app.database.models.user import User
                    user = await db.get(User, user_id)
                    if user:
                        logger.info(f"Position created for user {user_id}: {data.get('nft_token_id')}")
                        # Could update user stats or trigger other actions
                        
                elif event_type == "position.updated":
                    # Update position metrics if tracked
                    logger.info(f"Position updated for user {user_id}: {data.get('nft_token_id')}")
                    
                elif event_type == "position.closed":
                    # Handle position closure
                    logger.info(f"Position closed for user {user_id}: {data.get('nft_token_id')}")
                
                await db.commit()
                break  # Exit async generator
                
        except Exception as e:
            logger.error(f"Error handling position event: {e}")
    
    async def _handle_operation_event(
        self,
        event_type: str,
        data: Dict[str, Any],
        metadata: Dict[str, Any]
    ):
        """Handle operation-related events."""
        user_id = metadata.get("user_id")
        if not user_id:
            return
        
        if event_type == "operation.completed":
            logger.info(f"Operation completed for user {user_id}: {data.get('tx_hash')}")
            # Could update transaction status in API database
    
    async def _handle_reward_event(
        self,
        event_type: str,
        data: Dict[str, Any],
        metadata: Dict[str, Any]
    ):
        """Handle reward-related events."""
        user_id = metadata.get("user_id")
        if not user_id:
            return
        
        if event_type == "reward.earned":
            amount = data.get("amount", 0)
            token = data.get("token_address", "")
            logger.info(f"Reward earned by user {user_id}: {amount} of {token}")
            # Could update user reward totals
    
    async def _handle_gauge_event(
        self,
        event_type: str,
        data: Dict[str, Any],
        metadata: Dict[str, Any]
    ):
        """Handle gauge staking events."""
        user_id = metadata.get("user_id")
        if not user_id:
            return
        
        if event_type == "gauge.staked":
            logger.info(f"Position staked by user {user_id}: {data.get('position_id')}")
        elif event_type == "gauge.unstaked":
            logger.info(f"Position unstaked by user {user_id}: {data.get('position_id')}")


# Global instance
blockchain_consumer = BlockchainEventConsumer()