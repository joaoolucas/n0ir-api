from fastapi import APIRouter, HTTPException
from app.schemas.common import HealthResponse
from app.core.pools_service import pools_service

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={
        503: {"model": HealthResponse, "description": "Service Unavailable"}
    }
)
async def health_check():
    """
    Check service health status.
    
    Returns the current health status of the API service including:
    - Service status (healthy/unhealthy)
    - Connected blockchain network
    - Current block number
    - Sugar contract address
    - Last update timestamp
    """
    try:
        health_status = await pools_service.get_health()
        
        if health_status["status"] == "unhealthy":
            raise HTTPException(
                status_code=503,
                detail=health_status
            )
        
        return health_status
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "network": "base",
                "error": str(e)
            }
        )