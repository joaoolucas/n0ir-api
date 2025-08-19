from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.api.v1.api import api_router
from app.core.logger import logger

# Create FastAPI application
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description="API for accessing Aerodrome Finance Concentrated Liquidity pool data on Base network",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

# Add custom exception handler for better error formatting
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc!r}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "details": {"error": str(exc)}
            }
        }
    )

# Include API router
app.include_router(api_router, prefix=settings.api_prefix)

# Root endpoint
@app.get("/")
async def root():
    return {
        "name": settings.api_title,
        "version": settings.api_version,
        "docs": "/docs",
        "api": settings.api_prefix
    }

# Startup event
@app.on_event("startup")
async def startup_event():
    logger.info(f"🚀 {settings.api_title} v{settings.api_version} starting up...")
    logger.info(f"📍 API available at {settings.api_prefix}")
    logger.info(f"📚 Documentation available at /docs")
    logger.info(f"🔗 Connected to RPC: {settings.rpc_url[:30]}...")
    logger.info(f"📁 Logging to: {settings.log_dir}/" if settings.enable_file_logging else "📝 File logging disabled")
    
    # Initialize database connection
    from app.database.session import init_db
    init_db()
    
    if settings.get_database_url:
        logger.info("🗄️  Database connection initialized")
    else:
        logger.warning("⚠️  No database configured - user management features disabled")
    
    # Initialize agent management service listener
    try:
        from app.services.agent_management_service import AgentManagementService
        agent_service = AgentManagementService()
        await agent_service.start_listener()
        logger.info("🤖 Agent management service initialized")
    except Exception as e:
        logger.warning(f"⚠️  Could not initialize agent management service: {e}")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    logger.info(f"👋 {settings.api_title} shutting down...")
    
    # Close database connection
    from app.database.session import close_db
    await close_db()