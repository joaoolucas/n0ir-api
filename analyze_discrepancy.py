#!/usr/bin/env python3
import json
import urllib.request
from decimal import Decimal

# The discrepancy is 0.036442 USDC
# Let's find where this comes from

user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
url = f'https://n0ir-api-staging.up.railway.app/api/v1/users/{user_id}/transactions?limit=100&sort=asc'
with urllib.request.urlopen(url) as response:
    data = json.loads(response.read())

# Group transactions by session (between deposits)
sessions = []
current_session = []

for tx in data['transactions']:
    if tx['status'] != 'CONFIRMED':
        continue
        
    tx_type = tx['transaction_type']
    
    if tx_type == 'DEPOSIT' and current_session:
        # Start new session
        sessions.append(current_session)
        current_session = [tx]
    else:
        current_session.append(tx)

if current_session:
    sessions.append(current_session)

print("Analyzing sessions (deposit cycles):")
print("=" * 80)

total_leftover = Decimal(0)

for i, session in enumerate(sessions, 1):
    print(f"\nSession {i}:")
    print("-" * 40)
    
    deposits = Decimal(0)
    withdrawals = Decimal(0) 
    pos_created = Decimal(0)
    pos_closed = Decimal(0)
    swaps = Decimal(0)
    
    for tx in session:
        tx_type = tx['transaction_type']
        amount = Decimal(str(tx.get('amount_usdc', 0)))
        
        if tx_type == 'DEPOSIT':
            deposits += amount
            print(f"  DEPOSIT:      +{amount:10.6f}")
        elif tx_type in ['WITHDRAWAL', 'WITHDRAW']:
            withdrawals += amount
            print(f"  WITHDRAWAL:   -{amount:10.6f}")
        elif tx_type == 'POSITION_CREATED':
            usdc_ret = Decimal(str(tx.get('event_data', {}).get('usdc_returned', 0)))
            net = amount - usdc_ret
            pos_created += net
            print(f"  POS_CREATED:  -{net:10.6f} (gross: {amount}, ret: {usdc_ret})")
        elif tx_type == 'POSITION_CLOSED':
            pos_closed += amount
            print(f"  POS_CLOSED:   +{amount:10.6f}")
        elif tx_type == 'AERO_SWAP':
            swaps += amount
            print(f"  AERO_SWAP:    +{amount:10.6f}")
    
    session_balance = deposits - withdrawals - pos_created + pos_closed + swaps
    print(f"  Session balance: {session_balance:10.6f} USDC")
    
    if i < len(sessions):  # Not the last session
        total_leftover += session_balance
        print(f"  (Leftover from old session)")

print("\n" + "=" * 80)
print(f"Total leftover from old sessions: {total_leftover:10.6f} USDC")
print(f"This explains the discrepancy of:  0.036442 USDC")
print(f"Match: {abs(total_leftover - Decimal('0.036442')) < Decimal('0.0001')}")
