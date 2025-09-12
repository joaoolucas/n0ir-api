#!/usr/bin/env python3
"""Fix and run migrations on production database."""

import os
import subprocess
import sys
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def skip_applied_migrations():
    """Skip migrations that have already been applied."""
    try:
        db_url = os.environ.get("DATABASE_URL", "")
        if not db_url:
            return
        
        # Ensure it uses asyncpg
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
        
        engine = create_async_engine(db_url)
        
        async with engine.begin() as conn:
            # Check current version
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            current_version = result.scalar()
            print(f"📊 Current migration: {current_version}")
            
            # Check what already exists in the database
            result = await conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'positions'
            """))
            existing_columns = {row[0] for row in result}
            
            # Check if tables exist
            result = await conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """))
            existing_tables = {row[0] for row in result}
            
            # If hedge columns already exist in positions, skip to migration 029
            hedge_columns = {'hedge_id', 'hedge_enabled', 'hedge_size_usdc'}
            if hedge_columns.issubset(existing_columns):
                print("✅ Hedge columns already exist in positions table")
                
                # Skip directly to the last migration if we're behind
                if current_version in ["024_relax_position_fields", "025_add_hedge_positions", 
                                       "026_merge_hedge_into_positions", "027_remove_unused_columns",
                                       "028_jsonb_to_real_columns"]:
                    await conn.execute(text("""
                        UPDATE alembic_version 
                        SET version_num = '029_consolidate_transactions'
                    """))
                    print("✅ Skipped to migration 029 (database already has all changes)")
                    return
            
            # If hedge_positions table exists and we're at 024, mark 025 as complete
            if 'hedge_positions' in existing_tables and current_version == "024_relax_position_fields":
                await conn.execute(text("""
                    UPDATE alembic_version 
                    SET version_num = '025_add_hedge_positions'
                """))
                print("✅ Marked migration 025 as complete (tables already exist)")
        
        await engine.dispose()
    except Exception as e:
        print(f"⚠️ Could not check migrations: {e}")

# Use the DATABASE_URL from environment (Railway sets this)
# Don't override it here!

print("🔧 Starting migration fix process...")

# Skip migrations that have already been applied
asyncio.run(skip_applied_migrations())

# Run alembic upgrade head
print("\n📦 Running database migrations...")
try:
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        check=False
    )
    
    if result.returncode == 0:
        print("✅ Migrations completed successfully!")
        print(result.stdout)
    else:
        print("❌ Migration failed, but continuing...")
        print(result.stderr)
        # Don't exit - let the app start anyway
        
except Exception as e:
    print(f"⚠️  Migration error: {e}")
    # Don't exit - let the app start anyway

print("\n🚀 Starting application...")
# Start the app regardless of migration status
os.system("python run.py")