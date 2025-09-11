# Implementation Steps for Railway Individual Agents (Option 1)

## Overview

Complete implementation plan for individual agents with CDP wallet creation integrated into the agent process. This involves three repositories: n0ir-api, n0ir-agent-manager (new), and n0ir-executor.

## Architecture Flow

```
User Signs Up → API → Agent-Manager → Spawn Process → Create CDP Wallet → Report Back → API Updates User
```

## Phase 1: Create Agent Manager Service (Week 1)

### Step 1.1: Create New Repository/Directory

```bash
# Create agent-manager service directory
mkdir n0ir-agent-manager
cd n0ir-agent-manager

# Initialize project structure
mkdir src
mkdir tests
touch requirements.txt
touch Dockerfile
touch railway.toml
touch .env.example
```

### Step 1.2: Set Up Core Dependencies

```python
# requirements.txt
fastapi==0.104.1
uvicorn==0.24.0
redis==5.0.1
psutil==5.9.6
loguru==0.7.2
asyncio==3.4.3
multiprocessing-logging==0.3.4
python-dotenv==1.0.0
sqlalchemy==2.0.23
asyncpg==0.29.0
aiohttp==3.9.1
```

### Step 1.3: Create AgentProcessManager

```python
# src/agent_process_manager.py
import asyncio
import multiprocessing as mp
from multiprocessing import Queue
import signal
import os
from typing import Dict, Optional
from datetime import datetime
import json
import redis
import psutil
from loguru import logger

class AgentProcessManager:
    """Core manager for individual agent processes."""
    
    def __init__(self):
        self.processes: Dict[str, mp.Process] = {}
        self.message_queues: Dict[str, Queue] = {}
        self.redis_client = self._init_redis()
        self.max_agents = int(os.getenv('MAX_AGENTS', '50'))
        self.agent_memory_mb = int(os.getenv('AGENT_MEMORY_MB', '256'))
        
    def _init_redis(self):
        """Initialize Redis connection."""
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        return redis.from_url(redis_url, decode_responses=True)
    
    async def start(self):
        """Main entry point for the manager."""
        logger.info("Starting Agent Process Manager...")
        
        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)
        
        # Start background tasks
        tasks = [
            asyncio.create_task(self._monitor_processes()),
            asyncio.create_task(self._listen_for_commands()),
            asyncio.create_task(self._monitor_resources()),
            asyncio.create_task(self._restore_previous_agents()),
            asyncio.create_task(self._listen_for_wallet_reports())  # NEW
        ]
        
        # Run forever
        await asyncio.gather(*tasks)
    
    async def _listen_for_wallet_reports(self):
        """Listen for wallet creation reports from agent processes."""
        pubsub = self.redis_client.pubsub()
        pubsub.subscribe('wallet_created')
        
        for message in pubsub.listen():
            if message['type'] == 'message':
                try:
                    data = json.loads(message['data'])
                    user_id = data['user_id']
                    wallet_address = data['wallet_address']
                    
                    logger.info(f"Wallet created for user {user_id}: {wallet_address}")
                    
                    # Store wallet info
                    self.redis_client.hset(
                        f"user_wallets",
                        user_id,
                        json.dumps({
                            'wallet_address': wallet_address,
                            'created_at': datetime.utcnow().isoformat()
                        })
                    )
                    
                    # Notify API that wallet is ready
                    self.redis_client.publish(
                        'wallet_ready',
                        json.dumps({
                            'user_id': user_id,
                            'wallet_address': wallet_address
                        })
                    )
                    
                except Exception as e:
                    logger.error(f"Error processing wallet report: {e}")
    
    async def start_agent(self, user_id: str) -> Dict:
        """Start an agent process for a user."""
        if user_id in self.processes:
            logger.info(f"Agent already running for user {user_id}")
            return {'success': True, 'status': 'already_running'}
        
        if len(self.processes) >= self.max_agents:
            logger.error(f"Max agents limit reached ({self.max_agents})")
            return {'success': False, 'error': 'max_agents_reached'}
        
        try:
            # Create process
            process = mp.Process(
                target=run_agent_process,
                args=(user_id,),
                name=f"agent_{user_id}"
            )
            process.start()
            
            self.processes[user_id] = process
            
            # Store state in Redis
            self.redis_client.hset(
                'active_agents',
                user_id,
                json.dumps({
                    'pid': process.pid,
                    'started_at': datetime.utcnow().isoformat(),
                    'status': 'starting'  # Will change to 'running' after wallet creation
                })
            )
            
            logger.info(f"Started agent for user {user_id} (PID: {process.pid})")
            return {'success': True, 'pid': process.pid}
            
        except Exception as e:
            logger.error(f"Failed to start agent for {user_id}: {e}")
            return {'success': False, 'error': str(e)}
    
    async def stop_agent(self, user_id: str) -> bool:
        """Stop an agent process."""
        # Implementation from the spec
        pass
```

