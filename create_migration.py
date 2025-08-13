#!/usr/bin/env python
"""
Script to create an initial Alembic migration for the database.
Run this to generate the migration files after setting up your DATABASE_URL.

Usage:
    python create_migration.py
"""

import os
import subprocess
import sys

def main():
    # Check if DATABASE_URL is set
    if not os.getenv("DATABASE_URL"):
        print("WARNING: DATABASE_URL not set. Migration will be created but cannot be applied without a database.")
        print("To set DATABASE_URL for testing, you can use:")
        print("  export DATABASE_URL=postgresql://user:pass@localhost/dbname")
        print()
    
    # Create initial migration
    print("Creating initial database migration...")
    try:
        result = subprocess.run(
            ["alembic", "revision", "--autogenerate", "-m", "Initial database schema"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ Migration created successfully!")
            print(result.stdout)
            print("\nTo apply the migration, run:")
            print("  alembic upgrade head")
        else:
            print("❌ Failed to create migration:")
            print(result.stderr)
            sys.exit(1)
            
    except FileNotFoundError:
        print("❌ Alembic not found. Please install it with: pip install alembic")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()