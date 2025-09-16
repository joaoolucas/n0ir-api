"""Health check endpoints for monitoring system status."""

from fastapi import APIRouter
from typing import Dict, Any
from datetime import datetime

router = APIRouter()


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Basic health check endpoint.
    
    Returns:
        Dictionary with service status
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "n0ir-api"
    }