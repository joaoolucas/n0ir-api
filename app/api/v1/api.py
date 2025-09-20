from fastapi import APIRouter, Depends
from app.api.v1.endpoints import blockchain, health, strategy, users
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

api_router.include_router(
    strategy.router,
    tags=["Strategy"],
    dependencies=[Depends(verify_bearer_token)]
)

api_router.include_router(
    users.router,
    tags=["Users"],
    dependencies=[Depends(verify_bearer_token)]
)