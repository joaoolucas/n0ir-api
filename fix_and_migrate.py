#!/usr/bin/env python3
"""Fix migration version names and run migrations"""

import asyncio
import os
import sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
import subprocess

async def fix_migration_version():
    """Fix the alembic version table to use shorter version names"""
    
    # Get database URL from environment
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set")
        return False
    
    # Convert to asyncpg URL if needed
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    print(f"Connecting to database...")
    
    try:
        # Create engine
        engine = create_async_engine(db_url)
        
        async with engine.begin() as conn:
            # Check if alembic_version table exists
            result = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'alembic_version'
                )
            """))
            table_exists = result.scalar()
            
            if not table_exists:
                print("alembic_version table doesn't exist yet, migrations will create it")
                await engine.dispose()
                return True
            
            # Check current version
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            current = result.scalar()
            print(f"Current version in database: {current}")
            
            # Update to shorter name if needed
            if current == "005_add_pool_name_to_positions":
                await conn.execute(text("UPDATE alembic_version SET version_num = '005_add_pool_name_to_pos'"))
                print("Updated version to: 005_add_pool_name_to_pos")
            elif current == "004_add_user_pnl_fields":
                print("Database is at version 004, migration 005 will be applied")
            else:
                print(f"Database version is: {current}")
        
        await engine.dispose()
        return True
        
    except Exception as e:
        print(f"Error fixing migration: {e}")
        return False

async def fix_missing_columns():
    """Add all missing columns to users table"""
    
    # Get database URL from environment
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set")
        return False
    
    # Convert to asyncpg URL if needed
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    try:
        # Create engine
        engine = create_async_engine(db_url)
        
        async with engine.begin() as conn:
            # List of columns to check and add if missing
            columns_to_add = [
                ("has_deposited_50_usdc", "BOOLEAN NOT NULL DEFAULT FALSE"),
                ("agent_started_at", "TIMESTAMP WITH TIME ZONE"),
                ("agent_stopped_at", "TIMESTAMP WITH TIME ZONE"),
                ("last_balance_check", "TIMESTAMP WITH TIME ZONE"),
                ("agent_metadata", "JSONB"),
                ("created_at", "TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP"),
                ("updated_at", "TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP")
            ]
            
            for column_name, column_type in columns_to_add:
                # Check if column exists
                result = await conn.execute(text(f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_name = 'users' 
                        AND column_name = '{column_name}'
                    )
                """))
                column_exists = result.scalar()
                
                if column_exists:
                    print(f"✅ Column {column_name} already exists")
                else:
                    print(f"Adding {column_name} column...")
                    
                    # Add the column
                    await conn.execute(text(f"""
                        ALTER TABLE users 
                        ADD COLUMN {column_name} {column_type}
                    """))
                    
                    print(f"✅ Successfully added {column_name} column")
            
            # Special handling for has_deposited_50_usdc - update based on net deposits
            print("Updating has_deposited_50_usdc based on net deposits...")
            await conn.execute(text("""
                UPDATE users 
                SET has_deposited_50_usdc = TRUE 
                WHERE (total_deposits_usdc - total_withdrawals_usdc) >= 50
            """))
            
            print("✅ All missing columns have been added")
        
        await engine.dispose()
        return True
        
    except Exception as e:
        print(f"❌ Error adding columns: {e}")
        return False

async def main():
    """Main function to fix and run migrations"""
    
    print("=== Fixing migration version names ===")
    success = await fix_migration_version()
    
    if not success:
        print("Failed to fix migration versions")
        sys.exit(1)
    
    print("\n=== Fixing missing columns in users table ===")
    success = await fix_missing_columns()
    
    if not success:
        print("Failed to fix missing columns")
        # Don't exit, continue with migrations
    
    print("\n=== Running Alembic migrations ===")
    # Run alembic upgrade
    result = subprocess.run(["alembic", "upgrade", "head"], capture_output=True, text=True)
    
    if result.returncode == 0:
        print("✅ Migrations completed successfully!")
        print(result.stdout)
    else:
        print("❌ Migration failed!")
        print(result.stderr)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())