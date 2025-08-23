#!/usr/bin/env python3
"""
Railway Database Migration Tool
Run migrations on your Railway PostgreSQL database

Usage:
  python migrate_railway.py status    - Check current schema
  python migrate_railway.py migrate   - Apply migration
  python migrate_railway.py test      - Test connection
"""

import sys
import os
from datetime import datetime
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import SQLAlchemyError

# Railway Database URL
DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

def test_connection():
    """Test database connection."""
    print("🧪 Testing connection to Railway database...")
    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()
            print(f"✅ Connected successfully!")
            print(f"PostgreSQL version: {version}")
            return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

def check_status():
    """Check current schema status."""
    print("📊 Checking current schema status...\n")
    
    try:
        engine = create_engine(DATABASE_URL)
        inspector = inspect(engine)
        
        with engine.connect() as conn:
            # 1. Check users table
            print("1. USERS table columns:")
            if 'users' in inspector.get_table_names():
                columns = inspector.get_columns('users')
                for col in columns:
                    indicator = "❌" if col['name'] in ['cdp_owner_wallet_address', 'cdp_owner_wallet_name'] else "✅"
                    print(f"   {indicator} {col['name']} ({col['type']})")
            else:
                print("   ⚠️  Table does not exist")
            
            print("\n2. PROTOCOL_FEES table:")
            if 'protocol_fees' in inspector.get_table_names():
                print("   ❌ Still exists (should be removed)")
                # Count records
                result = conn.execute(text("SELECT COUNT(*) FROM protocol_fees"))
                count = result.scalar()
                print(f"   📊 Contains {count} records")
            else:
                print("   ✅ Removed (good!)")
            
            print("\n3. POSITIONS table protocol fee columns:")
            if 'positions' in inspector.get_table_names():
                columns = inspector.get_columns('positions')
                protocol_cols = [col for col in columns if 'protocol' in col['name'].lower()]
                
                expected = ['protocol_fee_amount', 'protocol_fee_collected', 'protocol_fee_tx_hash']
                for exp in expected:
                    found = any(col['name'] == exp for col in protocol_cols)
                    indicator = "✅" if found else "❌"
                    print(f"   {indicator} {exp}")
            else:
                print("   ⚠️  Table does not exist")
            
            print("\n4. TRANSACTIONS table:")
            if 'transactions' in inspector.get_table_names():
                columns = inspector.get_columns('transactions')
                has_related = any(col['name'] == 'related_position_id' for col in columns)
                indicator = "✅" if has_related else "❌"
                print(f"   {indicator} related_position_id column")
                
                # Check transaction types
                result = conn.execute(text("""
                    SELECT DISTINCT transaction_type 
                    FROM transactions 
                    ORDER BY transaction_type
                """))
                types = [row[0] for row in result]
                print(f"   📊 Transaction types: {', '.join(types)}")
            
            return True
            
    except Exception as e:
        print(f"❌ Error checking status: {e}")
        return False

