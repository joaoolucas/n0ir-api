#!/usr/bin/env python3
"""Test script to check user PnL data from the API."""

import requests
import json
from decimal import Decimal

# Configuration
API_URL = "https://n0ir-api-production.up.railway.app"
BEARER_TOKEN = "5RRJ8kHdu5M6HL91hY5bUI0abWtbANwjqVKtmjq4BMk="
USER_ID = "0xC2952cc28EDf37B053188D89e6ac888B9855d132"

headers = {
    "Authorization": f"Bearer {BEARER_TOKEN}",
    "Content-Type": "application/json"
}

def get_user_pnl():
    """Get user PnL from the API."""
    response = requests.get(f"{API_URL}/api/v1/users/{USER_ID}/pnl", headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error getting PnL: {response.status_code} - {response.text}")
        return None

def get_user_transactions():
    """Get user transactions from the API."""
    response = requests.get(f"{API_URL}/api/v1/users/{USER_ID}/transactions", headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error getting transactions: {response.status_code} - {response.text}")
        return None

def get_user_positions():
    """Get user positions from the API."""
    response = requests.get(f"{API_URL}/api/v1/users/{USER_ID}/positions", headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error getting positions: {response.status_code} - {response.text}")
        return None

def get_user_info():
    """Get user info from the API."""
    response = requests.get(f"{API_URL}/api/v1/users/{USER_ID}", headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error getting user info: {response.status_code} - {response.text}")
        return None

def main():
    print(f"Checking PnL for user: {USER_ID}")
    print("=" * 80)
    
    # Get user info
    user_info = get_user_info()
    if user_info:
        print("\n## User Info:")
        print(f"- CDP Wallet: {user_info.get('cdp_wallet_address', 'N/A')}")
        print(f"- Balance: {user_info.get('usdc_balance', 0)} USDC")
        print(f"- Total Deposits: {user_info.get('total_deposits_usdc', 0)} USDC")
        print(f"- Total Withdrawals: {user_info.get('total_withdrawals_usdc', 0)} USDC")
        print(f"- Net Deposits: {Decimal(str(user_info.get('total_deposits_usdc', 0))) - Decimal(str(user_info.get('total_withdrawals_usdc', 0)))} USDC")
    
    # Get PnL
    pnl = get_user_pnl()
    if pnl:
        print("\n## Current PnL:")
        print(json.dumps(pnl, indent=2))
    
    # Get transactions
    transactions = get_user_transactions()
    if transactions:
        print(f"\n## Transactions ({len(transactions)} total):")
        
        # Initialize lists
        deposits = []
        withdrawals = []
        position_created = []
        position_closed = []
        
        # Handle case where transactions might be a list of strings or objects
        if transactions and isinstance(transactions[0], str):
            print("  Transaction IDs:", transactions[:5])
        else:
            # Categorize transactions
            for tx in transactions:
                if isinstance(tx, dict):
                    tx_type = tx.get('tx_type', '')
                    if tx_type == 'DEPOSIT':
                        deposits.append(tx)
                    elif tx_type in ['WITHDRAWAL', 'WITHDRAW']:
                        withdrawals.append(tx)
                    elif tx_type == 'POSITION_CREATED':
                        position_created.append(tx)
                    elif tx_type == 'POSITION_CLOSED':
                        position_closed.append(tx)
        
        print(f"- Deposits: {len(deposits)}")
        if deposits:
            total_deposits = sum(Decimal(str(tx.get('amount_usdc', 0))) for tx in deposits)
            print(f"  Total: {total_deposits} USDC")
            for tx in deposits[:3]:  # Show first 3
                print(f"  - {tx.get('amount_usdc', 0)} USDC on {tx.get('created_at', 'N/A')}")
        
        print(f"- Withdrawals: {len(withdrawals)}")
        if withdrawals:
            total_withdrawals = sum(Decimal(str(tx.get('amount_usdc', 0))) for tx in withdrawals)
            print(f"  Total: {total_withdrawals} USDC")
            for tx in withdrawals[:3]:  # Show first 3
                print(f"  - {tx.get('amount_usdc', 0)} USDC on {tx.get('created_at', 'N/A')}")
        
        print(f"- Positions Created: {len(position_created)}")
        print(f"- Positions Closed: {len(position_closed)}")
        if position_closed:
            for tx in position_closed[:5]:  # Show first 5
                metadata = tx.get('tx_metadata', {})
                realized_pnl = metadata.get('realized_pnl_usdc', 'N/A')
                print(f"  - Token ID {metadata.get('nft_token_id', 'N/A')}: Realized PnL = {realized_pnl} USDC")
    
    # Get positions
    positions = get_user_positions()
    if positions:
        print(f"\n## Positions ({len(positions)} total):")
        
        active_positions = [p for p in positions if p.get('status') == 'ACTIVE']
        closed_positions = [p for p in positions if p.get('status') == 'CLOSED']
        
        print(f"- Active: {len(active_positions)}")
        if active_positions:
            total_unrealized = sum(Decimal(str(p.get('unrealized_pnl_usdc', 0))) for p in active_positions)
            print(f"  Total Unrealized PnL: {total_unrealized} USDC")
            for pos in active_positions[:3]:  # Show first 3
                print(f"  - Token {pos.get('nft_token_id')}: Unrealized = {pos.get('unrealized_pnl_usdc', 0)} USDC")
        
        print(f"- Closed: {len(closed_positions)}")
        if closed_positions:
            total_realized_from_positions = sum(Decimal(str(p.get('realized_pnl_usdc', 0))) for p in closed_positions)
            print(f"  Total Realized PnL from closed positions: {total_realized_from_positions} USDC")
            for pos in closed_positions[:3]:  # Show first 3
                print(f"  - Token {pos.get('nft_token_id')}: Realized = {pos.get('realized_pnl_usdc', 0)} USDC")
    
    print("\n" + "=" * 80)
    print("\n## Analysis:")
    
    if user_info and pnl:
        deposits = Decimal(str(user_info.get('total_deposits_usdc', 0)))
        withdrawals = Decimal(str(user_info.get('total_withdrawals_usdc', 0)))
        net_deposits = deposits - withdrawals
        
        print(f"Net Deposits: {net_deposits} USDC")
        print(f"Current PnL shows:")
        print(f"  - Realized: {pnl.get('realized_pnl_usdc', 0)} USDC")
        print(f"  - Unrealized: {pnl.get('unrealized_pnl_usdc', 0)} USDC")
        
        if withdrawals == 0:
            print("\n⚠️  Issue identified: User has no withdrawals, so realized PnL should be 0")
            print("   The system correctly shows realized PnL as 0")
            print("   All profit is shown as unrealized until withdrawals occur")
        
        if positions and closed_positions:
            total_realized_from_positions = sum(Decimal(str(p.get('realized_pnl_usdc', 0))) for p in closed_positions)
            print(f"\n   However, closed positions show realized PnL of {total_realized_from_positions} USDC")
            print("   This suggests the PnL calculation logic needs adjustment")

if __name__ == "__main__":
    main()