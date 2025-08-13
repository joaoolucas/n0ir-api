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
    
    # Create async engine with connection pooling
    engine = create_async_engine(
        settings.get_database_url,
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