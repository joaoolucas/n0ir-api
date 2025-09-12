#!/usr/bin/env python3
"""Fix migration state to match actual database schema."""

import os
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.config import settings
from app.core.logger import logger

async def fix_migration_state():
    """Update alembic version to match actual database state."""
    try:
        # Get database URL
        db_url = os.environ.get("DATABASE_URL") or settings.get_database_url
        if not db_url:
            logger.error("No database URL configured")
            return False
        
        # Ensure it uses asyncpg
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
        
        logger.info("Connecting to database...")
        engine = create_async_engine(db_url)
        
        async with engine.begin() as conn:
            # Check current version
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            current_version = result.scalar()
            logger.info(f"Current migration version: {current_version}")
            
            # Check what actually exists in the database
            result = await conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'positions'
                ORDER BY column_name
            """))
            position_columns = {row[0] for row in result}
            
            # Check if tables exist
            result = await conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                AND table_name IN ('hedge_positions', 'hedge_events', 'pool_metrics')
            """))
            existing_tables = {row[0] for row in result}
            
            # Determine the actual state
            logger.info(f"Found {len(position_columns)} columns in positions table")
            logger.info(f"Hedge tables exist: {existing_tables}")
            
            # Key indicators of migration progress:
            # - If hedge columns exist in positions: migrations 026+ are done
            # - If entry_date exists: migration 027+ are done  
            # - If token0_symbol exists: migration 028+ are done
            
            hedge_columns = {'hedge_id', 'hedge_enabled', 'hedge_size_usdc'}
            new_columns = {'entry_date', 'exit_date', 'realized_pnl_usdc'}
            real_columns = {'token0_symbol', 'token1_symbol', 'pool_fee_tier'}
            
            target_version = current_version
            
            if real_columns.issubset(position_columns):
                # All migrations through 028 are applied
                target_version = '029_consolidate_transactions'
                logger.info("✅ Database has all schema changes through migration 029")
            elif new_columns.issubset(position_columns):
                # Migrations through 027 are applied
                target_version = '028_jsonb_to_real_columns'
                logger.info("✅ Database has schema changes through migration 027")
            elif hedge_columns.issubset(position_columns):
                # Migrations through 026 are applied
                target_version = '027_remove_unused_columns'
                logger.info("✅ Database has hedge columns (migration 026 applied)")
            elif 'hedge_positions' in existing_tables:
                # Migration 025 is applied
                target_version = '026_merge_hedge_into_positions'
                logger.info("✅ Database has hedge_positions table (migration 025 applied)")
            
            if target_version != current_version:
                # Update the alembic version
                await conn.execute(text(f"""
                    UPDATE alembic_version 
                    SET version_num = '{target_version}'
                """))
                logger.info(f"✅ Updated migration version from {current_version} to {target_version}")
            else:
                logger.info(f"ℹ️ Migration version is already correct: {current_version}")
            
            # Show summary
            logger.info("\n📊 Database Schema Summary:")
            logger.info(f"  - Hedge columns in positions: {'✅' if hedge_columns.issubset(position_columns) else '❌'}")
            logger.info(f"  - Date columns added: {'✅' if new_columns.issubset(position_columns) else '❌'}")
            logger.info(f"  - Real columns added: {'✅' if real_columns.issubset(position_columns) else '❌'}")
            logger.info(f"  - Hedge tables dropped: {'✅' if not existing_tables else '❌'}")
            logger.info(f"  - Final migration version: {target_version}")
        
        await engine.dispose()
        return True
        
    except Exception as e:
        logger.error(f"Failed to fix migration state: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(fix_migration_state())
    exit(0 if success else 1)