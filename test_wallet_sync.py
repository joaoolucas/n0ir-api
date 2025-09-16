#!/usr/bin/env python3
"""Test script for wallet transaction sync functionality."""

import asyncio
import requests
import json
from datetime import datetime

# Configuration
API_BASE_URL = "http://localhost:8000/api/v1"
API_KEY = "PgSu2QFE67b4koEsqfe6yp831l7KCKgH"  # CDP API key
USER_ID = "0xdbe4e3bcb15b221324b776db6f0cbff24918ea51"  # Owner wallet
CDP_WALLET = "0x7b3106F56447c9C313C19f519b290Ff4E293D573"  # CDP wallet

# Bearer token for API authentication (if needed)
BEARER_TOKEN = "your-bearer-token-here"


def test_sync_endpoint():
    """Test the sync-wallet-transactions endpoint."""
    print("\n" + "="*80)
    print("Testing Wallet Transaction Sync Endpoint")
    print("="*80)
    
    # Endpoint URL
    url = f"{API_BASE_URL}/users/{USER_ID}/sync-wallet-transactions"
    
    # Headers
    headers = {
        "Authorization": f"Bearer {BEARER_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Query parameters
    params = {
        "api_key": API_KEY,
        "limit": 100  # Fetch up to 100 transactions
    }
    
    print(f"\n📡 Calling: POST {url}")
    print(f"User ID (Owner): {USER_ID}")
    print(f"CDP Wallet: {CDP_WALLET}")
    print(f"Limit: {params['limit']} transactions")
    
    try:
        # Make the request
        response = requests.post(url, headers=headers, params=params)
        
        print(f"\n📊 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("\n✅ Sync Successful!")
            print(json.dumps(data, indent=2))
            
            # Display summary
            print("\n" + "-"*60)
            print("SUMMARY:")
            print("-"*60)
            print(f"Transactions Synced: {data.get('transactions_synced', 0)}")
            
            breakdown = data.get('breakdown', {})
            print(f"\nBreakdown:")
            print(f"  Deposits:    {breakdown.get('deposits', 0)}")
            print(f"  Withdrawals: {breakdown.get('withdrawals', 0)}")
            print(f"  Stakings:    {breakdown.get('stakings', 0)}")
            print(f"  Unknown:     {breakdown.get('unknown', 0)}")
            
            totals = data.get('totals', {})
            print(f"\nTotals:")
            print(f"  Total Deposited:  ${totals.get('total_deposited_usdc', 0):,.2f} USDC")
            print(f"  Total Withdrawn:  ${totals.get('total_withdrawn_usdc', 0):,.2f} USDC")
            print(f"  Net Flow:         ${totals.get('net_flow_usdc', 0):,.2f} USDC")
            
        else:
            print(f"\n❌ Error: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"\n❌ Exception: {e}")


def test_get_transactions():
    """Test the get transactions endpoint with auto-sync."""
    print("\n" + "="*80)
    print("Testing Get Transactions with Auto-Sync")
    print("="*80)
    
    # Endpoint URL
    url = f"{API_BASE_URL}/users/{USER_ID}/transactions"
    
    # Headers
    headers = {
        "Authorization": f"Bearer {BEARER_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Query parameters
    params = {
        "limit": 20,
        "sync_fresh": True,  # Enable auto-sync
        "api_key": API_KEY   # Provide API key for sync
    }
    
    print(f"\n📡 Calling: GET {url}")
    print(f"User ID: {USER_ID}")
    print(f"Auto-sync: {params['sync_fresh']}")
    print(f"Limit: {params['limit']} transactions")
    
    try:
        # Make the request
        response = requests.get(url, headers=headers, params=params)
        
        print(f"\n📊 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ Found {data.get('total', 0)} transactions")
            
            # Group transactions by type
            transactions = data.get('transactions', [])
            by_type = {}
            for tx in transactions:
                tx_type = tx.get('tx_type', 'UNKNOWN')
                if tx_type not in by_type:
                    by_type[tx_type] = []
                by_type[tx_type].append(tx)
            
            # Display summary
            print("\n" + "-"*60)
            print("TRANSACTION TYPES:")
            print("-"*60)
            for tx_type, txs in by_type.items():
                print(f"\n{tx_type}: {len(txs)} transactions")
                # Show first 3 of each type
                for tx in txs[:3]:
                    amount = tx.get('amount_usdc', 0)
                    timestamp = tx.get('created_at', '')[:19]
                    tx_hash = tx.get('tx_hash', '')
                    if tx_hash:
                        tx_hash = f"{tx_hash[:10]}...{tx_hash[-6:]}"
                    print(f"  {timestamp} - ${amount:,.2f} USDC - {tx_hash}")
                if len(txs) > 3:
                    print(f"  ... and {len(txs) - 3} more")
                    
        else:
            print(f"\n❌ Error: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"\n❌ Exception: {e}")


def main():
    """Run all tests."""
    print("\n🔍 Testing Wallet Transaction Sync Integration")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    # Test sync endpoint
    test_sync_endpoint()
    
    # Wait a bit
    print("\n⏳ Waiting 2 seconds before next test...")
    import time
    time.sleep(2)
    
    # Test get transactions with auto-sync
    test_get_transactions()
    
    print("\n" + "="*80)
    print("✅ Testing Complete!")
    print("="*80)


if __name__ == "__main__":
    main()