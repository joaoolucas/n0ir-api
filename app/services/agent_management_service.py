import redis
import json
import asyncio
from typing import Dict, Optional
from datetime import datetime
from loguru import logger
from app.core.config import settings


class AgentManagementService:
    def __init__(self):
        try:
            # Handle Railway template variable format
            redis_url = settings.redis_url
            if redis_url and not redis_url.startswith(('redis://', 'rediss://')):
                logger.warning(f"Invalid Redis URL format: {redis_url[:20]}...")
                redis_url = None
            
            if redis_url:
                self.redis_client = redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_connect_timeout=5
                )
                # Test connection
                self.redis_client.ping()
                logger.info("Redis connection established")
            else:
                logger.warning("Redis URL not configured, running without Redis")
                self.redis_client = None
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}. Running without Redis.")
            self.redis_client = None
            
        self.wallet_callbacks = {}
        self._listener_task = None
        
    async def start_listener(self):
        """Start listening for wallet creation events."""
        if self.redis_client and self._listener_task is None:
            self._listener_task = asyncio.create_task(self._listen_for_wallet_creation())
    
    async def _listen_for_wallet_creation(self):
        """Listen for wallet creation events from agent manager."""
        if not self.redis_client:
            return
            
        try:
            pubsub = self.redis_client.pubsub()
            # Listen for both wallet_created and agent_responses
            pubsub.subscribe('wallet_created', 'agent_responses')
            
            while True:
                try:
                    message = pubsub.get_message(timeout=0.1)
                    if message and message['type'] == 'message':
                        data = json.loads(message['data'])
                        user_id = data.get('user_id')
                        
                        # Handle both wallet_created and agent_responses messages
                        if user_id in self.wallet_callbacks:
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
                except Exception as e:
                    logger.error(f"Error processing wallet creation message: {e}")
                
                await asyncio.sleep(0.1)
                
        except Exception as e:
            logger.error(f"Error in wallet creation listener: {e}")
    
    async def start_agent(self, user_id: str, wait_for_wallet: bool = True) -> Dict:
        """Smart agent start - handles wallet creation if needed.
        
        Args:
            user_id: The user's wallet address (used as ID)
            wait_for_wallet: Whether to wait for CDP wallet creation (default: True)
        
        Returns:
            Dict with success status and agent/wallet info
        """
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
                self.redis_client.publish('agent_commands', json.dumps(command))
                logger.info(f"Published start command for {user_id}, waiting for wallet...")
                
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