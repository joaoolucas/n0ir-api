from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, List
from app.services.agent_management_service import AgentManagementService


router = APIRouter(prefix="/agents", tags=["agents"])

# Create a singleton instance of the service
agent_service = AgentManagementService()


@router.post("/start/{user_id}")
async def start_agent(user_id: str) -> Dict:
    """Start agent for user."""
    result = await agent_service.request_agent_start(user_id)
    if not result.get('success'):
        raise HTTPException(status_code=500, detail=result.get('error', 'Failed to start agent'))
    return result


@router.post("/start-with-wallet/{user_id}")
async def start_agent_with_wallet(user_id: str) -> Dict:
    """Start agent for user and wait for wallet creation."""
    result = await agent_service.request_agent_start_with_wallet(user_id)
    if not result.get('success'):
        raise HTTPException(status_code=500, detail=result.get('error', 'Failed to start agent'))
    return result


@router.post("/stop/{user_id}")
async def stop_agent(user_id: str) -> Dict:
    """Stop agent for user."""
    success = await agent_service.request_agent_stop(user_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to stop agent")
    return {"success": success, "user_id": user_id}


@router.post("/restart/{user_id}")
async def restart_agent(user_id: str) -> Dict:
    """Restart agent for user."""
    result = await agent_service.restart_agent(user_id)
    if not result.get('success'):
        raise HTTPException(status_code=500, detail=result.get('error', 'Failed to restart agent'))
    return result


@router.get("/status/{user_id}")
async def get_agent_status(user_id: str) -> Dict:
    """Get agent status."""
    status = await agent_service.get_agent_status(user_id)
    if not status:
        raise HTTPException(status_code=404, detail="Agent not found")
    return status


@router.get("/")
async def list_agents() -> List[Dict]:
    """List all agents and their statuses."""
    agents = await agent_service.list_all_agents()
    return agents


@router.on_event("startup")
async def startup_event():
    """Start the wallet creation listener on startup."""
    await agent_service.start_listener()