#!/usr/bin/env python3
"""
Script to clear all keys from Redis cache.
"""

import redis
from urllib.parse import urlparse
import sys

# Redis connection URL
REDIS_URL = "redis://default:JupjBvrNSfMYfNNaYZtkivGAiTgPSqKm@centerbeam.proxy.rlwy.net:42947"

def clear_redis():
    """Clear all keys from Redis."""
    try:
        # Parse the Redis URL
        url = urlparse(REDIS_URL)

        # Connect to Redis
        r = redis.Redis(
            host=url.hostname,
            port=url.port,
            password=url.password,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )

        # Test connection
        print("Testing Redis connection...")
        r.ping()
        print("✓ Connected to Redis successfully")

        # Get the number of keys before clearing
        key_count = r.dbsize()
        print(f"\nFound {key_count} keys in Redis")

        if key_count == 0:
            print("Redis is already empty.")
            return

        # Confirm before clearing
        response = input(f"\nAre you sure you want to delete all {key_count} keys? (yes/no): ")
        if response.lower() != 'yes':
            print("Operation cancelled.")
            return

        # Clear all keys
        print("\nClearing all keys...")
        r.flushdb()

        # Verify
        new_count = r.dbsize()
        print(f"✓ Redis cleared successfully. Current key count: {new_count}")

    except redis.ConnectionError as e:
        print(f"✗ Failed to connect to Redis: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    clear_redis()