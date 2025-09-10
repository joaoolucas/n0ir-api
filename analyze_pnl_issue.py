#!/usr/bin/env python3
"""Analyze PnL calculation issue for user."""

import requests
import json
from decimal import Decimal
from datetime import datetime

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
data = response.json()
transactions = data.get('transactions', [])

print(f"Total transactions: {len(transactions)}")
print("=" * 80)

# Analyze deposits and withdrawals
deposits = []
withdrawals = []
position_created = []
position_closed = []

for tx in transactions:
    tx_type = tx.get('transaction_type', '')
    if tx_type == 'DEPOSIT':
        deposits.append(tx)
    elif tx_type == 'WITHDRAWAL':
        withdrawals.append(tx)
    elif tx_type == 'POSITION_CREATED':
        position_created.append(tx)
    elif tx_type == 'POSITION_CLOSED':
        position_closed.append(tx)

# Calculate actual deposits (from user wallet to CDP wallet)
user_wallet = USER_ID.lower()
cdp_wallet = "0x1409f9dfb8c05a31a5fb4b3ffeea60298bef30bb".lower()

actual_deposits = []
for tx in deposits:
    event_data = tx.get('event_data', {})
    from_addr = event_data.get('from_address', '').lower()
    to_addr = event_data.get('to_address', '').lower()
    
    if to_addr == cdp_wallet and from_addr == user_wallet:
        actual_deposits.append(tx)

print(f"\n## Deposits Analysis:")
print(f"Total deposit transactions: {len(deposits)}")
print(f"Actual deposits from user wallet: {len(actual_deposits)}")

total_deposits = Decimal(0)
for tx in actual_deposits:
    amount = Decimal(str(tx.get('amount_usdc', 0)))
    total_deposits += amount
    print(f"  - {amount} USDC on {tx.get('created_at', 'N/A')[:10]}")

print(f"Total actual deposits: {total_deposits} USDC")

# Calculate actual withdrawals
actual_withdrawals = []
for tx in withdrawals:
    event_data = tx.get('event_data', {})
    from_addr = event_data.get('from_address', '').lower()
    to_addr = event_data.get('to_address', '').lower()
    
    if from_addr == cdp_wallet and to_addr == user_wallet:
        actual_withdrawals.append(tx)

print(f"\n## Withdrawals Analysis:")
print(f"Total withdrawal transactions: {len(withdrawals)}")
print(f"Actual withdrawals to user wallet: {len(actual_withdrawals)}")

total_withdrawals = Decimal(0)
for tx in actual_withdrawals:
    amount = Decimal(str(tx.get('amount_usdc', 0)))
    total_withdrawals += amount
    print(f"  - {amount} USDC on {tx.get('created_at', 'N/A')[:10]}")

print(f"Total actual withdrawals: {total_withdrawals} USDC")

# Calculate net deposits
net_deposits = total_deposits - total_withdrawals
print(f"\n## Net Deposits: {net_deposits} USDC")

# Analyze closed positions
print(f"\n## Closed Positions Analysis:")
print(f"Total positions created: {len(position_created)}")
print(f"Total positions closed: {len(position_closed)}")

# Map position creation to closing
positions_map = {}
for tx in position_created:
    event_data = tx.get('event_data', {})
    token_id = str(event_data.get('tokenId', ''))
    if token_id:
        positions_map[token_id] = {
            'created': tx,
            'entry_amount': Decimal(str(tx.get('amount_usdc', 0)))
        }

# Calculate PnL from closed positions
total_realized_pnl = Decimal(0)
for tx in position_closed:
    event_data = tx.get('event_data', {})
    token_id = str(event_data.get('tokenId', ''))
    exit_amount = Decimal(str(tx.get('amount_usdc', 0)))
    
    if token_id in positions_map:
        entry_amount = positions_map[token_id]['entry_amount']
        pnl = exit_amount - entry_amount
        total_realized_pnl += pnl
        print(f"  Token {token_id}: Entry={entry_amount}, Exit={exit_amount}, PnL={pnl}")

print(f"\nTotal Realized PnL from closed positions: {total_realized_pnl} USDC")

# Get positions
response = requests.get(f"{API_URL}/api/v1/users/{USER_ID}/positions", headers=headers)
positions = response.json()

active_positions = [p for p in positions if p.get('status') == 'ACTIVE']
closed_positions = [p for p in positions if p.get('status') == 'CLOSED']

print(f"\n## Positions Status:")
print(f"Active positions: {len(active_positions)}")
print(f"Closed positions: {len(closed_positions)}")

# Calculate current portfolio value
total_unrealized = Decimal(0)
for pos in active_positions:
    unrealized = Decimal(str(pos.get('unrealized_pnl_usdc', 0)))
    total_unrealized += unrealized
    print(f"  Token {pos.get('nft_token_id')}: Unrealized PnL = {unrealized} USDC")

print(f"\nTotal Unrealized PnL: {total_unrealized} USDC")

# Get current wallet balance
response = requests.get(f"{API_URL}/api/v1/users/{USER_ID}", headers=headers)
user_info = response.json()
wallet_balance = Decimal(str(user_info.get('usdc_balance', 0)))

print(f"\n## Current State:")
print(f"Wallet Balance: {wallet_balance} USDC")
print(f"Net Deposits: {net_deposits} USDC")
print(f"Total Realized PnL (from closed positions): {total_realized_pnl} USDC")
print(f"Total Unrealized PnL (from active positions): {total_unrealized} USDC")

# Calculate what PnL should be
print(f"\n## Correct PnL Calculation:")
print(f"Based on the formula in the code:")
print(f"  - Realized PnL should be: (withdrawals - deposits) if withdrawals > deposits, else 0")
print(f"  - Current formula gives: {max(total_withdrawals - total_deposits, Decimal(0))} USDC")
print(f"\nBut the user expects:")
print(f"  - Realized: ~2.11 USDC (based on closed positions)")
print(f"  - Unrealized: ~0.24 USDC (based on active positions)")

print(f"\n## The Issue:")
print("The system shows total_deposits=0 and total_withdrawals=0 in the user info,")
print("which causes the PnL calculation to be incorrect.")
print("\nThe get_deposit_withdrawal_totals method is not finding the transactions")
print("because it's filtering by user wallet address, but the user_id in the database")
print("is the EOA address (0xC2952...) while deposits come from that address to the CDP wallet.")