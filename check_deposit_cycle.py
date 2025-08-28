#!/usr/bin/env python3
import json
import urllib.request
import urllib.parse

# User ID
user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'

# Get recent transactions
url = f'https://n0ir-api-staging.up.railway.app/api/v1/users/{user_id}/transactions?limit=20&sort=desc'
with urllib.request.urlopen(url) as response:
    data = json.loads(response.read())

print("Recent transaction flow:")
print("-" * 60)

last_deposit = None
last_withdrawal = None
for tx in data['transactions']:
    tx_type = tx['transaction_type']
    amount = float(tx.get('amount_usdc', 0))
    created = tx['created_at'][:19]
    
    if tx_type == 'DEPOSIT':
        last_deposit = amount
        print(f"{created} DEPOSIT      +{amount:10.6f} USDC")
    elif tx_type in ['WITHDRAWAL', 'WITHDRAW']:
        last_withdrawal = amount
        print(f"{created} WITHDRAWAL   -{amount:10.6f} USDC")
    elif tx_type == 'POSITION_CREATED':
        usdc_returned = 0
        if tx.get('event_data') and 'usdc_returned' in tx['event_data']:
            usdc_returned = float(tx['event_data']['usdc_returned'])
        net = amount - usdc_returned
        print(f"{created} POS_CREATED  -{amount:10.6f} USDC")
        if usdc_returned > 0:
            print(f"                   └─ Returned: +{usdc_returned:10.6f} USDC")
            print(f"                   └─ Net:      -{net:10.6f} USDC")
    elif tx_type == 'POSITION_CLOSED':
        print(f"{created} POS_CLOSED   +{amount:10.6f} USDC")
    elif tx_type == 'AERO_SWAP':
        print(f"{created} AERO_SWAP    +{amount:10.6f} USDC")

print("-" * 60)
print(f"\nLast deposit: {last_deposit} USDC")

# Calculate what the balance should be based on latest deposit
if last_deposit == 50.0:
    print("\nExpected balance calculation (based on latest 50 USDC deposit):")
    print(f"  Deposited:        50.000000 USDC")
    print(f"  Position cost:   -49.990000 USDC")
    print(f"  USDC returned:    +0.012543 USDC")
    print(f"  Net position:    -49.977457 USDC")
    print(f"  Expected balance:  0.022543 USDC")
