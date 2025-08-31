#!/usr/bin/env python3
"""Reset production database - drops all tables and recreates schema."""

import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import asyncpg

# Production database URL
DATABASE_URL = "postgresql://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway"

# Convert to asyncpg URL
ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

async def reset_database():
    """Drop all tables and reset the database."""
    print("🔄 Connecting to production database...")
    
    # Create engine
    engine = create_async_engine(ASYNC_DATABASE_URL, echo=True)
    
    async with engine.begin() as conn:
        print("\n⚠️  WARNING: This will DELETE ALL DATA in the production database!")
        print(f"Database: {DATABASE_URL}")
        
        # Get confirmation
        confirm = input("\nType 'RESET PRODUCTION' to confirm: ")
        if confirm != "RESET PRODUCTION":
            print("❌ Reset cancelled")
            return
        
        print("\n🗑️  Dropping all tables...")
        
        # Drop all tables in the public schema
        await conn.execute(text("""
            DO $$ 
            DECLARE 
                r RECORD;
            BEGIN
                -- Disable foreign key checks
                SET session_replication_role = 'replica';
                
                -- Drop all tables
                FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') 
                LOOP
                    EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
                END LOOP;
                
                -- Drop all custom types
                FOR r IN (SELECT typname FROM pg_type WHERE typtype = 'e' AND typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public'))
                LOOP
                    EXECUTE 'DROP TYPE IF EXISTS ' || quote_ident(r.typname) || ' CASCADE';
                END LOOP;
                
                -- Re-enable foreign key checks
                SET session_replication_role = 'origin';
            END $$;
        """))
        
        print("✅ All tables dropped")
        
        # Drop alembic version table specifically
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version CASCADE"))
        print("✅ Alembic version table dropped")
        
        # Verify tables are gone
        result = await conn.execute(text("""
            SELECT COUNT(*) as table_count 
            FROM pg_tables 
            WHERE schemaname = 'public'
        """))
        count = result.scalar()
        
        if count == 0:
            print(f"\n✅ Database reset complete! All tables removed.")
            print("\n📝 Next steps:")
            print("1. Run: alembic upgrade head")
            print("2. Or redeploy the service to run migrations automatically")
        else:
            print(f"\n⚠️  Warning: {count} tables still remain in the database")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(reset_database())