### Step 1.4: Create Agent Runner with Wallet Creation

```python
# src/agent_runner.py
"""Individual agent process runner with CDP wallet creation."""
import asyncio
import os
import sys
import redis
import json
from datetime import datetime
from loguru import logger

# Add n0ir-executor to path
sys.path.append(os.getenv('EXECUTOR_PATH', '/app/executor'))

def run_agent_process(user_id: str):
    """Entry point for individual agent process with wallet creation."""
    
    # Configure for specific user
    os.environ['USER_ID'] = user_id
    os.environ['WALLET_IDEMPOTENCY_KEY'] = f"user_{user_id}"
    
    # Import executor and wallet manager (from n0ir-executor)
    from executor.src.main import Executor
    from executor.src.wallets.manager import WalletManager
    
    # Initialize Redis for reporting
    redis_client = redis.from_url(
        os.getenv('REDIS_URL', 'redis://localhost:6379'),
        decode_responses=True
    )
    
    async def main():
        try:
            logger.info(f"Starting agent for user {user_id}")
            
            # Check if wallet already exists
            wallet_info = redis_client.hget('user_wallets', user_id)
            
            if not wallet_info:
                # Create CDP wallet for this user
                logger.info(f"Creating CDP wallet for user {user_id}")
                
                wallet_manager = WalletManager()
                wallet_manager.settings.wallet_idempotency_key = f"user_{user_id}"
                await wallet_manager.initialize()
                
                wallet_address = wallet_manager.wallet_address
                
                logger.info(f"Wallet created for user {user_id}: {wallet_address}")
                
                # Report wallet creation back via Redis
                redis_client.publish(
                    'wallet_created',
                    json.dumps({
                        'user_id': user_id,
                        'wallet_address': wallet_address,
                        'owner_address': wallet_manager.owner_account.address if wallet_manager.owner_account else None,
                        'created_at': datetime.utcnow().isoformat()
                    })
                )
                
                # Store wallet locally for future reference
                redis_client.hset(
                    'user_wallets',
                    user_id,
                    json.dumps({
                        'wallet_address': wallet_address,
                        'created_at': datetime.utcnow().isoformat()
                    })
                )
            else:
                wallet_data = json.loads(wallet_info)
                wallet_address = wallet_data['wallet_address']
                logger.info(f"Using existing wallet for user {user_id}: {wallet_address}")
            
            # Update agent status to running
            redis_client.hset(
                'active_agents',
                user_id,
                json.dumps({
                    'status': 'running',
                    'wallet_address': wallet_address,
                    'updated_at': datetime.utcnow().isoformat()
                })
            )
            
            # Now run the executor with the wallet
            executor = Executor(
                user_id=user_id,
                mode='individual',
                wallet_address=wallet_address
            )
            
            await executor.initialize()
            await executor.run()
            
        except Exception as e:
            logger.error(f"Agent {user_id} crashed: {e}")
            
            # Report failure
            redis_client.hset(
                'active_agents',
                user_id,
                json.dumps({
                    'status': 'failed',
                    'error': str(e),
                    'updated_at': datetime.utcnow().isoformat()
                })
            )
            raise
    
    # Run the agent
    asyncio.run(main())
```

## Phase 2: Modify n0ir-executor for Multi-User Support (Week 1)

### Step 2.1: Add Individual Mode to Executor

```python
# n0ir-executor/src/main.py modifications
class Executor:
    def __init__(self, user_id: Optional[str] = None, mode: str = 'standalone'):
        self.user_id = user_id
        self.mode = mode  # 'standalone' or 'individual'
        
        if mode == 'individual':
            # Configure for specific user
            self._configure_for_user(user_id)
    
    def _configure_for_user(self, user_id: str):
        """Configure executor for specific user."""
        # Set user-specific configuration
        self.wallet_key = f"user_{user_id}"
        self.redis_prefix = f"agent:{user_id}:"
        self.log_prefix = f"[User:{user_id}]"
```

