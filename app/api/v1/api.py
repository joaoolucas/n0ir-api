from fastapi import APIRouter, Depends
from app.api.v1.endpoints import blockchain, health, core, info
from app.core.auth import verify_bearer_token

api_router = APIRouter()

# Include health endpoint without auth (for monitoring)
api_router.include_router(
    health.router,
    tags=["Health"]
)

# Include blockchain endpoints with Bearer token authentication
api_router.include_router(
    blockchain.router,
    tags=["Blockchain"],
    dependencies=[Depends(verify_bearer_token)]
)

# Include Core endpoints for essential operations
api_router.include_router(
    core.router,
    tags=["Core"],
    dependencies=[Depends(verify_bearer_token)]
)

# Include Info endpoints for querying data
api_router.include_router(
    info.router,
    tags=["Info"],
    dependencies=[Depends(verify_bearer_token)]
)