#!/usr/bin/env python3
"""Run database migrations manually."""

import asyncio
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from app.core.config import settings


def run_migrations():
    """Run critical migrations directly."""
    engine = create_engine(settings.database_url or settings.get_database_url())
    
    with engine.begin() as conn:
        # Check if confirmed_at column exists
        try:
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='transactions' 
                AND column_name='confirmed_at'
            """))
            
            if not result.fetchone():
                print("📦 Adding confirmed_at column to transactions table...")
                conn.execute(text("""
                    ALTER TABLE transactions 
                    ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMP WITH TIME ZONE
                """))
                
                # Set confirmed_at for existing confirmed transactions
                conn.execute(text("""
                    UPDATE transactions 
                    SET confirmed_at = created_at 
                    WHERE status = 'CONFIRMED' 
                    AND confirmed_at IS NULL
                """))
                
                print("✅ Migration completed successfully!")
            else:
                print("ℹ️ confirmed_at column already exists")
                
        except ProgrammingError as e:
            print(f"❌ Migration failed: {e}")
            return False
    
    return True


if __name__ == "__main__":
    if run_migrations():
        print("✅ All migrations completed")
        sys.exit(0)
    else:
        print("❌ Migration failed")
        sys.exit(1)