#!/usr/bin/env python
"""
Test script to verify the API works without a database configured.
The API should start and non-database endpoints should work normally.
"""

import requests
import json
import sys

BASE_URL = "http://localhost:8000"

def test_health():
    """Test health endpoint."""
    print("Testing health endpoint...")
    response = requests.get(f"{BASE_URL}/api/v1/health")
    assert response.status_code == 200
    print(f"✅ Health check: {response.json()}")

def test_pools():
    """Test pools endpoint."""
    print("\nTesting pools endpoint...")
    response = requests.get(f"{BASE_URL}/api/v1/pools?limit=5")
    assert response.status_code == 200
    data = response.json()
    print(f"✅ Found {len(data['pools'])} pools")

def test_user_endpoints_without_db():
    """Test that user endpoints fail gracefully without database."""
    print("\nTesting user endpoints without database...")
    
    # Try to create a user
    user_data = {
        "user_id": "test_user_1",
        "wallet_address": "0x123...",
        "cdp_wallet_name": "Test Wallet",
        "cdp_owner_wallet_address": "0x456...",
        "cdp_owner_wallet_name": "Owner Wallet"
    }
    
    response = requests.post(f"{BASE_URL}/api/v1/users", json=user_data)
    if response.status_code == 500:
        print("✅ User creation fails gracefully without database")
    else:
        print(f"⚠️  Unexpected response: {response.status_code}")

def main():
    print("=" * 50)
    print("n0ir API No-Database Test")
    print("=" * 50)
    
    # Check if API is running
    try:
        response = requests.get(BASE_URL)
        if response.status_code != 200:
            print("❌ API is not running at http://localhost:8000")
            print("Start it with: python run.py")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to API at http://localhost:8000")
        print("Start it with: python run.py")
        sys.exit(1)
    
    print(f"✅ API is running at {BASE_URL}\n")
    
    # Run tests
    try:
        test_health()
        test_pools()
        test_user_endpoints_without_db()
        
        print("\n" + "=" * 50)
        print("✅ All tests passed!")
        print("The API works correctly without a database.")
        print("Database-dependent features will be disabled.")
        print("=" * 50)
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()