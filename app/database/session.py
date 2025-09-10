from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from app.core.config import settings
from app.core.logger import logger

# Create async engine
engine = None
async_session_maker = None

def init_db():
    """Initialize database connection."""
    global engine, async_session_maker
    
    if not settings.get_database_url:
        logger.warning("No database URL configured. Database features will be disabled.")
        return
    
    # Get database URL and ensure it uses asyncpg
    db_url = settings.get_database_url
    logger.info(f"Using database URL: {db_url[:30]}... (private_url: {settings.database_private_url is not None}, database_url: {settings.database_url is not None})")
    
    # Convert postgresql:// or postgres:// to postgresql+asyncpg://
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif "postgresql+" in db_url and not db_url.startswith("postgresql+asyncpg://"):
        # If it's using a different driver, replace it
        parts = db_url.split("://", 1)
        if len(parts) == 2:
            db_url = f"postgresql+asyncpg://{parts[1]}"
    
    # Create async engine with connection pooling
    engine = create_async_engine(
        db_url,
        echo=settings.database_echo,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_pool_overflow,
        pool_pre_ping=True,  # Verify connections before using
        poolclass=None if settings.database_pool_size > 0 else NullPool
    )
    
    # Create session factory
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False
    )
    
    logger.info("Database connection initialized successfully")

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency to get database session.
    Usage:
        @app.get("/")
        async def root(db: AsyncSession = Depends(get_db)):
            ...
    """
    if not async_session_maker:
        init_db()
        if not async_session_maker:
            raise RuntimeError("Database is not configured")
    
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def close_db():
    """Close database connection."""
    global engine
    if engine:
        await engine.dispose()
        logger.info("Database connection closed")