from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from app.core.config import settings
from app.api.v1.api import api_router
from app.core.logger import logger
from app.services.agent_management_service import get_agent_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager to handle startup and shutdown."""
    
    # Startup
    logger.info("Starting API with agent management service listener...")
    try:
        # Get the singleton instance
        agent_service = get_agent_service()
        if agent_service.redis_client:
            await agent_service.start_listener()
            logger.info("Agent management service listener started successfully")
        else:
            logger.warning("Agent management service running without Redis")
    except Exception as e:
        logger.error(f"Failed to start agent management service listener: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down agent management service listener...")
    # Cleanup if needed

# Create FastAPI application
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description="API for accessing Aerodrome Finance Concentrated Liquidity pool data on Base network",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
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
    
    # Agent management service is now initialized in lifespan handler
    agent_service = get_agent_service()
    if agent_service and agent_service.redis_client:
        logger.info("🤖 Agent management service already initialized via lifespan")
    else:
        logger.warning("⚠️  Agent management service not initialized - check lifespan handler")
    
    # Don't create a new instance here - it's handled in lifespan
    try:
        pass  # Keep try block for consistency
    except Exception as e:
        logger.warning(f"⚠️  Could not initialize agent management service: {e}")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    logger.info(f"👋 {settings.api_title} shutting down...")
    
    # Close database connection
    from app.database.session import close_db
    await close_db()