### Step 2.2: Add State Isolation

```python
# n0ir-executor/src/state_manager.py
class UserStateManager:
    """Manage state for individual user agents."""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.redis_key_prefix = f"user:{user_id}:"
    
    async def save_state(self, state: dict):
        """Save user-specific state."""
        key = f"{self.redis_key_prefix}state"
        await self.redis_client.set(key, json.dumps(state))
    
    async def load_state(self) -> dict:
        """Load user-specific state."""
        key = f"{self.redis_key_prefix}state"
        state = await self.redis_client.get(key)
        return json.loads(state) if state else {}
```

## Phase 3: API Integration with Wallet Creation (Week 2)

### Step 3.1: Add Agent Management Service with Wallet Handling

```python
# n0ir-api/app/services/agent_management_service.py
import redis
import json
import asyncio
from typing import Dict, Optional
from datetime import datetime
from loguru import logger

class AgentManagementService:
    """Service for managing user agents and wallet creation."""
    
    def __init__(self):
        self.redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True
        )
        # Start wallet listener in background
        asyncio.create_task(self._listen_for_wallet_creation())
        self.wallet_callbacks = {}
    
    async def _listen_for_wallet_creation(self):
        """Listen for wallet creation notifications."""
        pubsub = self.redis_client.pubsub()
        pubsub.subscribe('wallet_ready')
        
        for message in pubsub.listen():
            if message['type'] == 'message':
                try:
                    data = json.loads(message['data'])
                    user_id = data['user_id']
                    
                    # Trigger callback if waiting
                    if user_id in self.wallet_callbacks:
                        self.wallet_callbacks[user_id].set_result(data)
                        del self.wallet_callbacks[user_id]
                        
                except Exception as e:
                    logger.error(f"Error processing wallet ready: {e}")
    
    async def request_agent_start_with_wallet(self, user_id: str) -> Dict:
        """Request agent start and wait for wallet creation."""
        
        # Setup callback for wallet creation
        wallet_future = asyncio.Future()
        self.wallet_callbacks[user_id] = wallet_future
        
        # Request agent start
        command = {
            'action': 'start',
            'user_id': user_id,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        self.redis_client.publish('agent_commands', json.dumps(command))
        
        try:
            # Wait for wallet creation (timeout 60 seconds for CDP wallet deployment)
            wallet_data = await asyncio.wait_for(wallet_future, timeout=60)
            
            return {
                'success': True,
                'user_id': user_id,
                'wallet_address': wallet_data['wallet_address'],
                'agent_status': 'running'
            }
            
        except asyncio.TimeoutError:
            logger.error(f"Wallet creation timeout for user {user_id}")
            # Clean up callback
            if user_id in self.wallet_callbacks:
                del self.wallet_callbacks[user_id]
            
            return {
                'success': False,
                'error': 'Wallet creation timeout'
            }
    
    async def request_agent_stop(self, user_id: str) -> bool:
        """Request agent stop."""
        command = {
            'action': 'stop',
            'user_id': user_id
        }
        
        self.redis_client.publish('agent_commands', json.dumps(command))
        return True
    
    async def get_agent_status(self, user_id: str) -> Optional[Dict]:
        """Get current agent status."""
        data = self.redis_client.hget('active_agents', user_id)
        return json.loads(data) if data else None
    
    async def get_wallet_info(self, user_id: str) -> Optional[Dict]:
        """Get wallet info for user."""
        data = self.redis_client.hget('user_wallets', user_id)
        return json.loads(data) if data else None
```

### Step 3.2: Create API Endpoints

```python
# n0ir-api/app/api/v1/endpoints/agents.py
from fastapi import APIRouter, Depends, HTTPException
from app.services.agent_management_service import AgentManagementService

router = APIRouter(prefix="/agents")

@router.post("/start/{user_id}")
async def start_agent(
    user_id: str,
    service: AgentManagementService = Depends()
):
    """Start agent for user."""
    result = await service.request_agent_start(user_id)
    
    if not result.get('success'):
        raise HTTPException(status_code=500, detail="Failed to start agent")
    
    return result

@router.post("/stop/{user_id}")
async def stop_agent(
    user_id: str,
    service: AgentManagementService = Depends()
):
    """Stop agent for user."""
    success = await service.request_agent_stop(user_id)
    return {"success": success}

@router.get("/status/{user_id}")
async def get_agent_status(
    user_id: str,
    service: AgentManagementService = Depends()
):
    """Get agent status."""
    status = await service.get_agent_status(user_id)
    
    if not status:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return status
```

