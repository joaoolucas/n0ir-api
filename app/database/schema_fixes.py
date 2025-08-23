"""Schema fixes for production database issues."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logger import logger


async def ensure_schema_compatibility(session: AsyncSession):
    """Ensure all required schema elements exist in the database."""
    
    try:
        # 1. Check and create AgentStatus enum if it doesn't exist
        result = await session.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'agentstatus'
            )
        """))
        has_agent_status = result.scalar()
        
        if not has_agent_status:
            logger.info("Creating AgentStatus enum...")
            await session.execute(text("""
                CREATE TYPE agentstatus AS ENUM (
                    'not_started',
                    'starting',
                    'running',
                    'stopping',
                    'stopped',
                    'error'
                )
            """))
            await session.commit()
            logger.info("Created AgentStatus enum")
        
        # 2. Check and add agent_status columns to users table if they don't exist
        result = await session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'users' 
            AND column_name = 'agent_status'
        """))
        has_agent_status_col = result.fetchone() is not None
        
        if not has_agent_status_col:
            logger.info("Adding agent_status columns to users table...")
            await session.execute(text("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS agent_status agentstatus DEFAULT 'not_started',
                ADD COLUMN IF NOT EXISTS agent_started_at TIMESTAMP WITH TIME ZONE,
                ADD COLUMN IF NOT EXISTS agent_stopped_at TIMESTAMP WITH TIME ZONE,
                ADD COLUMN IF NOT EXISTS last_balance_check TIMESTAMP WITH TIME ZONE
            """))
            await session.commit()
            logger.info("Added agent_status columns to users table")
        
        # 3. Check and add related_position_id to transactions table if it doesn't exist
        result = await session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'transactions' 
            AND column_name = 'related_position_id'
        """))
        has_related_position = result.fetchone() is not None
        
        if not has_related_position:
            logger.info("Adding related_position_id to transactions table...")
            await session.execute(text("""
                ALTER TABLE transactions
                ADD COLUMN IF NOT EXISTS related_position_id BIGINT
            """))
            await session.commit()
            logger.info("Added related_position_id to transactions table")
        
        # 4. Check and create agent_events table if it doesn't exist
        result = await session.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = 'agent_events'
        """))
        has_agent_events = result.fetchone() is not None
        
        if not has_agent_events:
            logger.info("Creating agent_events table...")
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS agent_events (
                    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id VARCHAR NOT NULL,
                    event_type VARCHAR NOT NULL,
                    event_metadata JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))
            
            # Try to add foreign key, but don't fail if it exists
            try:
                await session.execute(text("""
                    ALTER TABLE agent_events
                    ADD CONSTRAINT fk_agent_events_user
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                """))
            except:
                pass
            
            # Create index
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_agent_events_user_created 
                ON agent_events(user_id, created_at DESC)
            """))
            await session.commit()
            logger.info("Created agent_events table")
        
        logger.info("Schema compatibility check completed")
        
    except Exception as e:
        logger.error(f"Error ensuring schema compatibility: {e}")
        # Don't fail the application startup, just log the error
        pass