def run_migration():
    """Run the schema migration."""
    print("🔄 Starting migration on Railway database...\n")
    
    if not test_connection():
        print("❌ Cannot proceed without database connection")
        return False
    
    # Confirm with user
    print("\n⚠️  WARNING: This will modify your production database!")
    print("The following changes will be made:")
    print("  1. Remove cdp_owner_wallet_address from users table")
    print("  2. Remove cdp_owner_wallet_name from users table")
    print("  3. Add protocol fee tracking to positions table")
    print("  4. Add related_position_id to transactions table")
    print("  5. Delete protocol_fees table")
    print("")
    
    response = input("Are you sure you want to proceed? Type 'YES' to continue: ")
    if response != 'YES':
        print("❌ Migration cancelled")
        return False
    
    try:
        engine = create_engine(DATABASE_URL)
        
        with engine.begin() as conn:  # Transaction - auto rollback on error
            print("\n📝 Executing migration steps...")
            
            # Step 1: Remove redundant columns from users
            print("1. Removing redundant columns from users table...")
            try:
                conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS cdp_owner_wallet_address"))
                conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS cdp_owner_wallet_name"))
                print("   ✅ Columns removed")
            except Exception as e:
                print(f"   ⚠️  Warning: {e}")
            
            # Step 2: Add protocol fee tracking to positions
            print("2. Adding protocol fee columns to positions table...")
            try:
                conn.execute(text("""
                    ALTER TABLE positions 
                    ADD COLUMN IF NOT EXISTS protocol_fee_amount DECIMAL(20,6) DEFAULT 0,
                    ADD COLUMN IF NOT EXISTS protocol_fee_collected BOOLEAN DEFAULT FALSE,
                    ADD COLUMN IF NOT EXISTS protocol_fee_tx_hash VARCHAR
                """))
                print("   ✅ Columns added")
            except Exception as e:
                print(f"   ⚠️  Warning: {e}")
            
            # Step 3: Add related position to transactions
            print("3. Adding related_position_id to transactions table...")
            try:
                conn.execute(text("""
                    ALTER TABLE transactions 
                    ADD COLUMN IF NOT EXISTS related_position_id INTEGER
                """))
                
                # Check if positions table has nft_token_id
                result = conn.execute(text("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = 'positions' AND column_name = 'nft_token_id'
                """))
                
                if result.rowcount > 0:
                    conn.execute(text("""
                        ALTER TABLE transactions
                        ADD CONSTRAINT fk_transaction_position 
                        FOREIGN KEY (related_position_id) 
                        REFERENCES positions(nft_token_id)
                    """))
                
                print("   ✅ Column and foreign key added")
            except Exception as e:
                print(f"   ⚠️  Warning: {e}")
            
            # Step 4: Migrate protocol_fees data if table exists
            print("4. Migrating protocol_fees data...")
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = 'protocol_fees'
                )
            """))
            
            if result.scalar():
                # Check if positions has position_id column
                result = conn.execute(text("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = 'positions' AND column_name = 'position_id'
                """))
                
                if result.rowcount > 0:
                    # Migrate data
                    conn.execute(text("""
                        UPDATE positions p
                        SET protocol_fee_amount = pf.fee_amount_usdc,
                            protocol_fee_collected = pf.collected,
                            protocol_fee_tx_hash = pf.collection_tx_hash
                        FROM protocol_fees pf
                        WHERE p.position_id = pf.position_id
                    """))
                    print("   ✅ Data migrated")
                
                # Drop protocol_fees table
                conn.execute(text("DROP TABLE IF EXISTS protocol_fees CASCADE"))
                print("   ✅ protocol_fees table removed")
            else:
                print("   ℹ️  protocol_fees table doesn't exist, skipping")
            
            # Step 5: Create indexes
            print("5. Creating indexes...")
            try:
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_position_protocol_fee_collected 
                    ON positions(protocol_fee_collected)
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_position_protocol_fee_tx 
                    ON positions(protocol_fee_tx_hash)
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_transaction_related_position 
                    ON transactions(related_position_id)
                """))
                print("   ✅ Indexes created")
            except Exception as e:
                print(f"   ⚠️  Warning: {e}")
            
            # Step 6: Clean up old indexes
            print("6. Cleaning up old indexes...")
            try:
                conn.execute(text("DROP INDEX IF EXISTS idx_user_cdp_owner"))
                print("   ✅ Old indexes removed")
            except Exception as e:
                print(f"   ⚠️  Warning: {e}")
            
            print("\n✅ Migration completed successfully!")
            return True
            
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        print("Transaction has been rolled back - no changes were made.")
        return False

def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == 'test':
        test_connection()
    elif command == 'status':
        check_status()
    elif command == 'migrate':
        if run_migration():
            print("\n📊 New schema status:")
            check_status()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)

if __name__ == "__main__":
    main()