### Step 3.3: Modify User Creation Flow with Wallet Creation

```python
# n0ir-api/app/api/v1/endpoints/users.py modifications
@router.post("/create-with-agent", response_model=UserResponse)
async def create_user_with_agent(
    request: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
    agent_service: AgentManagementService = Depends()
):
    """Create user, start agent, and wait for CDP wallet creation."""
    
    # Step 1: Create user record (without wallet initially)
    user_service = UserService(db)
    user = await user_service.create_user(
        user_id=request.user_id,
        email=request.email,
        status='pending_wallet'  # Initial status
    )
    
    try:
        # Step 2: Start agent and wait for wallet creation
        logger.info(f"Starting agent and creating wallet for user {request.user_id}")
        
        agent_result = await agent_service.request_agent_start_with_wallet(request.user_id)
        
        if agent_result.get('success'):
            # Step 3: Update user with wallet information
            wallet_address = agent_result['wallet_address']
            
            await user_service.update_user(
                user_id=request.user_id,
                wallet_address=wallet_address,
                cdp_wallet_name=f"n0ir-user-{request.user_id}",
                cdp_owner_wallet_address=wallet_address,  # Will be updated with actual owner
                cdp_owner_wallet_name=f"n0ir-owner-{request.user_id}",
                status='active',
                agent_status='running'
            )
            
            logger.info(f"User {request.user_id} created with wallet {wallet_address}")
            
            # Refresh user data
            user = await user_service.get_user(request.user_id)
            
            return UserResponse.model_validate(user)
        else:
            # Wallet creation failed
            logger.error(f"Failed to create wallet for user {request.user_id}: {agent_result.get('error')}")
            
            # Update user status
            await user_service.update_user(
                user_id=request.user_id,
                status='wallet_creation_failed'
            )
            
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create wallet: {agent_result.get('error')}"
            )
            
    except Exception as e:
        logger.error(f"Error creating user with agent: {e}")
        
        # Clean up - mark user as failed
        await user_service.update_user(
            user_id=request.user_id,
            status='creation_failed'
        )
        
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users/{user_id}/wallet")
async def get_user_wallet(
    user_id: str,
    agent_service: AgentManagementService = Depends()
):
    """Get wallet info for user."""
    wallet_info = await agent_service.get_wallet_info(user_id)
    
    if not wallet_info:
        raise HTTPException(status_code=404, detail="Wallet not found")
    
    return wallet_info

@router.post("/users/{user_id}/retry-wallet")
async def retry_wallet_creation(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    agent_service: AgentManagementService = Depends()
):
    """Retry wallet creation for a user."""
    user_service = UserService(db)
    user = await user_service.get_user(user_id)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.wallet_address:
        return {"message": "User already has a wallet", "wallet_address": user.wallet_address}
    
    # Retry agent start and wallet creation
    agent_result = await agent_service.request_agent_start_with_wallet(user_id)
    
    if agent_result.get('success'):
        await user_service.update_user(
            user_id=user_id,
            wallet_address=agent_result['wallet_address'],
            status='active'
        )
        return agent_result
    else:
        raise HTTPException(status_code=500, detail="Failed to create wallet")
```

## Phase 4: Railway Deployment Configuration (Week 2)

### Step 4.1: Create Railway Configuration

```toml
# agent-manager/railway.toml
[build]
builder = "DOCKERFILE"

[deploy]
startCommand = "python -m src.main"
healthcheckPath = "/health"
healthcheckTimeout = 100
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3

[[services]]
name = "agent-manager"
  [services.deploy]
  memory = "4GB"
  cpu = "2"
```

### Step 4.2: Create Dockerfile

```dockerfile
# agent-manager/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent-manager code
COPY src/ ./src/

# Copy executor code (for agent processes)
COPY --from=executor-build /app/executor ./executor

# Create startup script
COPY start.sh .
RUN chmod +x start.sh

CMD ["./start.sh"]
```

### Step 4.3: Environment Variables

