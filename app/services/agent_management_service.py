import redis
import redis.asyncio as aioredis
import json
import asyncio
from typing import Dict, Optional
from datetime import datetime
from loguru import logger
from app.core.config import settings

# Global singleton instance
_agent_service_instance = None

def get_agent_service():
    """Get the singleton agent management service instance."""
    global _agent_service_instance
    if _agent_service_instance is None:
        _agent_service_instance = AgentManagementService()
    return _agent_service_instance


class AgentManagementService:
    def __init__(self):
        self.redis_url = settings.redis_url
        self.redis_client = None
        self.async_redis_client = None
        self.wallet_callbacks = {}
        self._listener_task = None
        self._pubsub = None
        self._initialized = False
        
    async def _ensure_initialized(self):
        """Ensure the service is initialized with async Redis."""
        if self._initialized:
            return
            
        try:
            # Handle Railway template variable format
            redis_url = self.redis_url
            logger.info(f"Attempting Redis connection with URL: {redis_url[:30] if redis_url else 'None'}...")
            
            # Check if it's a template variable that wasn't expanded
            if redis_url and redis_url.startswith('${{'):
                logger.error(f"Redis URL appears to be an unexpanded template variable: {redis_url}")
                redis_url = None
            elif redis_url and not redis_url.startswith(('redis://', 'rediss://')):
                logger.warning(f"Invalid Redis URL format (should start with redis:// or rediss://): {redis_url[:30]}...")
                redis_url = None
            
            if redis_url:
                logger.info(f"Creating async Redis client with URL: {redis_url[:30]}...")
                # Create both sync (for publishing) and async (for subscribing) clients
                self.redis_client = redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_connect_timeout=5
                )
                self.async_redis_client = await aioredis.from_url(
                    redis_url,
                    decode_responses=True
                )
                # Test connection
                await self.async_redis_client.ping()
                logger.info(f"Async Redis connection established successfully to {redis_url[:30]}")
                self._initialized = True
            else:
                logger.warning("Redis URL not configured, running without Redis (agent features disabled)")
                self.redis_client = None
                self.async_redis_client = None
        except Exception as e:
            logger.error(f"Failed to connect to Redis at {self.redis_url[:30] if self.redis_url else 'None'}: {e}")
            logger.warning("Running without Redis - agent management features will be disabled")
            self.redis_client = None
            self.async_redis_client = None
        
    async def start_listener(self):
        """Start listening for wallet creation events."""
        await self._ensure_initialized()
        if self.async_redis_client and self._listener_task is None:
            self._listener_task = asyncio.create_task(self._listen_for_wallet_creation())
            logger.info("Started wallet creation listener task")
    
    async def _listen_for_wallet_creation(self):
        """Listen for wallet creation events from agent manager."""
        if not self.async_redis_client:
            logger.warning("No async Redis client, cannot start listener")
            return
            
        try:
            # Create pubsub with async client
            self._pubsub = self.async_redis_client.pubsub()
            # Listen for wallet_created, wallet_ready, agent_responses, and transaction_complete
            await self._pubsub.subscribe('wallet_created', 'wallet_ready', 'agent_responses', 'transaction_complete')
            logger.info("Subscribed to channels: wallet_created, wallet_ready, agent_responses, transaction_complete")
            
            # Use async iterator for messages
            async for message in self._pubsub.listen():
                try:
                    logger.debug(f"Received pubsub message: type={message.get('type')}, channel={message.get('channel')}")
                    
                    if message and message['type'] == 'message':
                        logger.info(f"Processing message from channel {message['channel']}: {message['data'][:100]}")
                        data = json.loads(message['data'])
                        user_id = data.get('user_id')
                        logger.info(f"Message for user_id: {user_id}, channel: {message['channel']}")
                        
                        # Handle wallet_ready event to update database
                        if message['channel'] == 'wallet_ready':
                            wallet_address = data.get('wallet_address')
                            if user_id and wallet_address:
                                logger.info(f"Received wallet_ready for user {user_id}: {wallet_address}")
                                # Update the user's wallet address in the database
                                try:
                                    from app.services.user_service import UserService
                                    from app.database.session import get_db
                                    async for db in get_db():
                                        user_service = UserService(db)
                                        await user_service.update_user_wallet(user_id, wallet_address)
                                        break
                                except Exception as e:
                                    logger.error(f"Failed to update wallet address for user {user_id}: {e}")
                        
                        # Handle transaction_complete events for withdrawals
                        if message['channel'] == 'transaction_complete':
                            action = data.get('action')
                            if action == 'withdraw':
                                callback_key = f"{user_id}:withdraw"
                                if callback_key in self.wallet_callbacks:
                                    future = self.wallet_callbacks[callback_key]
                                    if not future.done():
                                        future.set_result(data)
                                    del self.wallet_callbacks[callback_key]
                                    logger.info(f"Processed withdrawal callback for user {user_id}")
                        
                        # Handle both wallet_created and agent_responses messages for callbacks
                        elif user_id in self.wallet_callbacks:
                            # Check if this is a successful response with wallet
                            if message['channel'] == 'agent_responses':
                                if data.get('action') == 'start' and data.get('success'):
                                    # Wait for actual wallet creation event
                                    logger.info(f"Agent started for {user_id}, waiting for wallet...")
                                    continue
                            
                            future = self.wallet_callbacks[user_id]
                            if not future.done():
                                future.set_result(data)
                            del self.wallet_callbacks[user_id]
                            logger.info(f"Processed callback for user {user_id}")
                except Exception as e:
                    logger.error(f"Error processing wallet creation message: {e}")
                    
        except Exception as e:
            logger.error(f"Error in wallet creation listener: {e}")
        finally:
            if self._pubsub:
                await self._pubsub.unsubscribe()
                await self._pubsub.close()
    
    async def start_agent(self, user_id: str, wait_for_wallet: bool = True) -> Dict:
        """Smart agent start - handles wallet creation if needed.
        
        Args:
            user_id: The user's wallet address (used as ID)
            wait_for_wallet: Whether to wait for CDP wallet creation (default: True)
        
        Returns:
            Dict with success status and agent/wallet info
        """
        await self._ensure_initialized()
        if not self.redis_client:
            logger.warning("Redis not available, cannot start agent")
            return {'success': False, 'error': 'Redis not available'}
        
        # Prepare command - let agent manager decide if wallet is needed
        command = {
            'action': 'start',
            'user_id': user_id,
            'wait_for_wallet': wait_for_wallet,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # If we should wait for wallet creation
        if wait_for_wallet:
            wallet_future = asyncio.Future()
            self.wallet_callbacks[user_id] = wallet_future
            
            try:
                # Publish command and check if anyone is listening
                num_subscribers = self.redis_client.publish('agent_commands', json.dumps(command))
                logger.info(f"Published start command for {user_id} to {num_subscribers} subscribers, waiting for wallet...")
                
                if num_subscribers == 0:
                    logger.error(f"No subscribers listening on 'agent_commands' channel! Agent manager may not be running or connected.")
                
                # Wait for wallet creation or confirmation
                wallet_data = await asyncio.wait_for(wallet_future, timeout=60)
                
                return {
                    'success': True,
                    'user_id': user_id,
                    'wallet_address': wallet_data.get('wallet_address'),
                    'agent_status': 'running',
                    'wallet_created': wallet_data.get('wallet_created', False)
                }
            except asyncio.TimeoutError:
                if user_id in self.wallet_callbacks:
                    del self.wallet_callbacks[user_id]
                logger.warning(f"Timeout waiting for wallet creation for {user_id}")
                return {'success': False, 'error': 'Wallet creation timeout'}
            except Exception as e:
                if user_id in self.wallet_callbacks:
                    del self.wallet_callbacks[user_id]
                logger.error(f"Error in start_agent with wallet: {e}")
                return {'success': False, 'error': str(e)}
        else:
            # Just start the agent without waiting
            try:
                self.redis_client.publish('agent_commands', json.dumps(command))
                logger.info(f"Published start command for {user_id} (no wait)")
                
                return {
                    'success': True,
                    'user_id': user_id,
                    'status': 'start_requested',
                    'agent_status': 'starting'
                }
            except Exception as e:
                logger.error(f"Error requesting agent start: {e}")
                return {'success': False, 'error': str(e)}
    
    async def request_agent_stop(self, user_id: str) -> bool:
        """Request agent stop."""
        await self._ensure_initialized()
        if not self.redis_client:
            logger.warning("Redis not available, cannot stop agent")
            return False
            
        command = {
            'action': 'stop',
            'user_id': user_id,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        try:
            self.redis_client.publish('agent_commands', json.dumps(command))
            return True
        except Exception as e:
            logger.error(f"Error requesting agent stop: {e}")
            return False
    
    async def get_agent_status(self, user_id: str) -> Optional[Dict]:
        """Get agent status from Redis."""
        await self._ensure_initialized()
        if not self.redis_client:
            logger.warning("Redis not available, cannot get agent status")
            return None
            
        try:
            status_key = f"agent:{user_id}:status"
            status = self.redis_client.get(status_key)
            
            if status:
                return json.loads(status)
            
            return None
        except Exception as e:
            logger.error(f"Error getting agent status: {e}")
            return None
    
    async def list_all_agents(self) -> list:
        """List all agents and their statuses."""
        await self._ensure_initialized()
        if not self.redis_client:
            logger.warning("Redis not available, cannot list agents")
            return []
            
        try:
            pattern = "agent:*:status"
            keys = self.redis_client.keys(pattern)
            
            agents = []
            for key in keys:
                user_id = key.split(':')[1]
                status = self.redis_client.get(key)
                if status:
                    agent_data = json.loads(status)
                    agent_data['user_id'] = user_id
                    agents.append(agent_data)
            
            return agents
        except Exception as e:
            logger.error(f"Error listing agents: {e}")
            return []
    
    async def restart_agent(self, user_id: str) -> Dict:
        """Restart an agent."""
        await self._ensure_initialized()
        if not self.redis_client:
            logger.warning("Redis not available, cannot restart agent")
            return {'success': False, 'error': 'Redis not available'}
            
        command = {
            'action': 'restart',
            'user_id': user_id,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        try:
            self.redis_client.publish('agent_commands', json.dumps(command))
            return {
                'success': True,
                'user_id': user_id,
                'status': 'restart_requested'
            }
        except Exception as e:
            logger.error(f"Error requesting agent restart: {e}")
            return {'success': False, 'error': str(e)}
    
    async def withdraw_usdc(self, user_id: str, amount: float, to_address: str = None) -> Dict:
        """Request USDC withdrawal through agent manager.
        
        Args:
            user_id: The user's wallet address (used as ID)
            amount: Amount of USDC to withdraw
            to_address: Optional destination address (defaults to user_id if not provided)
        
        Returns:
            Dict with success status and transaction info
        """
        await self._ensure_initialized()
        if not self.redis_client:
            logger.warning("Redis not available, cannot process withdrawal")
            return {'success': False, 'error': 'Redis not available'}
        
        # Default to user's own address if not specified
        if not to_address:
            to_address = user_id
        
        # Create withdrawal command
        command = {
            'action': 'withdraw',
            'user_id': user_id,
            'amount_usdc': amount,
            'to_address': to_address,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Set up callback to wait for transaction result
        withdrawal_future = asyncio.Future()
        self.wallet_callbacks[f"{user_id}:withdraw"] = withdrawal_future
        
        try:
            # Publish withdrawal command
            num_subscribers = self.redis_client.publish('agent_commands', json.dumps(command))
            logger.info(f"Published withdraw command for {user_id} ({amount} USDC) to {num_subscribers} subscribers")
            
            if num_subscribers == 0:
                logger.error("No subscribers on 'agent_commands' channel! Agent manager may not be running.")
                del self.wallet_callbacks[f"{user_id}:withdraw"]
                return {'success': False, 'error': 'Agent manager not available'}
            
            # Wait for transaction result (timeout after 30 seconds)
            result = await asyncio.wait_for(withdrawal_future, timeout=30)
            
            return {
                'success': result.get('success', False),
                'tx_hash': result.get('tx_hash'),
                'amount': amount,
                'to_address': to_address,
                'error': result.get('error')
            }
            
        except asyncio.TimeoutError:
            if f"{user_id}:withdraw" in self.wallet_callbacks:
                del self.wallet_callbacks[f"{user_id}:withdraw"]
            logger.warning(f"Timeout waiting for withdrawal transaction for {user_id}")
            return {'success': False, 'error': 'Transaction timeout'}
        except Exception as e:
            if f"{user_id}:withdraw" in self.wallet_callbacks:
                del self.wallet_callbacks[f"{user_id}:withdraw"]
            logger.error(f"Error processing withdrawal: {e}")
            return {'success': False, 'error': str(e)}