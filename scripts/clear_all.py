#!/usr/bin/env python3
"""Clear all data from both Redis and PostgreSQL database."""

import asyncio
import sys
import subprocess

async def main():
    print("=" * 60)
    print("COMPLETE DATA RESET")
    print("=" * 60)
    print("\nThis will clear ALL data from:")
    print("  1. Redis cache")
    print("  2. PostgreSQL database")
    print("\n⚠️  WARNING: This action CANNOT be undone!")

    response = input("\nAre you ABSOLUTELY SURE you want to continue? (yes/no): ")

    if response.lower() != 'yes':
        print("Aborted")
        return

    print("\n" + "=" * 60)
    print("CLEARING REDIS")
    print("=" * 60)

    # Run Redis clear script
    try:
        result = subprocess.run([sys.executable, "scripts/clear_redis.py"],
                              input="yes\n",
                              text=True,
                              capture_output=True)
        if result.returncode == 0:
            print("✅ Redis cleared successfully")
        else:
            print(f"❌ Failed to clear Redis:\n{result.stderr}")
    except Exception as e:
        print(f"❌ Error clearing Redis: {e}")

    print("\n" + "=" * 60)
    print("CLEARING DATABASE")
    print("=" * 60)

    # Run database clear script
    try:
        result = subprocess.run([sys.executable, "scripts/clear_database.py"],
                              input="yes\n",
                              text=True,
                              capture_output=True)
        if result.returncode == 0:
            print("✅ Database cleared successfully")
        else:
            print(f"❌ Failed to clear database:\n{result.stderr}")
    except Exception as e:
        print(f"❌ Error clearing database: {e}")

    print("\n" + "=" * 60)
    print("✅ COMPLETE RESET FINISHED")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())