```bash
# Railway environment variables to set
MAX_AGENTS=50
AGENT_MEMORY_MB=256
REDIS_URL=${REDIS_URL}
DATABASE_URL=${DATABASE_URL}
CDP_API_KEY_ID=${CDP_API_KEY_ID}
CDP_API_KEY_SECRET=${CDP_API_KEY_SECRET}
API_URL=https://${API_SERVICE}.railway.app
EXECUTOR_PATH=/app/executor
```

## Phase 5: Monitoring & Production Features (Week 3)

### Step 5.1: Add Health Checks

```python
# src/health.py
from fastapi import FastAPI
import psutil

app = FastAPI()

@app.get("/health")
async def health_check():
    """Health check for Railway."""
    
    manager = get_manager_instance()
    
    return {
        "status": "healthy",
        "active_agents": len(manager.processes),
        "max_agents": manager.max_agents,
        "memory_usage_percent": psutil.virtual_memory().percent,
        "cpu_usage_percent": psutil.cpu_percent(),
        "uptime_seconds": manager.get_uptime()
    }

@app.get("/metrics")
async def metrics():
    """Prometheus metrics."""
    # Return metrics in Prometheus format
    pass
```

### Step 5.2: Implement Graceful Shutdown

```python
# src/shutdown_handler.py
class GracefulShutdown:
    """Handle graceful shutdown."""
    
    async def shutdown(self):
        """Gracefully shutdown all agents."""
        logger.info("Starting graceful shutdown...")
        
        # Save all agent states
        for user_id in self.processes:
            await self.save_agent_state(user_id)
        
        # Stop all agents with timeout
        await asyncio.gather(*[
            self.stop_agent_gracefully(user_id) 
            for user_id in self.processes
        ])
        
        logger.info("Graceful shutdown complete")
```

### Step 5.3: Add State Persistence

```python
# src/state_persistence.py
class StatePersistence:
    """Persist and restore agent states."""
    
    async def persist_all_states(self):
        """Persist all agent states to Redis."""
        for user_id, process in self.processes.items():
            if process.is_alive():
                state = await self.get_agent_state(user_id)
                await self.redis_client.setex(
                    f"agent_state:{user_id}",
                    86400,  # 24 hour TTL
                    json.dumps(state)
                )
    
    async def restore_agents(self):
        """Restore agents from persisted state."""
        # Get all users who had active agents
        pattern = "agent_state:*"
        for key in self.redis_client.scan_iter(pattern):
            user_id = key.split(':')[1]
            await self.start_agent(user_id)
```

## Phase 6: Testing & Validation (Week 3)

### Step 6.1: Local Testing

```bash
# Test locally with docker-compose
docker-compose up -d redis postgres
python -m src.main

# In another terminal, test agent creation
curl -X POST http://localhost:8001/agents/start/test_user_1
curl -X POST http://localhost:8001/agents/start/test_user_2
curl http://localhost:8001/health
```

### Step 6.2: Load Testing

```python
# tests/load_test.py
import asyncio
import aiohttp

async def create_test_users(count: int):
    """Create multiple test users with agents."""
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for i in range(count):
            user_id = f"test_user_{i}"
            task = session.post(
                f"http://localhost:8000/api/v1/users/create-with-agent",
                json={"user_id": user_id}
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        return results

# Test with 20 concurrent users
asyncio.run(create_test_users(20))
```

### Step 6.3: Integration Tests

```python
# tests/test_integration.py
async def test_full_flow():
    """Test complete user + agent creation flow."""
    
    # Create user
    user = await create_user_with_agent("test_user")
    assert user.agent_status == "active"
    
    # Check agent is running
    status = await get_agent_status("test_user")
    assert status["status"] == "running"
    
    # Stop agent
    await stop_agent("test_user")
    
    # Verify stopped
    status = await get_agent_status("test_user")
    assert status is None
```

## Deployment Checklist

### Pre-Deployment
- [ ] All tests passing locally
- [ ] Docker build successful
- [ ] Environment variables configured in Railway
- [ ] Redis and PostgreSQL provisioned in Railway

### Deployment Steps
1. [ ] Deploy agent-manager service to Railway
2. [ ] Deploy updated n0ir-api with agent endpoints
3. [ ] Deploy updated n0ir-executor with individual mode
4. [ ] Verify health checks passing
5. [ ] Test with single user
6. [ ] Load test with 10 users
7. [ ] Monitor resource usage

### Post-Deployment
- [ ] Monitor logs for errors
- [ ] Check memory/CPU usage
- [ ] Verify agent auto-restart on failure
- [ ] Test graceful shutdown
- [ ] Document any issues

