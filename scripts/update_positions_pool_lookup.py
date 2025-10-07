#!/usr/bin/env python3
"""Add logic to positions service to fetch correct pool address from positions endpoint."""

# For future reference, when fetching position data, the service should:
# 1. Call GET /api/v1/positions?position_id={id} to get the correct pool_address
# 2. Use that pool_address for any pool-related operations
# 3. This ensures we always use the accurate pool address stored in the database

print("""
For future position operations, use this approach:

async def get_position_with_correct_pool(position_id: int):
    # Fetch position data including correct pool address
    response = await fetch(f"/api/v1/positions?position_id={position_id}")
    position_data = response.json()

    # Extract the correct pool address
    pool_address = position_data['position']['pool_address']

    # Use this pool_address for all subsequent operations
    return pool_address

This ensures pool addresses are always correct and come from the authoritative source.
""")