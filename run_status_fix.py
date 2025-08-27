#!/usr/bin/env python3
"""Call the API endpoint to fix status capitalization."""

import requests

# Try both http and https
for protocol in ['https', 'http']:
    url = f"{protocol}://n0ir-api-staging.up.railway.app/api/v1/admin/fix-status-capitalization"
    
    try:
        print(f"Trying {url}...")
        response = requests.post(url, headers={'Content-Type': 'application/json'}, timeout=30)
        
        if response.status_code == 200:
            print("Success!")
            print(response.json())
            break
        else:
            print(f"Status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Error with {protocol}: {e}")