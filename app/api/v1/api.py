from fastapi import APIRouter
from app.api.v1.endpoints import pools, tokens, health, positions, wallets, strategy, users, transactions, agents, debug, admin

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

api_router.include_router(
    positions.router,
    tags=["Positions"]
)

api_router.include_router(
    wallets.router,
    tags=["Wallet Registry"]
)

api_router.include_router(
    strategy.router,
    tags=["Strategy"]
)

api_router.include_router(
    users.router,
    tags=["Users"]
)

api_router.include_router(
    transactions.router,
    prefix="/transactions",
    tags=["Transactions"]
)

api_router.include_router(
    agents.router
    # Tags already defined in agents.router
)

# Debug endpoints (only in development)
api_router.include_router(
    debug.router,
    tags=["Debug"]
)

# Admin endpoints (temporary for migrations)
api_router.include_router(
    admin.router,
    prefix="/admin",
    tags=["Admin"]
)