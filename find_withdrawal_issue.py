#!/usr/bin/env python3
import json
import urllib.request
from decimal import Decimal

user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
url = f'https://n0ir-api-staging.up.railway.app/api/v1/users/{user_id}/transactions?limit=100&sort=asc'
with urllib.request.urlopen(url) as response:
    data = json.loads(response.read())

transactions = [tx for tx in data['transactions'] if tx['status'] == 'CONFIRMED']
transactions.sort(key=lambda x: x['created_at'])

print("WITHDRAWAL ACCURACY ANALYSIS")
print("=" * 80)
print("\nHypothesis: The withdrawals have incorrect amounts, leaving ~0.036 USDC behind")
print("\n" + "=" * 80)

# Track balance with correct accounting
balance = Decimal(0)
print("\nFull transaction flow with running balance:")
print("-" * 80)

for tx in transactions:
    tx_type = tx['transaction_type']
    amount = Decimal(str(tx.get('amount_usdc', 0)))
    created = tx['created_at'][:19]
    
    if tx_type == 'DEPOSIT':
        balance += amount
        print(f"{created} DEPOSIT      +{amount:10.6f} | Balance: {balance:10.6f}")
    elif tx_type in ['WITHDRAWAL', 'WITHDRAW']:
        balance -= amount
        print(f"{created} WITHDRAWAL   -{amount:10.6f} | Balance: {balance:10.6f}")
        # Check if this withdrawal should have been different
        if balance < 0:
            print(f"    ⚠️  NEGATIVE BALANCE! Withdrawal too large by {abs(balance):.6f}")
    elif tx_type == 'POSITION_CREATED':
        usdc_ret = Decimal(str(tx.get('event_data', {}).get('usdc_returned', 0)))
        net = amount - usdc_ret
        balance -= net
        print(f"{created} POS_CREATED  -{net:10.6f} | Balance: {balance:10.6f}")
    elif tx_type == 'POSITION_CLOSED':
        balance += amount
        print(f"{created} POS_CLOSED   +{amount:10.6f} | Balance: {balance:10.6f}")
    elif tx_type == 'AERO_SWAP':
        balance += amount
        print(f"{created} AERO_SWAP    +{amount:10.6f} | Balance: {balance:10.6f}")

print(f"\nFinal calculated balance: {balance:10.6f}")
print(f"API shows: 0.058985")
print(f"Difference: {balance - Decimal('0.058985'):10.6f}")

# Find specific withdrawal issues
print("\n" + "=" * 80)
print("FINDING THE PROBLEMATIC WITHDRAWAL:")
print("-" * 80)

# The last withdrawal before the latest deposit
print("\nLast withdrawal was 49.777673 USDC")
print("If we had withdrawn 49.777673 - 0.036442 = 49.741231 USDC instead,")
print("the balance would be correct!")

print("\nThis suggests the withdrawal amount was calculated incorrectly,")
print("not accounting for accumulated slippage from previous position closes.")
