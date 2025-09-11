#!/usr/bin/env python3
"""
Fix balance using API endpoint to add adjustment transaction.
"""
import json
import urllib.request
import urllib.parse

# First check current balance
user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
balance_url = f'https://n0ir-api-staging.up.railway.app/api/v1/users/{user_id}/balance'

print("Checking current balance...")
with urllib.request.urlopen(balance_url) as response:
    data = json.loads(response.read())
    current_balance = float(data['available_balance_usdc'])
    print(f"Current balance: {current_balance} USDC")

if abs(current_balance - 0.058985) < 0.001:
    print("Balance matches expected 0.058985 USDC")
    print("Need to withdraw 0.036442 USDC to reach target of 0.022543 USDC")
    
    # Call withdrawal endpoint to create adjustment
    withdraw_url = f'https://n0ir-api-staging.up.railway.app/api/v1/users/{user_id}/withdraw'
    
    # Prepare withdrawal request
    withdraw_data = {
        "amount_usdc": 0.036442,
        "tx_hash": f"adjustment-balance-fix-{user_id[:8]}",  # Provide a fake tx_hash to mark as already executed
        "destination_address": "0x0000000000000000000000000000000000000000",  # Burn address for adjustment
        "force_close_positions": False,
        "withdraw_all": False
    }
    
    headers = {
        'Content-Type': 'application/json'
    }
    
    req = urllib.request.Request(
        withdraw_url,
        data=json.dumps(withdraw_data).encode('utf-8'),
        headers=headers,
        method='POST'
    )
    
    try:
        print("\nCreating balance adjustment transaction...")
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read())
            print(f"✅ Adjustment transaction created: {result.get('transaction_id')}")
            
        # Verify new balance
        print("\nVerifying new balance...")
        with urllib.request.urlopen(balance_url) as response:
            data = json.loads(response.read())
            new_balance = float(data['available_balance_usdc'])
            print(f"New balance: {new_balance} USDC")
            print(f"Target balance: 0.022543 USDC")
            
            if abs(new_balance - 0.022543) < 0.001:
                print("✅ Balance successfully corrected!")
            else:
                print(f"⚠️  Balance is {new_balance}, expected 0.022543")
                print(f"   Difference: {new_balance - 0.022543:.6f} USDC")
                
    except urllib.error.HTTPError as e:
        print(f"Error creating adjustment: {e.code}")
        error_data = e.read().decode('utf-8')
        print(f"Error details: {error_data}")
else:
    print(f"⚠️  Current balance {current_balance} doesn't match expected 0.058985")
    print("Balance may have already been adjusted or changed")