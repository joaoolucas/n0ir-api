#!/usr/bin/env python3
"""
Database Migration Runner
Usage: python run_migration.py [command]

Commands:
  status    - Show current migration status
  upgrade   - Apply all pending migrations
  downgrade - Revert last migration
  test      - Test migration on a transaction (rollback)
"""

import sys
import os
from sqlalchemy import create_engine, text
from app.core.config import settings
import subprocess

def get_db_url():
    """Get database URL from settings."""
    return settings.database_url or settings.database_private_url

def run_alembic_migration():
    """Run migration using Alembic."""
    commands = {
        'status': ['alembic', 'current'],
        'upgrade': ['alembic', 'upgrade', 'head'],
        'downgrade': ['alembic', 'downgrade', '-1'],
        'history': ['alembic', 'history'],
    }
    
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command not in commands:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)
    
    print(f"Running: {' '.join(commands[command])}")
    result = subprocess.run(commands[command])
    sys.exit(result.returncode)

def run_sql_migration():
    """Run raw SQL migration (alternative method)."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1]
    db_url = get_db_url()
    
    if not db_url:
        print("ERROR: No database URL configured")
        sys.exit(1)
    
    engine = create_engine(db_url)
    
    if command == 'status':
        with engine.connect() as conn:
            # Check current schema
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                ORDER BY ordinal_position
            """))
            print("\nUsers table columns:")
            for row in result:
                print(f"  - {row[0]}")
            
            # Check if protocol_fees exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = 'protocol_fees'
                )
            """))
            has_protocol_fees = result.scalar()
            print(f"\nProtocol_fees table exists: {has_protocol_fees}")
            
            # Check positions columns
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'positions' 
                AND column_name LIKE 'protocol%'
            """))
            protocol_cols = list(result)
            print(f"\nPositions protocol columns: {len(protocol_cols)}")
            for row in protocol_cols:
                print(f"  - {row[0]}")
    
    elif command == 'upgrade':
        print("Applying migration...")
        migration_file = 'migrations/simplify_schema.sql'
        
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
        
        with engine.begin() as conn:  # Auto-commits on success, rolls back on error
            try:
                # Split by semicolons but be careful with functions
                statements = []
                current = []
                in_function = False
                
                for line in migration_sql.split('\n'):
                    if 'DO $$' in line:
                        in_function = True
                    if '$$;' in line:
                        in_function = False
                    
                    current.append(line)
                    
                    if ';' in line and not in_function:
                        statements.append('\n'.join(current))
                        current = []
                
                if current:
                    statements.append('\n'.join(current))
                
                for i, statement in enumerate(statements, 1):
                    statement = statement.strip()
                    if statement and not statement.startswith('--'):
                        print(f"Executing statement {i}/{len(statements)}...")
                        conn.execute(text(statement))
                
                print("✅ Migration completed successfully!")
                
            except Exception as e:
                print(f"❌ Migration failed: {e}")
                print("Transaction rolled back.")
                sys.exit(1)
    
    elif command == 'test':
        print("Testing migration (will rollback)...")
        migration_file = 'migrations/simplify_schema.sql'
        
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
        
        with engine.begin() as conn:
            # Create savepoint
            trans = conn.begin_nested()
            
            try:
                print("Applying migration in test mode...")
                conn.execute(text(migration_sql))
                
                # Test the results
                result = conn.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'users' 
                    AND column_name = 'cdp_owner_wallet_address'
                """))
                
                if result.rowcount == 0:
                    print("✅ Column successfully removed")
                else:
                    print("❌ Column still exists")
                
                # Rollback
                trans.rollback()
                print("✅ Test complete - changes rolled back")
                
            except Exception as e:
                print(f"❌ Test failed: {e}")
                trans.rollback()
                sys.exit(1)
    
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)

if __name__ == "__main__":
    # Check if Alembic is properly configured
    if os.path.exists('alembic.ini'):
        print("Using Alembic for migration...")
        run_alembic_migration()
    else:
        print("Using raw SQL migration...")
        run_sql_migration()