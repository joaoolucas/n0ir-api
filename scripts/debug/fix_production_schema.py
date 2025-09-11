#!/usr/bin/env python3
"""Script to fix missing schema elements in production database."""

import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def fix_production_schema():
    """Fix missing schema elements in production database."""
    
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("DATABASE_URL not found in environment")
        return
    
    # Convert to async URL
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    
    # Create engine
    engine = create_async_engine(database_url)
    
    async with AsyncSession(engine) as session:
        try:
            # Check current alembic version
            result = await session.execute(text("SELECT version_num FROM alembic_version"))
            current_version = result.scalar_one_or_none()
            print(f"Current alembic version: {current_version}")
            
            # 1. Check and create AgentStatus enum if it doesn't exist
            result = await session.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_type WHERE typname = 'agentstatus'
                )
            """))
            has_agent_status = result.scalar()
            
            if not has_agent_status:
                print("Creating AgentStatus enum...")
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
                print("✅ Created AgentStatus enum")
            else:
                print("AgentStatus enum already exists")
            
            # 2. Check and add agent_status columns to users table if they don't exist
            result = await session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                AND column_name = 'agent_status'
            """))
            has_agent_status_col = result.fetchone() is not None
            
            if not has_agent_status_col:
                print("Adding agent_status columns to users table...")
                await session.execute(text("""
                    ALTER TABLE users
                    ADD COLUMN agent_status agentstatus DEFAULT 'not_started',
                    ADD COLUMN agent_started_at TIMESTAMP WITH TIME ZONE,
                    ADD COLUMN agent_stopped_at TIMESTAMP WITH TIME ZONE,
                    ADD COLUMN last_balance_check TIMESTAMP WITH TIME ZONE
                """))
                print("✅ Added agent_status columns to users table")
            else:
                print("agent_status columns already exist in users table")
            
            # 3. Check and add related_position_id to transactions table if it doesn't exist
            result = await session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'transactions' 
                AND column_name = 'related_position_id'
            """))
            has_related_position = result.fetchone() is not None
            
            if not has_related_position:
                print("Adding related_position_id to transactions table...")
                await session.execute(text("""
                    ALTER TABLE transactions
                    ADD COLUMN related_position_id BIGINT
                """))
                
                # Check if positions table has nft_token_id as primary key
                result = await session.execute(text("""
                    SELECT column_name 
                    FROM information_schema.key_column_usage 
                    WHERE table_name = 'positions' 
                    AND constraint_name IN (
                        SELECT constraint_name 
                        FROM information_schema.table_constraints 
                        WHERE table_name = 'positions' 
                        AND constraint_type = 'PRIMARY KEY'
                    )
                """))
                pk_column = result.fetchone()
                
                if pk_column and pk_column[0] == 'nft_token_id':
                    # Add foreign key constraint if positions uses nft_token_id as PK
                    try:
                        await session.execute(text("""
                            ALTER TABLE transactions
                            ADD CONSTRAINT fk_transaction_position
                            FOREIGN KEY (related_position_id) 
                            REFERENCES positions(nft_token_id)
                        """))
                        print("✅ Added foreign key constraint for related_position_id")
                    except:
                        print("Could not add foreign key constraint (might already exist)")
                
                print("✅ Added related_position_id to transactions table")
            else:
                print("related_position_id already exists in transactions table")
            
            # 4. Check and create agent_events table if it doesn't exist
            result = await session.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name = 'agent_events'
            """))
            has_agent_events = result.fetchone() is not None
            
            if not has_agent_events:
                print("Creating agent_events table...")
                await session.execute(text("""
                    CREATE TABLE agent_events (
                        event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id VARCHAR NOT NULL,
                        event_type VARCHAR NOT NULL,
                        event_metadata JSONB,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                    )
                """))
                
                # Create index on user_id and created_at
                await session.execute(text("""
                    CREATE INDEX idx_agent_events_user_created 
                    ON agent_events(user_id, created_at DESC)
                """))
                
                print("✅ Created agent_events table")
            else:
                print("agent_events table already exists")
            
            # 5. Update alembic version if needed
            if current_version in ['30ff38b3b56d', 'd8de59893c30', '003_fix_position_primary_key']:
                print(f"Updating alembic version from {current_version} to 008_add_agent_state_tracking...")
                await session.execute(text("""
                    UPDATE alembic_version 
                    SET version_num = '008_add_agent_state_tracking'
                """))
                print("✅ Updated alembic version")
            
            # Commit all changes
            await session.commit()
            print("\n✅ All schema fixes applied successfully!")
            
        except Exception as e:
            print(f"Error fixing schema: {e}")
            await session.rollback()
            raise
        finally:
            await engine.dispose()

if __name__ == "__main__":
    asyncio.run(fix_production_schema())