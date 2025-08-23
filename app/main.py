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
    
    # First, ensure schema compatibility
    from app.database.session import get_db
    from app.database.schema_fixes import ensure_schema_compatibility
    
    logger.info("Ensuring database schema compatibility...")
    async for db in get_db():
        await ensure_schema_compatibility(db)
        break  # Exit after first iteration
    
    try:
        # Get the singleton instance
        agent_service = get_agent_service()
        if agent_service.redis_client:
            await agent_service.start_listener()
            logger.info("Agent management service listener started successfully")
            
            # Publish balance events for existing users with balance > 0
            # This ensures agents start for users who already have sufficient balance
            logger.info("Publishing initial balance events for existing users...")
            from app.services.user_service import UserService
            
            async for db in get_db():
                user_service = UserService(db)
                users = await user_service.list_all_users()
                
                for user in users:
                    try:
                        # Get user's current balance
                        balance = await user_service.get_user_balance(user.user_id)
                        
                        if balance and balance > 0:
                            # Publish balance event to trigger agent startup if balance >= 10
                            await agent_service.publish_balance_event(
                                user_id=user.user_id,
                                balance=float(balance),
                                event_type='startup_check'
                            )
                            logger.info(f"Published startup balance event for {user.user_id}: {balance} USDC")
                    except Exception as e:
                        logger.error(f"Error publishing balance event for {user.user_id}: {e}")
                
                logger.info("Initial balance events published")
                break  # Exit the async generator after first iteration
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