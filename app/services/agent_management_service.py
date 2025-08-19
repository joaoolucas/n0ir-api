import redis
import json
import asyncio
from typing import Dict, Optional
from datetime import datetime
from loguru import logger
from app.core.config import settings


class AgentManagementService:
    def __init__(self):
        self.redis_client = redis.from_url(
            settings.redis_url,
            decode_responses=True
        )
        self.wallet_callbacks = {}
        self._listener_task = None
        
    async def start_listener(self):
        """Start listening for wallet creation events."""
        if self._listener_task is None:
            self._listener_task = asyncio.create_task(self._listen_for_wallet_creation())
    
    async def _listen_for_wallet_creation(self):
        """Listen for wallet creation events from agent manager."""
        try:
            pubsub = self.redis_client.pubsub()
            pubsub.subscribe('wallet_created')
            
            while True:
                try:
                    message = pubsub.get_message(timeout=0.1)
                    if message and message['type'] == 'message':
                        data = json.loads(message['data'])
                        user_id = data.get('user_id')
                        
                        if user_id in self.wallet_callbacks:
                            future = self.wallet_callbacks[user_id]
                            if not future.done():
                                future.set_result(data)
                            del self.wallet_callbacks[user_id]
                except Exception as e:
                    logger.error(f"Error processing wallet creation message: {e}")
                
                await asyncio.sleep(0.1)
                
        except Exception as e:
            logger.error(f"Error in wallet creation listener: {e}")
    
    async def request_agent_start_with_wallet(self, user_id: str) -> Dict:
        """Request agent start and wait for wallet creation."""
        wallet_future = asyncio.Future()
        self.wallet_callbacks[user_id] = wallet_future
        
        command = {
            'action': 'start',
            'user_id': user_id,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        self.redis_client.publish('agent_commands', json.dumps(command))
        
        try:
            wallet_data = await asyncio.wait_for(wallet_future, timeout=60)
            return {
                'success': True,
                'user_id': user_id,
                'wallet_address': wallet_data['wallet_address'],
                'agent_status': 'running'
            }
        except asyncio.TimeoutError:
            if user_id in self.wallet_callbacks:
                del self.wallet_callbacks[user_id]
            return {'success': False, 'error': 'Wallet creation timeout'}
        except Exception as e:
            if user_id in self.wallet_callbacks:
                del self.wallet_callbacks[user_id]
            logger.error(f"Error in request_agent_start_with_wallet: {e}")
            return {'success': False, 'error': str(e)}
    
    async def request_agent_start(self, user_id: str) -> Dict:
        """Request agent start without waiting for wallet."""
        command = {
            'action': 'start',
            'user_id': user_id,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        try:
            self.redis_client.publish('agent_commands', json.dumps(command))
            return {
                'success': True,
                'user_id': user_id,
                'status': 'start_requested'
            }
        except Exception as e:
            logger.error(f"Error requesting agent start: {e}")
            return {'success': False, 'error': str(e)}
    
    async def request_agent_stop(self, user_id: str) -> bool:
        """Request agent stop."""
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