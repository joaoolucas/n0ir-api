#!/usr/bin/env python3
import json
import urllib.request
from decimal import Decimal

user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
url = f'https://n0ir-api-staging.up.railway.app/api/v1/users/{user_id}/transactions?limit=100&sort=asc'
with urllib.request.urlopen(url) as response:
    data = json.loads(response.read())

print("FULL TRANSACTION ANALYSIS")
print("=" * 100)
print("\nKey Question: Why is balance 0.058985 instead of 0.022543?")
print("Expected: Latest deposit (50) - Net position cost (49.977457) = 0.022543")
print("Actual: 0.058985")
print("Discrepancy: 0.036442 USDC")
print("\n" + "=" * 100)

# Find the most recent withdrawal and deposit to understand the "reset point"
transactions = [tx for tx in data['transactions'] if tx['status'] == 'CONFIRMED']

# Find the index of the latest 50 USDC deposit
latest_deposit_idx = None
for i, tx in enumerate(transactions):
    if tx['transaction_type'] == 'DEPOSIT' and float(tx.get('amount_usdc', 0)) == 50.0:
        if tx['created_at'] == '2025-08-28T16:39:28.640588Z':  # The specific latest deposit
            latest_deposit_idx = i
            break

print(f"\nFound latest 50 USDC deposit at index {latest_deposit_idx}")

# Check what happened BEFORE this deposit
print("\n--- TRANSACTIONS BEFORE THE LATEST 50 USDC DEPOSIT ---")
balance_before = Decimal(0)
deposits_before = Decimal(0)
withdrawals_before = Decimal(0)
pos_created_before = Decimal(0)
pos_closed_before = Decimal(0)
swaps_before = Decimal(0)

if latest_deposit_idx is not None:
    for tx in transactions[:latest_deposit_idx]:
        tx_type = tx['transaction_type']
        amount = Decimal(str(tx.get('amount_usdc', 0)))
        created = tx['created_at'][:19]
        
        if tx_type == 'DEPOSIT':
            deposits_before += amount
            balance_before += amount
            print(f"{created} DEPOSIT      +{amount:10.6f} | Running bal: {balance_before:10.6f}")
        elif tx_type in ['WITHDRAWAL', 'WITHDRAW']:
            withdrawals_before += amount
            balance_before -= amount
            print(f"{created} WITHDRAWAL   -{amount:10.6f} | Running bal: {balance_before:10.6f}")
        elif tx_type == 'POSITION_CREATED':
            usdc_ret = Decimal(str(tx.get('event_data', {}).get('usdc_returned', 0)))
            net = amount - usdc_ret
            pos_created_before += net
            balance_before -= net
            print(f"{created} POS_CREATE   -{net:10.6f} | Running bal: {balance_before:10.6f}")
        elif tx_type == 'POSITION_CLOSED':
            pos_closed_before += amount
            balance_before += amount
            print(f"{created} POS_CLOSE    +{amount:10.6f} | Running bal: {balance_before:10.6f}")
        elif tx_type == 'AERO_SWAP':
            swaps_before += amount
            balance_before += amount
            print(f"{created} AERO_SWAP    +{amount:10.6f} | Running bal: {balance_before:10.6f}")

print(f"\n*** BALANCE BEFORE LATEST 50 USDC DEPOSIT: {balance_before:10.6f} USDC ***")
print(f"This should have been ~0 if the previous withdrawal cleared everything")

# Check the withdrawal just before the latest deposit
print("\n--- CHECKING LAST WITHDRAWAL BEFORE LATEST DEPOSIT ---")
last_withdrawal_amount = Decimal('49.777673')
print(f"Last withdrawal amount: {last_withdrawal_amount}")
print(f"Balance before that withdrawal would have been: {balance_before + last_withdrawal_amount:10.6f}")
print(f"After withdrawal, balance was: {balance_before:10.6f}")

# Now track what happened AFTER the latest deposit
print("\n--- TRANSACTIONS AFTER THE LATEST 50 USDC DEPOSIT ---")
balance_after = balance_before + Decimal('50.0')  # The deposit itself
print(f"After deposit: Balance = {balance_after:10.6f}")

if latest_deposit_idx is not None:
    # Skip the deposit itself (index latest_deposit_idx) and the POS_CREATED before it (index 0)
    # The POS_CREATED at index 0 is AFTER the deposit chronologically
    remaining_txs = [transactions[0]]  # Just the position created after deposit
    
    for tx in remaining_txs:
        tx_type = tx['transaction_type']
        amount = Decimal(str(tx.get('amount_usdc', 0)))
        created = tx['created_at'][:19]
        
        if tx_type == 'POSITION_CREATED':
            usdc_ret = Decimal(str(tx.get('event_data', {}).get('usdc_returned', 0)))
            net = amount - usdc_ret
            balance_after -= net
            print(f"{created} POS_CREATE   -{net:10.6f} | Balance: {balance_after:10.6f}")

print(f"\n*** FINAL CALCULATED BALANCE: {balance_after:10.6f} USDC ***")
print(f"*** EXPECTED BALANCE: 0.022543 USDC ***")
print(f"*** ACTUAL API BALANCE: 0.058985 USDC ***")

print("\n" + "=" * 100)
print("ANALYSIS SUMMARY:")
print("-" * 50)
print(f"1. Balance carried over from before latest deposit: {balance_before:10.6f} USDC")
print(f"2. This carryover explains the discrepancy: {balance_before:10.6f} ≈ 0.036442")
print(f"3. The last withdrawal of {last_withdrawal_amount} did NOT zero out the balance")
print(f"4. There was a residual balance from previous cycles")
print("\nPOSSIBLE CAUSES:")
print("- Slippage on position closes (getting back less than invested)")
print("- Protocol fees not accounted for")
print("- Rounding differences accumulating over time")
print("- Missing transactions or events")
print("- AERO swaps not fully accounting for value")
