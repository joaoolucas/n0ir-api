#!/usr/bin/env python3
"""Test script to query USDC transfers directly from CDP SQL API."""

import httpx
import json
from datetime import datetime, timedelta

# CDP API configuration
CDP_API_KEY = "PgSu2QFE67b4koEsqfe6yp831l7KCKgH"
CDP_BASE_URL = "https://api.cdp.coinbase.com/platform/v2"
WALLET_ADDRESS = "0x7b3106f56447c9c313c19f519b290ff4e293d573"
USDC_ADDRESS = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"  # USDC on Base

def execute_query(sql: str):
    """Execute a SQL query against CDP API."""
    headers = {
        "Authorization": f"Bearer {CDP_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {"sql": sql}
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{CDP_BASE_URL}/data/query/run",
                headers=headers,
                json=payload
            )
            
            print(f"Response Status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                return result
            else:
                print(f"Error: {response.text}")
                return None
                
    except Exception as e:
        print(f"Request failed: {e}")
        return None

def test_usdc_transfers():
    """Test different queries to find USDC transfers."""
    
    print("=" * 80)
    print("Testing USDC Transfer Queries for wallet:", WALLET_ADDRESS)
    print("=" * 80)
    
    # Query 1: Direct events query with proper address formatting
    print("\n1. Testing direct Transfer events query...")
    sql1 = f"""
    SELECT 
        transaction_hash,
        block_number,
        timestamp,
        topics,
        data,
        address as contract_address
    FROM base.events
    WHERE address = LOWER('{USDC_ADDRESS}')
        AND event_signature = 'Transfer(address,address,uint256)'
        AND (
            topics[2] LIKE '%{WALLET_ADDRESS[2:].lower()}%'
            OR topics[3] LIKE '%{WALLET_ADDRESS[2:].lower()}%'
        )
    ORDER BY timestamp DESC
    LIMIT 10
    """
    
    result1 = execute_query(sql1)
    if result1 and result1.get('result'):
        print(f"Found {len(result1['result'])} Transfer events")
        for i, row in enumerate(result1['result'][:3]):
            print(f"\nEvent {i+1}:")
            print(f"  TX Hash: {row.get('transaction_hash')}")
            print(f"  Block: {row.get('block_number')}")
            print(f"  Timestamp: {row.get('timestamp')}")
            print(f"  Topics: {row.get('topics')}")
            print(f"  Data: {row.get('data')[:66] if row.get('data') else 'None'}...")
    else:
        print("No Transfer events found")
    
    # Query 2: Try with RIGHT() function for exact matching
    print("\n2. Testing with RIGHT() function for address extraction...")
    sql2 = f"""
    SELECT 
        transaction_hash,
        block_number,
        timestamp,
        CONCAT('0x', RIGHT(topics[2], 40)) as from_address,
        CONCAT('0x', RIGHT(topics[3], 40)) as to_address,
        data as value
    FROM base.events
    WHERE address = LOWER('{USDC_ADDRESS}')
        AND event_signature = 'Transfer(address,address,uint256)'
        AND (
            RIGHT(LOWER(topics[2]), 40) = '{WALLET_ADDRESS[2:].lower()}'
            OR RIGHT(LOWER(topics[3]), 40) = '{WALLET_ADDRESS[2:].lower()}'
        )
    ORDER BY timestamp DESC
    LIMIT 10
    """
    
    result2 = execute_query(sql2)
    if result2 and result2.get('result'):
        print(f"Found {len(result2['result'])} transfers with RIGHT() matching")
        for i, row in enumerate(result2['result'][:3]):
            print(f"\nTransfer {i+1}:")
            print(f"  TX Hash: {row.get('transaction_hash')}")
            print(f"  From: {row.get('from_address')}")
            print(f"  To: {row.get('to_address')}")
            print(f"  Value: {row.get('value')}")
    else:
        print("No transfers found with RIGHT() matching")
    
    # Query 3: Simple query without address filtering to verify USDC events exist
    print("\n3. Testing if USDC Transfer events exist at all...")
    sql3 = f"""
    SELECT 
        COUNT(*) as total_transfers
    FROM base.events
    WHERE address = LOWER('{USDC_ADDRESS}')
        AND event_signature = 'Transfer(address,address,uint256)'
        AND timestamp >= '2024-01-01'
    """
    
    result3 = execute_query(sql3)
    if result3 and result3.get('result'):
        print(f"Total USDC transfers since 2024: {result3['result'][0].get('total_transfers')}")
    
    # Query 4: Check recent transactions for the wallet
    print("\n4. Checking recent ETH transactions for wallet...")
    sql4 = f"""
    SELECT 
        transaction_hash,
        block_number,
        timestamp,
        from_address,
        to_address,
        value,
        gas
    FROM base.transactions
    WHERE (from_address = LOWER('{WALLET_ADDRESS}') OR to_address = LOWER('{WALLET_ADDRESS}'))
    ORDER BY timestamp DESC
    LIMIT 5
    """
    
    result4 = execute_query(sql4)
    if result4 and result4.get('result'):
        print(f"Found {len(result4['result'])} ETH transactions")
        for i, row in enumerate(result4['result']):
            print(f"\nTransaction {i+1}:")
            print(f"  TX Hash: {row.get('transaction_hash')}")
            print(f"  From: {row.get('from_address')}")
            print(f"  To: {row.get('to_address')}")
            print(f"  Timestamp: {row.get('timestamp')}")
    else:
        print("No ETH transactions found")
    
    # Query 5: Try searching in a specific time range
    print("\n5. Testing USDC transfers in last 30 days...")
    start_date = (datetime.now() - timedelta(days=30)).isoformat()
    sql5 = f"""
    SELECT 
        transaction_hash,
        block_number,
        timestamp,
        topics[2] as from_topic,
        topics[3] as to_topic
    FROM base.events
    WHERE address = LOWER('{USDC_ADDRESS}')
        AND event_signature = 'Transfer(address,address,uint256)'
        AND timestamp >= '{start_date}'
        AND (
            LOWER(topics[2]) LIKE '%{WALLET_ADDRESS[2:].lower()}%'
            OR LOWER(topics[3]) LIKE '%{WALLET_ADDRESS[2:].lower()}%'
        )
    ORDER BY timestamp DESC
    LIMIT 5
    """
    
    result5 = execute_query(sql5)
    if result5 and result5.get('result'):
        print(f"Found {len(result5['result'])} recent USDC transfers")
        for row in result5['result']:
            print(f"\nTX: {row.get('transaction_hash')}")
            print(f"  From topic: {row.get('from_topic')}")
            print(f"  To topic: {row.get('to_topic')}")
    else:
        print("No recent USDC transfers found")

if __name__ == "__main__":
    test_usdc_transfers()