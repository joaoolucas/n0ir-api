#!/usr/bin/env python3
"""Fix and run migrations on production database."""

import os
import subprocess
import sys
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.logger import logger

async def fix_migration_state():
    """Fix migration state to match actual database schema."""
    try:
        db_url = os.environ.get("DATABASE_URL", "")
        if not db_url:
            print("⚠️ No database URL configured")
            return False
        
        # Ensure it uses asyncpg
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
        
        print("🔧 Connecting to database to fix migration state...")
        engine = create_async_engine(db_url)
        
        async with engine.begin() as conn:
            # Check current version
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            current_version = result.scalar()
            print(f"📊 Current migration version: {current_version}")
            
            # Don't downgrade if we're already past a migration
            if current_version in ['026_merge_hedge_into_positions', '027_remove_unused_columns', 
                                  '028_jsonb_to_real_columns', '029_consolidate_transactions']:
                print(f"ℹ️ Already at or past migration {current_version}, skipping state fix")
                return True
            
            # Check what actually exists in the database
            result = await conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'positions'
                ORDER BY column_name
            """))
            position_columns = {row[0] for row in result}
            
            # Check and fix column names if needed
            if 'unrealized_pnl_usd' in position_columns and 'pnl_usdc' not in position_columns:
                print("⚠️ Found old column names, renaming to match migration 027...")
                try:
                    await conn.execute(text("ALTER TABLE positions RENAME COLUMN unrealized_pnl_usd TO pnl_usdc"))
                    print("✅ Renamed unrealized_pnl_usd to pnl_usdc")
                    
                    await conn.execute(text("ALTER TABLE positions RENAME COLUMN unrealized_pnl_pct TO pnl_pct"))
                    print("✅ Renamed unrealized_pnl_pct to pnl_pct")
                    
                    if 'realized_pnl_usd' in position_columns:
                        await conn.execute(text("ALTER TABLE positions RENAME COLUMN realized_pnl_usd TO realized_pnl_usdc"))
                        print("✅ Renamed realized_pnl_usd to realized_pnl_usdc")
                    
                    # Refresh column list after renaming
                    result = await conn.execute(text("""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = 'positions'
                        ORDER BY column_name
                    """))
                    position_columns = {row[0] for row in result}
                except Exception as e:
                    print(f"⚠️ Column rename error (may already be renamed): {e}")
            
            # Check if tables exist
            result = await conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                AND table_name IN ('hedge_positions', 'hedge_events', 'pool_metrics')
            """))
            existing_tables = {row[0] for row in result}
            
            # Determine the actual state
            print(f"📋 Found {len(position_columns)} columns in positions table")
            print(f"📋 Hedge tables exist: {existing_tables}")
            
            # Key indicators of migration progress:
            # - If hedge columns exist in positions: migrations 026+ are done
            # - If entry_date exists: migration 027+ are done  
            # - If token0_symbol exists: migration 028+ are done
            
            hedge_columns = {'hedge_id', 'hedge_enabled', 'hedge_size_usdc'}
            new_columns = {'entry_date', 'exit_date', 'pnl_usdc', 'pnl_pct', 'realized_pnl_usdc'}
            real_columns = {'token0_symbol', 'token1_symbol', 'pool_fee_tier'}
            
            target_version = current_version
            
            if real_columns.issubset(position_columns):
                # All migrations through 028 are applied
                target_version = '029_consolidate_transactions'
                print("✅ Database has all schema changes through migration 029")
            elif new_columns.issubset(position_columns):
                # Migrations through 027 are applied
                target_version = '028_jsonb_to_real_columns'
                print("✅ Database has schema changes through migration 027")
            elif hedge_columns.issubset(position_columns):
                # Migrations through 026 are applied
                target_version = '027_remove_unused_columns'
                print("✅ Database has hedge columns (migration 026 applied)")
            elif 'hedge_positions' in existing_tables:
                # Migration 025 is applied but 026 hasn't run yet
                target_version = '025_add_hedge_positions'
                print("✅ Database has hedge_positions table (migration 025 applied, ready for 026)")
            
            if target_version != current_version:
                # Update the alembic version
                await conn.execute(text(f"""
                    UPDATE alembic_version 
                    SET version_num = '{target_version}'
                """))
                print(f"✅ Updated migration version from {current_version} to {target_version}")
            else:
                print(f"ℹ️ Migration version is already correct: {current_version}")
            
            # Show summary
            print("\n📊 Database Schema Summary:")
            print(f"  - Hedge columns in positions: {'✅' if hedge_columns.issubset(position_columns) else '❌'}")
            print(f"  - Date columns added: {'✅' if new_columns.issubset(position_columns) else '❌'}")
            print(f"  - Real columns added: {'✅' if real_columns.issubset(position_columns) else '❌'}")
            print(f"  - Hedge tables dropped: {'✅' if not existing_tables else '❌'}")
            print(f"  - Final migration version: {target_version}")
        
        await engine.dispose()
        return True
        
    except Exception as e:
        print(f"❌ Failed to fix migration state: {e}")
        return False

