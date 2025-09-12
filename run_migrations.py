#!/usr/bin/env python3
"""Run database migrations."""

import os
import sys
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from app.core.config import settings
from app.core.logger import logger

def run_migrations():
    """Run all pending migrations."""
    try:
        # Get database URL
        db_url = settings.get_database_url
        if not db_url:
            logger.error("No database URL configured")
            return False
        
        # Convert to sync URL for migrations
        if db_url.startswith("postgresql+asyncpg://"):
            db_url = db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        elif db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        
        logger.info(f"Connecting to database...")
        
        # Create engine
        engine = create_engine(db_url)
        
        # First, check if we need to clean up old tables
        with engine.connect() as conn:
            # Check if hedge_positions table exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'hedge_positions'
                )
            """))
            hedge_table_exists = result.scalar()
            
            if hedge_table_exists:
                logger.info("Found existing hedge_positions table, dropping it...")
                conn.execute(text("DROP TABLE IF EXISTS hedge_events CASCADE"))
                conn.execute(text("DROP TABLE IF EXISTS hedge_positions CASCADE"))
                conn.commit()
                logger.info("Dropped old hedge tables")
            
            # Check if pool_metrics exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'pool_metrics'
                )
            """))
            if result.scalar():
                conn.execute(text("DROP TABLE IF EXISTS pool_metrics CASCADE"))
                conn.commit()
                logger.info("Dropped pool_metrics table")
        
        # Run Alembic migrations
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        
        logger.info("Running database migrations...")
        command.upgrade(alembic_cfg, "head")
        logger.info("Migrations completed successfully!")
        
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False

if __name__ == "__main__":
    success = run_migrations()
    sys.exit(0 if success else 1)