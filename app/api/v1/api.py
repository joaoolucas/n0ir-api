from fastapi import APIRouter, Depends
from app.api.v1.endpoints import pools, tokens, health, positions, wallets, strategy, users, transactions, admin
from app.core.auth import verify_bearer_token

api_router = APIRouter()

# Include health endpoint without auth (for monitoring)
api_router.include_router(
    health.router,
    tags=["Health"]
)

# Include all other endpoints with Bearer token authentication
api_router.include_router(
    pools.router,
    tags=["Pools"],
    dependencies=[Depends(verify_bearer_token)]
)

api_router.include_router(
    tokens.router,
    tags=["Tokens"],
    dependencies=[Depends(verify_bearer_token)]
)

api_router.include_router(
    positions.router,
    tags=["Positions"],
    dependencies=[Depends(verify_bearer_token)]
)

api_router.include_router(
    wallets.router,
    tags=["Wallet Registry"],
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

api_router.include_router(
    transactions.router,
    prefix="/transactions",
    tags=["Transactions"],
    dependencies=[Depends(verify_bearer_token)]
)

api_router.include_router(
    admin.router,
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(verify_bearer_token)]
)