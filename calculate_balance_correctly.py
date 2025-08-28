#!/usr/bin/env python3
import json
import urllib.request
from decimal import Decimal

# User ID
user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'

# Get ALL transactions
url = f'https://n0ir-api-staging.up.railway.app/api/v1/users/{user_id}/transactions?limit=100&sort=asc'
with urllib.request.urlopen(url) as response:
    data = json.loads(response.read())

deposits = Decimal(0)
withdrawals = Decimal(0)
position_created = Decimal(0)
position_closed = Decimal(0)
aero_swaps = Decimal(0)

print("All transactions in chronological order:")
print("-" * 80)

for tx in data['transactions']:
    tx_type = tx['transaction_type']
    amount = Decimal(str(tx.get('amount_usdc', 0)))
    created = tx['created_at'][:19]
    status = tx.get('status', 'UNKNOWN')
    
    if status != 'CONFIRMED':
        continue
        
    if tx_type == 'DEPOSIT':
        deposits += amount
        print(f"{created} DEPOSIT      +{amount:10.6f} USDC | Total deps: {deposits}")
    elif tx_type in ['WITHDRAWAL', 'WITHDRAW']:
        withdrawals += amount
        print(f"{created} WITHDRAWAL   -{amount:10.6f} USDC | Total withd: {withdrawals}")
    elif tx_type == 'POSITION_CREATED':
        usdc_returned = Decimal(0)
        if tx.get('event_data') and 'usdc_returned' in tx['event_data']:
            usdc_returned = Decimal(str(tx['event_data']['usdc_returned']))
        net = amount - usdc_returned
        position_created += net
        print(f"{created} POS_CREATED  -{net:10.6f} USDC (gross: {amount}, ret: {usdc_returned})")
    elif tx_type == 'POSITION_CLOSED':
        position_closed += amount
        print(f"{created} POS_CLOSED   +{amount:10.6f} USDC")
    elif tx_type == 'AERO_SWAP':
        aero_swaps += amount
        print(f"{created} AERO_SWAP    +{amount:10.6f} USDC")

print("-" * 80)
print("\nBalance calculation:")
print(f"  Total deposits:         +{deposits:12.6f} USDC")
print(f"  Total withdrawals:      -{withdrawals:12.6f} USDC")
print(f"  Positions created (net): -{position_created:12.6f} USDC")
print(f"  Positions closed:       +{position_closed:12.6f} USDC")
print(f"  AERO swaps:             +{aero_swaps:12.6f} USDC")
print(f"  ─────────────────────────────────────────")
balance = deposits - withdrawals - position_created + position_closed + aero_swaps
print(f"  Available balance:       {balance:12.6f} USDC")

print("\n\nCurrent active position calculation:")
print(f"  Latest deposit:          50.000000 USDC")
print(f"  Latest position cost:    49.990000 USDC")
print(f"  USDC returned:            0.012543 USDC")
print(f"  Net position cost:       49.977457 USDC")
print(f"  Expected balance:         0.022543 USDC")
print(f"  Actual calc balance:      {balance:9.6f} USDC")
print(f"  Difference:              {balance - Decimal('0.022543'):9.6f} USDC")
