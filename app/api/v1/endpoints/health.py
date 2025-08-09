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
    logger.debug(f"GET /health - IP: {request.client.host}")
    try:
        health_status = await pools_service.get_health()
        
        if health_status["status"] == "unhealthy":
            logger.warning(f"Service unhealthy: {health_status}")
            raise HTTPException(
                status_code=503,
                detail=health_status
            )
        
        logger.debug("Health check passed")
        return health_status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "network": "base",
                "error": str(e)
            }
        )