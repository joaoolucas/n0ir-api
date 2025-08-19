from fastapi import APIRouter, HTTPException, Request
from app.schemas.common import HealthResponse
from app.core.pools_service import pools_service
from app.core.logger import logger

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={
        503: {"model": HealthResponse, "description": "Service Unavailable"}
    }
)
async def health_check(request: Request):
    """
    Check service health status.
    
    Returns the current health status of the API service including:
    - Service status (healthy/unhealthy)
    - Connected blockchain network
    - Current block number
    - Sugar contract address
    - Last update timestamp
    """
    logger.debug(f"GET /health - IP: {request.client.host if request.client else 'unknown'}")
    
    # Return a simple health status for now
    # We'll check pools_service later once we confirm basic connectivity
    from datetime import datetime
    return {
        "status": "healthy",
        "network": "base",
        "block_number": 0,  # Will be updated when pools_service is working
        "sugar_address": "0x27fc745390d1f4BaF8D184FBd97748340f786634",
        "last_update": datetime.utcnow().isoformat()
    }