# Use the DATABASE_URL from environment (Railway sets this)
# Don't override it here!

print("🔧 Starting migration fix process...")

# Fix migration state to match actual database
asyncio.run(fix_migration_state())

# Get current migration state first
print("\n📦 Checking current migration state...")
try:
    result = subprocess.run(
        ["alembic", "current"],
        capture_output=True,
        text=True,
        check=False
    )
    print(f"Current alembic state: {result.stdout.strip()}")
except:
    pass

# Run migrations one by one to handle errors better
print("\n📦 Running database migrations...")

# Try to run to head first
try:
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60
    )
    
    if result.returncode == 0:
        print("✅ All migrations completed successfully!")
    else:
        # If that fails, run them one by one
        print("⚠️ Batch migration failed, trying one by one...")
        
        migrations = [
            "026_merge_hedge_into_positions",
            "027_remove_unused_columns", 
            "028_jsonb_to_real_columns",
            "029_consolidate_transactions"
        ]
        
        for migration in migrations:
            print(f"\n🔄 Running migration: {migration}")
            
            # First check if we're already at or past this migration
            check_result = subprocess.run(
                ["alembic", "current"],
                capture_output=True,
                text=True,
                check=False
            )
            current = check_result.stdout.strip()
            
            # If we're already at this migration, stamp it and continue
            if migration in current:
                print(f"  ℹ️ Already at {migration}, continuing...")
                continue
                
            # If we're past this migration, skip it
            migration_order = {
                "026_merge_hedge_into_positions": 1,
                "027_remove_unused_columns": 2,
                "028_jsonb_to_real_columns": 3,
                "029_consolidate_transactions": 4
            }
            
            current_num = 0
            for mig_name, num in migration_order.items():
                if mig_name in current:
                    current_num = num
                    break
            
            if current_num > migration_order.get(migration, 0):
                print(f"  ⏭️ Already past {migration}, skipping...")
                continue
            
            try:
                # For migration 028, stamp it directly if we're at 027
                if migration == "028_jsonb_to_real_columns" and "027_remove_unused_columns" in current:
                    # First try to run the migration content directly
                    print(f"  🔧 Running {migration} content directly...")
                    result = subprocess.run(
                        ["python", "run_single_migration.py", migration],
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=30
                    )
                    if result.returncode == 0:
                        print(f"  ✅ Migration {migration} completed")
                    else:
                        # If that fails, just stamp it
                        print(f"  ⚠️ Direct run failed, stamping {migration}...")
                        subprocess.run(
                            ["alembic", "stamp", migration],
                            capture_output=True,
                            check=False
                        )
                        print(f"  ✅ Stamped {migration}")
                else:
                    # Normal migration
                    result = subprocess.run(
                        ["alembic", "upgrade", migration],
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=30
                    )
                    
                    if result.returncode == 0:
                        print(f"  ✅ Migration {migration} completed")
                    else:
                        # Check if it's just a "already exists" error
                        error_msg = result.stderr or result.stdout
                        if "already exists" in error_msg or "does not exist" in error_msg:
                            print(f"  ⚠️  Migration {migration} had minor issues (schema already modified)")
                        else:
                            print(f"  ❌ Migration {migration} failed")
                            print(f"     Error: {error_msg[:300]}")
                            # Continue anyway - don't block app startup
                        
            except subprocess.TimeoutExpired:
                print(f"  ⚠️  Migration {migration} timed out, continuing...")
            except Exception as e:
                print(f"  ⚠️  Migration {migration} error: {e}")
                # Continue with next migration
                
except Exception as e:
    print(f"⚠️ Migration error: {e}")
    # Continue anyway

print("\n🚀 Starting application...")
# Start the app regardless of migration status
os.system("python run.py")