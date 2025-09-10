#!/usr/bin/env python3
"""Simple test to check user data structure."""

import requests
import json

# Configuration
API_URL = "https://n0ir-api-production.up.railway.app"
BEARER_TOKEN = "5RRJ8kHdu5M6HL91hY5bUI0abWtbANwjqVKtmjq4BMk="
USER_ID = "0xC2952cc28EDf37B053188D89e6ac888B9855d132"

headers = {
    "Authorization": f"Bearer {BEARER_TOKEN}",
    "Content-Type": "application/json"
}

# Get transactions
response = requests.get(f"{API_URL}/api/v1/users/{USER_ID}/transactions", headers=headers)
print(f"Transactions endpoint status: {response.status_code}")
print(f"Response type: {type(response.json())}")
print(f"Response content:\n{json.dumps(response.json(), indent=2)}")