## Complete Flow Diagram

### User Registration with Wallet Creation Flow

```
1. Frontend: User signs up
      ↓
2. API: POST /users/create-with-agent
      ↓
3. API: Create user record (status: 'pending_wallet')
      ↓
4. API: Publish to Redis 'agent_commands' → {'action': 'start', 'user_id': 'alice'}
      ↓
5. Agent-Manager: Receives command
      ↓
6. Agent-Manager: Spawns new process for user
      ↓
7. Agent Process: Checks if wallet exists
      ↓
8. Agent Process: Creates CDP wallet (using WalletManager)
      ↓
9. Agent Process: Publishes to Redis 'wallet_created' → {'user_id': 'alice', 'wallet_address': '0x...'}
      ↓
10. Agent-Manager: Forwards to 'wallet_ready' channel
      ↓
11. API: Receives wallet info
      ↓
12. API: Updates user record with wallet address
      ↓
13. API: Returns complete user data to Frontend
```

### Redis Communication Channels

```
agent_commands     : API → Agent-Manager (start/stop commands)
wallet_created     : Agent Process → Agent-Manager (wallet creation notification)
wallet_ready       : Agent-Manager → API (wallet ready notification)
active_agents      : Redis Hash (agent status storage)
user_wallets       : Redis Hash (wallet info storage)
```

## Key Implementation Details

### Wallet Creation Logic
- **Location**: Agent process (agent_runner.py)
- **When**: First time agent starts for a user
- **How**: Uses existing WalletManager from n0ir-executor
- **Idempotency**: Uses user_id to ensure one wallet per user

### Error Handling
- **Wallet Creation Timeout**: 60 seconds
- **Failed Creation**: User marked as 'wallet_creation_failed'
- **Retry Mechanism**: POST /users/{user_id}/retry-wallet endpoint
- **Process Crash**: Auto-restart with state recovery

### State Management
- **Agent Status**: Stored in Redis 'active_agents' hash
- **Wallet Info**: Stored in Redis 'user_wallets' hash
- **User Record**: Stored in PostgreSQL with wallet address

## Timeline

### Week 1
- Days 1-2: Create agent-manager service with process management
- Days 3-4: Modify executor for multi-user and wallet creation
- Day 5: Initial testing with mock users

### Week 2  
- Days 1-2: API integration with wallet creation flow
- Days 3-4: Railway deployment setup
- Day 5: Deploy to staging and test

### Week 3
- Days 1-2: Add monitoring, health checks, and error recovery
- Days 3-4: Load testing with multiple users
- Day 5: Production deployment

## Repository Changes Summary

### 1. n0ir-agent-manager (NEW)
- Process management for individual agents
- Redis pub/sub for commands
- Wallet creation monitoring
- Health checks and metrics

### 2. n0ir-executor (MODIFY)
- Add 'individual' mode
- Wallet creation on first run
- Redis reporting for wallet creation
- User-specific state isolation

### 3. n0ir-api (MODIFY)
- Agent management service
- User creation with wallet flow
- Wallet status endpoints
- Redis integration for agent commands

## Next Immediate Actions

1. **Create agent-manager repository**
   ```bash
   git init n0ir-agent-manager
   cd n0ir-agent-manager
   mkdir src tests
   touch requirements.txt Dockerfile railway.toml
   ```

2. **Copy the complete AgentProcessManager code from this spec**

3. **Modify n0ir-executor to add individual mode**
   ```python
   # In executor main.py
   if mode == 'individual':
       # User-specific configuration
   ```

4. **Update n0ir-api with agent service**
   ```python
   # Create app/services/agent_management_service.py
   # Update users.py endpoints
   ```

5. **Set up Railway project**
   - Create new service for agent-manager
   - Configure environment variables
   - Link to existing Redis/PostgreSQL

## Success Criteria

- [ ] User can sign up and automatically get CDP wallet
- [ ] Each user has dedicated agent process
- [ ] Wallet creation completes within 60 seconds
- [ ] Agent processes auto-restart on failure
- [ ] Can handle 50+ concurrent users
- [ ] Graceful shutdown preserves state
- [ ] Monitoring shows agent health and resource usage

This complete implementation plan integrates wallet creation into the agent process, ensuring each user gets both their dedicated agent and CDP wallet automatically!