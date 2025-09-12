#!/usr/bin/env python3
"""Check and fix database schema issues."""

import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv

load_dotenv()

async def check_and_fix_schema():
    """Check and fix the database schema."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL not set")
        return False
    
    # Convert to async URL
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
    
    engine = create_async_engine(database_url, echo=False)
    
    async with engine.begin() as conn:
        # Check current alembic version
        result = await conn.execute(text("SELECT version_num FROM alembic_version"))
        current_version = result.scalar()
        print(f"📍 Current alembic version: {current_version}")
        
        # Check if columns exist
        result = await conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'positions'
            ORDER BY ordinal_position;
        """))
        columns = [row[0] for row in result]
        print(f"📋 Position columns: {', '.join(columns)}")
        
        # Check for old vs new column names
        has_old_columns = 'unrealized_pnl_usd' in columns
        has_new_columns = 'pnl_usdc' in columns
        
        print(f"🔍 Has old columns (unrealized_pnl_usd): {has_old_columns}")
        print(f"🔍 Has new columns (pnl_usdc): {has_new_columns}")
        
        if has_old_columns and not has_new_columns:
            print("⚠️ Database has old column names, migration 027 didn't run properly")
            print("🔧 Applying column renames manually...")
            
            try:
                # Rename the PnL columns
                await conn.execute(text("ALTER TABLE positions RENAME COLUMN unrealized_pnl_usd TO pnl_usdc"))
                print("✅ Renamed unrealized_pnl_usd to pnl_usdc")
                
                await conn.execute(text("ALTER TABLE positions RENAME COLUMN unrealized_pnl_pct TO pnl_pct"))
                print("✅ Renamed unrealized_pnl_pct to pnl_pct")
                
                # realized_pnl_usd should become realized_pnl_usdc
                if 'realized_pnl_usd' in columns:
                    await conn.execute(text("ALTER TABLE positions RENAME COLUMN realized_pnl_usd TO realized_pnl_usdc"))
                    print("✅ Renamed realized_pnl_usd to realized_pnl_usdc")
                
                # Update alembic version to 027 if needed
                if current_version == '026_merge_hedge_into_positions':
                    await conn.execute(text("UPDATE alembic_version SET version_num = '027_remove_unused_columns'"))
                    print("✅ Updated alembic version to 027")
                
                print("✅ Schema fixed successfully!")
                return True
                
            except Exception as e:
                print(f"❌ Error fixing schema: {e}")
                return False
        
        elif not has_old_columns and has_new_columns:
            print("✅ Database already has new column names")
            return True
        
        elif has_old_columns and has_new_columns:
            print("⚠️ Database has both old and new columns - unexpected state")
            return False
        
        else:
            print("❌ Database missing both old and new columns - critical error")
            return False
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_and_fix_schema())