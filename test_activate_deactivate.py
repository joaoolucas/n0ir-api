#!/usr/bin/env python3
"""Test script for new activate/deactivate endpoints."""

import asyncio
import httpx
from datetime import datetime

# API URL - update to your staging/production URL as needed
API_URL = "http://localhost:8080"  # Update to your staging URL
# API_URL = "https://your-staging-api.railway.app"

TEST_USER_ID = f"test_user_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"


async def test_activate_deactivate():
    """Test the activate and deactivate endpoints."""
    async with httpx.AsyncClient() as client:
        print(f"\n=== Testing Activate/Deactivate Endpoints ===")
        print(f"Test User ID: {TEST_USER_ID}\n")

        # 1. Test Activate (creates user if not exists)
        print("1. Testing ACTIVATE endpoint...")
        try:
            response = await client.post(
                f"{API_URL}/api/v1/users/{TEST_USER_ID}/activate",
                json={"strategy_type": "delta_neutral"}
            )
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.json()}")
            assert response.status_code == 200, f"Activate failed: {response.text}"
            data = response.json()
            assert data["status"] in ["activated", "already_active"], f"Unexpected status: {data['status']}"
            print("   ✅ ACTIVATE successful\n")
        except Exception as e:
            print(f"   ❌ ACTIVATE failed: {e}\n")
            return

        # 2. Test Activate again (should return already_active)
        print("2. Testing ACTIVATE on already active agent...")
        try:
            response = await client.post(
                f"{API_URL}/api/v1/users/{TEST_USER_ID}/activate",
                json={"strategy_type": "delta_neutral"}
            )
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.json()}")
            data = response.json()
            if data["status"] == "already_active":
                print("   ✅ Correctly detected already active\n")
            else:
                print(f"   ⚠️  Status: {data['status']}\n")
        except Exception as e:
            print(f"   ❌ Second ACTIVATE failed: {e}\n")

        # 3. Test Deactivate without withdrawal
        print("3. Testing DEACTIVATE without withdrawal...")
        try:
            response = await client.post(
                f"{API_URL}/api/v1/users/{TEST_USER_ID}/deactivate",
                json={"withdraw_funds": False}
            )
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.json()}")
            assert response.status_code == 200, f"Deactivate failed: {response.text}"
            data = response.json()
            assert data["status"] in ["deactivated", "already_inactive"], f"Unexpected status: {data['status']}"
            print("   ✅ DEACTIVATE (no withdrawal) successful\n")
        except Exception as e:
            print(f"   ❌ DEACTIVATE failed: {e}\n")

        # 4. Test Activate after deactivate
        print("4. Testing ACTIVATE after deactivation...")
        try:
            response = await client.post(
                f"{API_URL}/api/v1/users/{TEST_USER_ID}/activate",
                json={"strategy_type": "delta_neutral"}
            )
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.json()}")
            assert response.status_code == 200
            print("   ✅ Re-ACTIVATE successful\n")
        except Exception as e:
            print(f"   ❌ Re-ACTIVATE failed: {e}\n")

        # 5. Test Deactivate with withdrawal
        print("5. Testing DEACTIVATE with withdrawal...")
        try:
            response = await client.post(
                f"{API_URL}/api/v1/users/{TEST_USER_ID}/deactivate",
                json={"withdraw_funds": True}
            )
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.json()}")
            assert response.status_code == 200, f"Deactivate with withdrawal failed: {response.text}"
            data = response.json()
            print(f"   Withdrawn amount: {data.get('withdrawn_amount', 'N/A')}")
            print(f"   TX Hash: {data.get('tx_hash', 'N/A')}")
            print("   ✅ DEACTIVATE with withdrawal successful\n")
        except Exception as e:
            print(f"   ❌ DEACTIVATE with withdrawal failed: {e}\n")

        print("=== All tests completed ===\n")


if __name__ == "__main__":
    asyncio.run(test_activate_deactivate())