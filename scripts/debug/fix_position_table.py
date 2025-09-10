#!/usr/bin/env python3
"""
Script to fix the positions table by removing position_id and making nft_token_id the primary key.
Run this on Railway with: python fix_position_table.py
"""

import os
import asyncio
import asyncpg
from urllib.parse import urlparse


async def fix_positions_table():
    """Fix the positions table schema."""
    
    # Get database URL from environment
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        return False
    
    # Parse the URL
    parsed = urlparse(database_url)
    
    # Connect to database
    try:
        conn = await asyncpg.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            user=parsed.username,
            password=parsed.password,
            database=parsed.path[1:],  # Remove leading /
            ssl='require'
        )
        print(f"Connected to database: {parsed.hostname}")
        
        # Check if position_id column exists
        check_query = """
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'positions' 
        AND column_name = 'position_id';
        """
        result = await conn.fetch(check_query)
        
        if not result:
            print("position_id column does not exist - schema already fixed!")
            await conn.close()
            return True
        
        print("Found position_id column - proceeding with fix...")
        
        # Start transaction
        async with conn.transaction():
            # Step 1: Drop foreign key constraints that reference position_id
            print("Step 1: Dropping foreign key constraints...")
            try:
                await conn.execute("ALTER TABLE transactions DROP CONSTRAINT IF EXISTS fk_transaction_position;")
                print("  - Dropped fk_transaction_position")
            except Exception as e:
                print(f"  - Note: {e}")
            
            # Step 2: Drop the primary key constraint on position_id
            print("Step 2: Dropping primary key constraint...")
            try:
                await conn.execute("ALTER TABLE positions DROP CONSTRAINT IF EXISTS positions_pkey;")
                print("  - Dropped positions_pkey")
            except Exception as e:
                print(f"  - Error dropping primary key: {e}")
            
            # Step 3: Drop the position_id column
            print("Step 3: Dropping position_id column...")
            await conn.execute("ALTER TABLE positions DROP COLUMN IF EXISTS position_id;")
            print("  - Dropped position_id column")
            
            # Step 4: Create new primary key on nft_token_id
            print("Step 4: Creating new primary key on nft_token_id...")
            await conn.execute("ALTER TABLE positions ADD PRIMARY KEY (nft_token_id);")
            print("  - Created primary key on nft_token_id")
            
            # Step 5: Create unique index on nft_token_id for better performance
            print("Step 5: Creating unique index...")
            try:
                await conn.execute("CREATE UNIQUE INDEX idx_position_nft_token_id ON positions (nft_token_id);")
                print("  - Created unique index on nft_token_id")
            except Exception as e:
                print(f"  - Note: Index may already exist: {e}")
            
            # Step 6: Recreate the foreign key for transactions using nft_token_id
            print("Step 6: Recreating foreign key constraints...")
            
            # Check if related_position_id column exists
            check_col = await conn.fetch("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'transactions' 
                AND column_name = 'related_position_id';
            """)
            
            if check_col:
                # Change column type to INTEGER if it exists
                try:
                    await conn.execute("""
                        ALTER TABLE transactions 
                        ALTER COLUMN related_position_id TYPE INTEGER 
                        USING related_position_id::INTEGER;
                    """)
                    print("  - Changed related_position_id to INTEGER type")
                except Exception as e:
                    print(f"  - Note: Could not change column type: {e}")
                
                # Create foreign key
                try:
                    await conn.execute("""
                        ALTER TABLE transactions 
                        ADD CONSTRAINT fk_transaction_position 
                        FOREIGN KEY (related_position_id) 
                        REFERENCES positions(nft_token_id);
                    """)
                    print("  - Created foreign key constraint")
                except Exception as e:
                    print(f"  - Note: Could not create foreign key: {e}")
            else:
                print("  - related_position_id column does not exist, skipping foreign key")
        
        print("\n✅ Successfully fixed positions table schema!")
        print("   - position_id column removed")
        print("   - nft_token_id is now the primary key")
        
        # Verify the fix
        print("\nVerifying schema...")
        columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable, 
                   column_default IS NOT NULL as has_default
            FROM information_schema.columns 
            WHERE table_name = 'positions' 
            ORDER BY ordinal_position;
        """)
        
        print("Current positions table columns:")
        for col in columns:
            print(f"  - {col['column_name']}: {col['data_type']} (nullable: {col['is_nullable']})")
        
        # Check primary key
        pk = await conn.fetch("""
            SELECT a.attname
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = 'positions'::regclass AND i.indisprimary;
        """)
        
        if pk:
            print(f"\nPrimary key: {pk[0]['attname']}")
        
        await conn.close()
        return True
        
    except Exception as e:
        print(f"ERROR: Failed to fix database: {e}")
        return False


if __name__ == "__main__":
    result = asyncio.run(fix_positions_table())
    exit(0 if result else 1)