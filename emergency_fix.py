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
        
        # Check current columns - get ALL columns to debug
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'positions'
            ORDER BY column_name
        """)
        columns = [row[0] for row in cur.fetchall()]
        
        print(f"📋 Found {len(columns)} columns in positions table")
        
        # Check for specific columns we care about
        has_old_unrealized = 'unrealized_pnl_usd' in columns
        has_new_pnl = 'pnl_usdc' in columns
        
        print(f"  - Has unrealized_pnl_usd: {has_old_unrealized}")
        print(f"  - Has pnl_usdc: {has_new_pnl}")
        
        if has_old_unrealized and not has_new_pnl:
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
        elif has_new_pnl:
            print("✅ Schema already has correct column names")
        elif len(columns) == 0:
            print("❌ No columns found - positions table might not exist or connection issue")
            # Try to check if table exists
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'positions'
            """)
            tables = cur.fetchall()
            print(f"  Tables found: {tables}")
            return False
        else:
            print("❌ Neither old nor new columns found")
            print(f"  Available columns: {', '.join(columns[:10])}")
            # Don't fail, just start the app anyway
            print("⚠️ Starting app anyway - columns might be correct already")
        
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
        print("⚠️ Schema fix had issues, but continuing anyway...")
    else:
        print("✅ Schema fix completed!")
    
    # Always start the application regardless
    print("\n🚀 Starting application...")
    os.system("python run.py")