#!/usr/bin/env python3
"""
Apply balance adjustment using the admin endpoint.
"""
import json
import urllib.request
import urllib.parse

user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
base_url = 'https://n0ir-api-staging.up.railway.app'

print("=" * 80)
print("APPLYING BALANCE ADJUSTMENT")
print("=" * 80)

# First check current balance
print("\n1. Checking current balance...")
balance_url = f'{base_url}/api/v1/users/{user_id}/balance'
with urllib.request.urlopen(balance_url) as response:
    data = json.loads(response.read())
    current_balance = float(data['available_balance_usdc'])
    print(f"   Current balance: {current_balance} USDC")
    print(f"   Target balance:  0.022543 USDC")
    print(f"   Need to remove:  0.036442 USDC")

# Apply adjustment using admin endpoint
print("\n2. Creating adjustment transaction...")
adjustment_url = f'{base_url}/api/v1/admin/balance-adjustment'

adjustment_data = {
    "user_id": user_id,
    "amount_usdc": 0.036442,
    "adjustment_type": "WITHDRAWAL",  # Remove from balance
    "reason": "Correction for historical withdrawal calculation error",
    "note": "Previous withdrawal was 49.777673 but should have been 49.741231 (0.036442 USDC difference due to accumulated slippage)"
}

headers = {'Content-Type': 'application/json'}

req = urllib.request.Request(
    adjustment_url,
    data=json.dumps(adjustment_data).encode('utf-8'),
    headers=headers,
    method='POST'
)

try:
    with urllib.request.urlopen(req) as response:
        result = json.loads(response.read())
        print(f"   ✅ Adjustment transaction created!")
        print(f"   Transaction ID: {result.get('transaction_id')}")
        print(f"   Type: {result.get('transaction_type')}")
        print(f"   Amount: {result.get('amount_usdc')} USDC")
        
except urllib.error.HTTPError as e:
    print(f"   ❌ Error: {e.code}")
    error_body = e.read().decode('utf-8')
    print(f"   Details: {error_body}")
    exit(1)

# Verify new balance
print("\n3. Verifying new balance...")
with urllib.request.urlopen(balance_url) as response:
    data = json.loads(response.read())
    new_balance = float(data['available_balance_usdc'])
    target_balance = 0.022543
    
    print(f"   New balance:    {new_balance} USDC")
    print(f"   Target balance: {target_balance} USDC")
    print(f"   Difference:     {abs(new_balance - target_balance):.6f} USDC")
    
    if abs(new_balance - target_balance) < 0.001:
        print("\n   ✅ SUCCESS! Balance has been corrected to match on-chain value!")
    else:
        print(f"\n   ⚠️  Balance is still off by {new_balance - target_balance:.6f} USDC")

# Check the balance breakdown
print("\n4. Checking balance breakdown...")
verify_url = f'{base_url}/api/v1/admin/verify-balance/{user_id}'
try:
    with urllib.request.urlopen(verify_url) as response:
        data = json.loads(response.read())
        print(f"   Calculated balance: {data['calculated_balance']} USDC")
        print("   Breakdown:")
        for key, value in data['breakdown'].items():
            print(f"     {key:20}: {value:12.6f} USDC")
except:
    pass

print("\n" + "=" * 80)
print("ADJUSTMENT COMPLETE")
print("=" * 80)
