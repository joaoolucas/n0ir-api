#!/usr/bin/env python3
"""Emergency fix for database schema - runs SQL directly."""

import os
import psycopg2
from psycopg2 import sql
import sys

def fix_schema():
    """Apply emergency schema fixes."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL not set")
        return False
    
    print("🔧 Applying emergency schema fixes...")
    
    try:
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        
        # Check current columns
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'positions' 
            AND column_name IN ('unrealized_pnl_usd', 'pnl_usdc')
        """)
        columns = [row[0] for row in cur.fetchall()]
        
        print(f"📋 Found columns: {columns}")
        
        if 'unrealized_pnl_usd' in columns and 'pnl_usdc' not in columns:
            print("⚠️ Found old column names, renaming...")
            
            # Rename columns
            try:
                cur.execute("ALTER TABLE positions RENAME COLUMN unrealized_pnl_usd TO pnl_usdc")
                print("✅ Renamed unrealized_pnl_usd to pnl_usdc")
            except Exception as e:
                print(f"⚠️ Could not rename unrealized_pnl_usd: {e}")
            
            try:
                cur.execute("ALTER TABLE positions RENAME COLUMN unrealized_pnl_pct TO pnl_pct")
                print("✅ Renamed unrealized_pnl_pct to pnl_pct")
            except Exception as e:
                print(f"⚠️ Could not rename unrealized_pnl_pct: {e}")
            
            try:
                cur.execute("ALTER TABLE positions RENAME COLUMN realized_pnl_usd TO realized_pnl_usdc")
                print("✅ Renamed realized_pnl_usd to realized_pnl_usdc")
            except Exception as e:
                print(f"⚠️ Could not rename realized_pnl_usd: {e}")
            
            conn.commit()
            print("✅ Schema fixes applied successfully!")
        elif 'pnl_usdc' in columns:
            print("✅ Schema already has correct column names")
        else:
            print("❌ Neither old nor new columns found - critical error")
            return False
        
        # Check and update alembic version
        cur.execute("SELECT version_num FROM alembic_version")
        version = cur.fetchone()
        if version and version[0] == '026_merge_hedge_into_positions':
            cur.execute("UPDATE alembic_version SET version_num = '027_remove_unused_columns'")
            conn.commit()
            print("✅ Updated alembic version to 027")
        
        cur.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error applying fixes: {e}")
        return False

if __name__ == "__main__":
    success = fix_schema()
    if not success:
        print("❌ Schema fix failed!")
        sys.exit(1)
    print("✅ Schema fix completed!")
    
    # Now start the application
    print("\n🚀 Starting application...")
    os.system("python run.py")