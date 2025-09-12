#!/usr/bin/env python3
"""Run a single migration directly."""

import os
import sys
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from alembic import command
from alembic.config import Config

async def run_migration(target_migration):
    """Run a specific migration."""
    try:
        # Get database URL
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            print("❌ No DATABASE_URL configured")
            return False
        
        # Setup alembic config
        alembic_cfg = Config("alembic.ini")
        
        # Run the specific migration
        print(f"🔄 Running migration: {target_migration}")
        command.upgrade(alembic_cfg, target_migration)
        print(f"✅ Migration {target_migration} completed")
        
        return True
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python run_single_migration.py <migration_name>")
        sys.exit(1)
    
    target = sys.argv[1]
    success = asyncio.run(run_migration(target))
    sys.exit(0 if success else 1)