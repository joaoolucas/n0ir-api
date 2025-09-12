#!/usr/bin/env python3
"""Fix and run migrations on production database."""

import os
import subprocess
import sys
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def mark_025_complete():
    """Mark migration 025 as complete if tables exist."""
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
            # Check if hedge_positions table exists
            result = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'hedge_positions'
                )
            """))
            table_exists = result.scalar()
            
            if table_exists:
                # Check current version
                result = await conn.execute(text("SELECT version_num FROM alembic_version"))
                current_version = result.scalar()
                
                if current_version == "024_relax_position_fields":
                    # Update to 025 since tables already exist
                    await conn.execute(text("""
                        UPDATE alembic_version 
                        SET version_num = '025_add_hedge_positions'
                        WHERE version_num = '024_relax_position_fields'
                    """))
                    print("✅ Marked migration 025 as complete (tables already exist)")
        
        await engine.dispose()
    except Exception as e:
        print(f"⚠️ Could not mark migration: {e}")

# Use the DATABASE_URL from environment (Railway sets this)
# Don't override it here!

print("🔧 Starting migration fix process...")

# Mark migration 025 as complete if tables exist
asyncio.run(mark_025_complete())

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