#!/usr/bin/env python3
"""Fix and run migrations on production database."""

import os
import subprocess
import sys

# Use the DATABASE_URL from environment (Railway sets this)
# Don't override it here!

print("🔧 Starting migration fix process...")

# Run alembic upgrade head
print("\n📦 Running database migrations...")
try:
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        check=False
    )
    
    if result.returncode == 0:
        print("✅ Migrations completed successfully!")
        print(result.stdout)
    else:
        print("❌ Migration failed, but continuing...")
        print(result.stderr)
        # Don't exit - let the app start anyway
        
except Exception as e:
    print(f"⚠️  Migration error: {e}")
    # Don't exit - let the app start anyway

print("\n🚀 Starting application...")
# Start the app regardless of migration status
os.system("python run.py")