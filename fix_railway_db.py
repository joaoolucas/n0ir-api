import asyncio
import asyncpg

async def fix_railway_db():
    conn = await asyncpg.connect(
        "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"
    )
    
    print("Connected to Railway database")
    
    # First check alembic version
    version = await conn.fetchval("SELECT version_num FROM alembic_version")
    print(f"Current alembic version: {version}")
    
    # Add missing columns to positions table
    print("\nAdding missing columns to positions table...")
    
    await conn.execute("""
        DO $$
        BEGIN
            -- Add created_at if missing
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'created_at') THEN
                ALTER TABLE positions ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL;
                RAISE NOTICE 'Added created_at column';
            END IF;
            
            -- Add updated_at if missing  
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'updated_at') THEN
                ALTER TABLE positions ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL;
                RAISE NOTICE 'Added updated_at column';
            END IF;
        END $$;
    """)
    
    # Fix transaction status enum type
    print("Fixing transaction status type...")
    
    # First drop any indexes that use the enum types
    await conn.execute("""
        DROP INDEX IF EXISTS idx_positions_status;
        DROP INDEX IF EXISTS idx_positions_pnl;
        DROP INDEX IF EXISTS idx_transactions_type;
    """)
    
    await conn.execute("""
        DO $$
        BEGIN
            -- Check if status is an enum type
            IF EXISTS (
                SELECT 1 
                FROM information_schema.columns 
                WHERE table_name = 'transactions' 
                AND column_name = 'status' 
                AND udt_name = 'transactionstatus'
            ) THEN
                -- Convert to VARCHAR
                ALTER TABLE transactions 
                ALTER COLUMN status TYPE VARCHAR(20) 
                USING status::text;
                
                DROP TYPE IF EXISTS transactionstatus CASCADE;
                RAISE NOTICE 'Converted transaction status from enum to VARCHAR';
            END IF;
            
            -- Do the same for positions status
            IF EXISTS (
                SELECT 1 
                FROM information_schema.columns 
                WHERE table_name = 'positions' 
                AND column_name = 'status' 
                AND udt_name = 'positionstatus'
            ) THEN
                -- Convert to VARCHAR  
                ALTER TABLE positions 
                ALTER COLUMN status TYPE VARCHAR(20) 
                USING status::text;
                
                DROP TYPE IF EXISTS positionstatus CASCADE;
                RAISE NOTICE 'Converted position status from enum to VARCHAR';
            END IF;
        END $$;
    """)
    
    # Recreate the indexes
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status) WHERE status = 'ACTIVE';
        CREATE INDEX IF NOT EXISTS idx_positions_pnl ON positions(user_id, unrealized_pnl_usd) WHERE status = 'ACTIVE';
        CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(tx_type, status);
    """)
    
    # Create missing indexes
    print("Creating missing indexes...")
    
    await conn.execute("""
        -- Positions indexes
        CREATE INDEX IF NOT EXISTS idx_positions_user ON positions(user_id, status);
        CREATE INDEX IF NOT EXISTS idx_positions_created ON positions(created_at DESC);
    """)
    
    # Check the results
    print("\nVerifying changes...")
    
    positions_columns = await conn.fetch("""
        SELECT column_name, data_type, udt_name
        FROM information_schema.columns 
        WHERE table_name = 'positions' 
        AND column_name IN ('created_at', 'updated_at', 'status')
        ORDER BY ordinal_position
    """)
    
    print("Positions columns after fix:")
    for col in positions_columns:
        print(f"  - {col['column_name']}: {col['data_type']} ({col['udt_name']})")
    
    tx_status = await conn.fetchrow("""
        SELECT data_type, udt_name
        FROM information_schema.columns 
        WHERE table_name = 'transactions' 
        AND column_name = 'status'
    """)
    
    print(f"\nTransactions status column: {tx_status['data_type']} ({tx_status['udt_name']})")
    
    # Update alembic version if needed
    if version != '011_fix_missing_columns':
        print(f"\nUpdating alembic version from {version} to 011_fix_missing_columns")
        await conn.execute("UPDATE alembic_version SET version_num = '011_fix_missing_columns'")
    
    await conn.close()
    print("\nDatabase fixes completed successfully!")

asyncio.run(fix_railway_db())