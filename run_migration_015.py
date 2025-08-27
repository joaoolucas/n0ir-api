#!/usr/bin/env python3
"""Run migration 015 manually on staging database."""

import asyncio
import asyncpg
from urllib.parse import urlparse

# Database URL from Railway staging
DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"


async def run_migration():
    """Run migration 015 for wallet balance tracking."""
    
    # Parse database URL
    parsed = urlparse(DATABASE_URL)
    
    # Connect to database
    conn = await asyncpg.connect(
        host=parsed.hostname,
        port=parsed.port,
        user=parsed.username,
        password=parsed.password,
        database=parsed.path.lstrip('/'),
        ssl='require'
    )
    
    print("Connected to staging database")
    
    try:
        print("\nRunning migration 015: Add wallet balance tracking fields...")
        
        await conn.execute("""
            DO $$
            BEGIN
                -- Add USDC balance field
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name = 'users' AND column_name = 'usdc_balance') THEN
                    ALTER TABLE users ADD COLUMN usdc_balance NUMERIC(20,6) DEFAULT 0 NOT NULL;
                    RAISE NOTICE 'Added column: usdc_balance';
                END IF;
                
                -- Add last deposit block
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name = 'users' AND column_name = 'last_deposit_block') THEN
                    ALTER TABLE users ADD COLUMN last_deposit_block INTEGER;
                    RAISE NOTICE 'Added column: last_deposit_block';
                END IF;
                
                -- Add last withdrawal block
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name = 'users' AND column_name = 'last_withdrawal_block') THEN
                    ALTER TABLE users ADD COLUMN last_withdrawal_block INTEGER;
                    RAISE NOTICE 'Added column: last_withdrawal_block';
                END IF;
                
                -- Add total deposits tracking
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name = 'users' AND column_name = 'total_deposits_usdc') THEN
                    ALTER TABLE users ADD COLUMN total_deposits_usdc NUMERIC(20,6) DEFAULT 0 NOT NULL;
                    RAISE NOTICE 'Added column: total_deposits_usdc';
                END IF;
                
                -- Add total withdrawals tracking
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name = 'users' AND column_name = 'total_withdrawals_usdc') THEN
                    ALTER TABLE users ADD COLUMN total_withdrawals_usdc NUMERIC(20,6) DEFAULT 0 NOT NULL;
                    RAISE NOTICE 'Added column: total_withdrawals_usdc';
                END IF;
                
                -- Add last scanned block for wallet monitoring
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name = 'users' AND column_name = 'last_scanned_block') THEN
                    ALTER TABLE users ADD COLUMN last_scanned_block INTEGER;
                    RAISE NOTICE 'Added column: last_scanned_block';
                END IF;
            END $$;
        """)
        
        print("✅ Migration 015 completed successfully")
        
        # Update alembic version
        await conn.execute("""
            UPDATE alembic_version 
            SET version_num = '015_add_wallet_balance_tracking'
            WHERE version_num = '013_fix_transaction_primary_key'
        """)
        
        print("✅ Updated alembic version to 015")
        
        # Verify the schema
        columns = await conn.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'users' 
            AND column_name IN (
                'usdc_balance', 'last_deposit_block', 'last_withdrawal_block',
                'total_deposits_usdc', 'total_withdrawals_usdc', 'last_scanned_block'
            )
            ORDER BY column_name
        """)
        
        print("\nNew columns in users table:")
        for col in columns:
            print(f"  ✓ {col['column_name']}: {col['data_type']}")
        
    except Exception as e:
        print(f"\n❌ Error during migration: {e}")
        raise
    finally:
        await conn.close()
        print("\nDisconnected from database")


if __name__ == "__main__":
    print("🚀 Running migration 015 on Railway staging database")
    asyncio.run(run_migration())
    print("✨ Migration completed!")