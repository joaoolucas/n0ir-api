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
            
            # Create stream if it doesn't exist by adding a dummy entry
            try:
                # First ensure the stream exists
                await self.redis_client.xadd(
                    self.stream_key,
                    {"init": "true"},
                    maxlen=1
                )
                logger.info(f"Initialized stream {self.stream_key}")
            except Exception:
                pass  # Stream might already exist
            
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
        consecutive_errors = 0
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
                
                consecutive_errors = 0  # Reset on success
                
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
                consecutive_errors += 1
                if consecutive_errors <= 3:
                    logger.debug(f"Waiting for blockchain events stream... ({str(e)[:50]})")
                elif consecutive_errors == 4:
                    logger.warning("No blockchain events yet - watcher may not be running")
                # Only log as error after many failures
                if consecutive_errors > 10:
                    logger.error(f"Persistent error in consumer loop: {e}")
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
        """Handle position-related events from blockchain.
        
        This is where business logic is triggered based on confirmed blockchain state.
        The watcher has already written to blockchain.positions table.
        """
        user_id = metadata.get("user_id")
        if not user_id:
            # Try to get user_id from owner address
            owner_address = data.get("owner")
            if owner_address:
                async for db in get_db():
                    from app.database.models.user import User
                    from sqlalchemy import select
                    result = await db.execute(
                        select(User).where(User.cdp_wallet_address == owner_address)
                    )
                    user = result.scalar_one_or_none()
                    if user:
                        user_id = user.user_id
                    break
            
            if not user_id:
                logger.debug(f"No user found for position event: {event_type}")
                return
        
        try:
            async for db in get_db():
                from app.database.models.user import User
                from app.services.user_service import UserService
                from decimal import Decimal
                
                service = UserService(db)
                
                if event_type == "position.created":
                    nft_token_id = data.get('nft_token_id')
                    logger.info(f"Processing position.created event: user={user_id}, token_id={nft_token_id}")
                    
                    # Update user metrics
                    user = await service.get_user(user_id)
                    if user:
                        # Initialize PnL tracking for new position
                        await service.recalculate_user_pnl(user_id)
                        
                        # Log position creation in business metrics
                        logger.success(
                            f"Position {nft_token_id} created for user {user_id} - confirmed on blockchain"
                        )
                        
                elif event_type == "position.updated":
                    nft_token_id = data.get('nft_token_id')
                    logger.info(f"Processing position.updated event: user={user_id}, token_id={nft_token_id}")
                    
                    # Recalculate user PnL with updated position values
                    await service.recalculate_user_pnl(user_id)
                    
                elif event_type == "position.closed":
                    nft_token_id = data.get('nft_token_id')
                    final_value = Decimal(str(data.get('final_value_usd', 0)))
                    
                    logger.info(
                        f"Processing position.closed event: user={user_id}, token_id={nft_token_id}, final_value={final_value}"
                    )
                    
                    # Update realized PnL
                    user = await service.get_user(user_id)
                    if user:
                        # The position is already marked as closed in blockchain.positions
                        # Update user's realized PnL
                        await service.recalculate_user_pnl(user_id)
                        
                        # Return funds to user balance if needed
                        if final_value > 0:
                            # Credit user balance with the final value
                            from app.database.models.transaction import Transaction
                            from app.schemas.users import TransactionType, TransactionStatus
                            
                            tx = Transaction(
                                user_id=user_id,
                                transaction_type=TransactionType.POSITION_CLOSED,
                                amount_usdc=final_value,
                                status=TransactionStatus.CONFIRMED,
                                tx_hash=data.get('tx_hash', ''),
                                description=f"Position {nft_token_id} closed"
                            )
                            db.add(tx)
                            
                        logger.success(
                            f"Position {nft_token_id} closed for user {user_id} - final value: {final_value} USDC"
                        )
                
                await db.commit()
                break  # Exit async generator
                
        except Exception as e:
            logger.error(f"Error handling position event {event_type}: {e}", exc_info=True)
    
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