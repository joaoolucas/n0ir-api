from fastapi import APIRouter, Depends
from app.api.v1.endpoints import blockchain, health, core, info, admin, allocation
from app.core.auth import verify_bearer_token

api_router = APIRouter()

# Include health endpoint without auth (for monitoring)
api_router.include_router(
    health.router,
    tags=["Health"]
)

# Include admin endpoints (auth handled per-endpoint)
api_router.include_router(
    admin.router,
    prefix="/admin",
    tags=["Admin"]
)

# Include blockchain endpoints (auth handled per-endpoint)
api_router.include_router(
    blockchain.router,
    tags=["Blockchain"]
)

# Include Core endpoints for essential operations
# Auth handled per-endpoint (JWT session tokens)
api_router.include_router(
    core.router,
    tags=["Core"]
)

# Include Info endpoints for querying data
# Auth handled per-endpoint (JWT session tokens or Bearer token)
api_router.include_router(
    info.router,
    tags=["Info"]
)

# Include Allocation endpoints for capital management
# Auth handled per-endpoint (JWT session tokens)
api_router.include_router(
    allocation.router,
    tags=["Capital Allocation"]
)