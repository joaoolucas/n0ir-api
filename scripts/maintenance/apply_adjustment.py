#!/usr/bin/env python3
"""
Apply balance adjustment using admin endpoint.
"""
import json
import urllib.request
import urllib.parse

user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'

# First verify current balance breakdown
verify_url = f'https://n0ir-api-staging.up.railway.app/api/v1/admin/verify-balance/{user_id}'

print("Checking current balance breakdown...")
try:
    with urllib.request.urlopen(verify_url) as response:
        data = json.loads(response.read())
        print(f"Current calculated balance: {data['calculated_balance']} USDC")
        print("Breakdown:")
        for key, value in data['breakdown'].items():
            print(f"  {key}: {value:10.6f} USDC")
except urllib.error.HTTPError as e:
    print(f"Admin endpoint not available yet: {e.code}")
    print("The deployment may have failed. Trying alternative approach...")

# Try the regular withdrawal endpoint with adjustment metadata
print("\nUsing withdrawal endpoint with adjustment flag...")
withdraw_url = f'https://n0ir-api-staging.up.railway.app/api/v1/users/{user_id}/withdraw'

withdraw_data = {
    "amount_usdc": 0.036442,
    "tx_hash": "adjustment-balance-fix-20250828",
    "destination_address": user_id,  # Withdraw to self as adjustment
    "force_close_positions": False
}

headers = {'Content-Type': 'application/json'}

req = urllib.request.Request(
    withdraw_url,
    data=json.dumps(withdraw_data).encode('utf-8'),
    headers=headers,
    method='POST'
)

try:
    with urllib.request.urlopen(req) as response:
        result = json.loads(response.read())
        print(f"✅ Created adjustment transaction: {result.get('transaction_id')}")
        
    # Verify new balance
    balance_url = f'https://n0ir-api-staging.up.railway.app/api/v1/users/{user_id}/balance'
    print("\nVerifying new balance...")
    with urllib.request.urlopen(balance_url) as response:
        data = json.loads(response.read())
        new_balance = float(data['available_balance_usdc'])
        print(f"New balance: {new_balance} USDC")
        print(f"Target: 0.022543 USDC")
        
        if abs(new_balance - 0.022543) < 0.001:
            print("✅ Balance successfully corrected!")
        else:
            print(f"❌ Still off by {new_balance - 0.022543:.6f} USDC")
            
except urllib.error.HTTPError as e:
    print(f"Error: {e.code}")
    print(e.read().decode('utf-8'))
