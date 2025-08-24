#!/usr/bin/env python3
"""Test script for blockchain balance sync functionality."""

import asyncio
import httpx
from decimal import Decimal

# Test user ID from your example
TEST_USER_ID = "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51"
API_BASE_URL = "http://localhost:8000/api/v1"


async def test_balance_sync():
    """Test the balance sync endpoint."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        print(f"Testing balance sync for user: {TEST_USER_ID}")
        print("-" * 60)
        
        # First, get current balance from the API
        print("1. Fetching current balance from API...")
        response = await client.get(f"{API_BASE_URL}/users/{TEST_USER_ID}/balance")
        
        if response.status_code == 200:
            balance_data = response.json()
            print(f"   Current DB balance: ${balance_data['usdc_balance']:.2f}")
            print(f"   Positions value: ${balance_data['positions_value']:.2f}")
            print(f"   Total value: ${balance_data['total_value']:.2f}")
        else:
            print(f"   Error fetching balance: {response.status_code} - {response.text}")
            return
        
        print("\n2. Triggering blockchain balance sync...")
        response = await client.post(f"{API_BASE_URL}/users/{TEST_USER_ID}/sync-balance")
        
        if response.status_code == 200:
            sync_result = response.json()
            print(f"   Blockchain balance: ${sync_result['blockchain_balance']:.2f}")
            print(f"   DB balance (before): ${sync_result['db_balance']:.2f}")
            print(f"   Difference: ${sync_result['difference']:.2f}")
            
            if sync_result.get('reconciled'):
                print(f"   ✓ Balance reconciled!")
                print(f"   Adjustment type: {sync_result['adjustment_type']}")
                print(f"   Adjustment amount: ${sync_result['adjustment_amount']:.2f}")
            elif abs(sync_result['difference']) < 0.01:
                print(f"   ✓ Balance already in sync (difference < $0.01)")
            else:
                print(f"   ⚠ Balance discrepancy detected but not reconciled")
                if 'error' in sync_result:
                    print(f"   Error: {sync_result['error']}")
        else:
            print(f"   Error syncing balance: {response.status_code} - {response.text}")
            return
        
        print("\n3. Verifying updated balance...")
        response = await client.get(f"{API_BASE_URL}/users/{TEST_USER_ID}/balance")
        
        if response.status_code == 200:
            balance_data = response.json()
            print(f"   Updated DB balance: ${balance_data['usdc_balance']:.2f}")
            print(f"   Positions value: ${balance_data['positions_value']:.2f}")
            print(f"   Total value: ${balance_data['total_value']:.2f}")
            
            # Check if the balance now matches blockchain
            if sync_result.get('reconciled'):
                expected_balance = sync_result['blockchain_balance']
                actual_balance = balance_data['usdc_balance']
                if abs(expected_balance - actual_balance) < 0.01:
                    print(f"\n✅ SUCCESS: Balance successfully synced with blockchain!")
                else:
                    print(f"\n❌ ERROR: Balance still doesn't match after sync")
        else:
            print(f"   Error fetching updated balance: {response.status_code} - {response.text}")


async def test_all_users_sync():
    """Test syncing all users' balances."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("\nTesting sync for all users...")
        print("-" * 60)
        
        # Get all users
        response = await client.get(f"{API_BASE_URL}/users")
        if response.status_code != 200:
            print(f"Error fetching users: {response.status_code}")
            return
        
        users = response.json()
        print(f"Found {len(users)} users")
        
        for user in users:
            user_id = user['user_id']
            print(f"\nSyncing balance for {user_id}...")
            
            response = await client.post(f"{API_BASE_URL}/users/{user_id}/sync-balance")
            if response.status_code == 200:
                sync_result = response.json()
                if sync_result.get('reconciled'):
                    print(f"  ✓ Reconciled: {sync_result['adjustment_amount']:.2f} USDC")
                else:
                    print(f"  ✓ In sync (diff: {sync_result.get('difference', 0):.2f} USDC)")
            else:
                print(f"  ✗ Error: {response.status_code}")


if __name__ == "__main__":
    print("Blockchain Balance Sync Test")
    print("=" * 60)
    asyncio.run(test_balance_sync())
    
    # Optionally test all users
    # asyncio.run(test_all_users_sync())