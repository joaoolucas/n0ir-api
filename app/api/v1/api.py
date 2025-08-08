from fastapi import APIRouter
from app.api.v1.endpoints import pools, tokens, health

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(
    health.router,
    tags=["Health"]
)

api_router.include_router(
    pools.router,
    tags=["Pools"]
)

api_router.include_router(
    tokens.router,
    tags=["Tokens"]
)