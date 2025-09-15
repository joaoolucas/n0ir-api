#!/usr/bin/env python3
"""Simple test to get USDC transfers from CDP SQL API."""

import httpx
import json

CDP_API_KEY = "PgSu2QFE67b4koEsqfe6yp831l7KCKgH"
CDP_BASE_URL = "https://api.cdp.coinbase.com/platform/v2"
WALLET = "0x7b3106f56447c9c313c19f519b290ff4e293d573"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"

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
            
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                return result
            else:
                print(f"Error: {response.text[:500]}")
                return None
                
    except Exception as e:
        print(f"Request failed: {e}")
        return None

# Test 1: Simple events query without complex filtering
print("Test 1: Get recent USDC Transfer events")
sql1 = f"""
SELECT 
    transaction_hash,
    block_number,
    timestamp,
    topics,
    data
FROM base.events
WHERE address = LOWER('{USDC}')
    AND event_signature = 'Transfer(address,address,uint256)'
ORDER BY timestamp DESC
LIMIT 5
"""

result1 = execute_query(sql1)
if result1 and result1.get('result'):
    print(f"Found {len(result1['result'])} events")
    for row in result1['result'][:2]:
        print(f"\nTX: {row['transaction_hash']}")
        print(f"Topics: {row['topics']}")

# Test 2: Find events for specific wallet using simple substring match
print("\n\nTest 2: Find USDC transfers for wallet using LIKE")
wallet_suffix = WALLET[2:].lower()  # Remove 0x and lowercase
sql2 = f"""
SELECT 
    transaction_hash,
    block_number,
    timestamp,
    topics
FROM base.events
WHERE address = LOWER('{USDC}')
    AND event_signature = 'Transfer(address,address,uint256)'
    AND (
        topics[2] LIKE '%{wallet_suffix}%'
        OR topics[3] LIKE '%{wallet_suffix}%'
    )
ORDER BY timestamp DESC
LIMIT 10
"""

result2 = execute_query(sql2)
if result2 and result2.get('result'):
    print(f"Found {len(result2['result'])} transfers for wallet")
    for row in result2['result'][:3]:
        print(f"\nTX: {row['transaction_hash']}")
        print(f"Topics[2]: {row['topics'][1] if len(row['topics']) > 1 else 'N/A'}")
        print(f"Topics[3]: {row['topics'][2] if len(row['topics']) > 2 else 'N/A'}")

# Test 3: Try with substring function
print("\n\nTest 3: Using SUBSTRING to extract addresses")
sql3 = f"""
SELECT 
    transaction_hash,
    SUBSTRING(topics[2], 27, 40) as from_addr,
    SUBSTRING(topics[3], 27, 40) as to_addr
FROM base.events
WHERE address = LOWER('{USDC}')
    AND event_signature = 'Transfer(address,address,uint256)'
    AND timestamp > '2024-12-01'
LIMIT 5
"""

result3 = execute_query(sql3)
if result3 and result3.get('result'):
    print(f"Found {len(result3['result'])} events with extracted addresses")
    for row in result3['result'][:2]:
        print(f"\nTX: {row['transaction_hash']}")
        print(f"From: 0x{row['from_addr']}")
        print(f"To: 0x{row['to_addr']}")

# Test 4: Get ETH transactions for the wallet
print("\n\nTest 4: Get ETH transactions for wallet")
sql4 = f"""
SELECT 
    transaction_hash,
    block_number,
    timestamp,
    from_address,
    to_address,
    value
FROM base.transactions
WHERE LOWER(from_address) = LOWER('{WALLET}')
    OR LOWER(to_address) = LOWER('{WALLET}')
ORDER BY timestamp DESC
LIMIT 5
"""

result4 = execute_query(sql4)
if result4 and result4.get('result'):
    print(f"Found {len(result4['result'])} ETH transactions")
    for row in result4['result']:
        print(f"\nTX: {row['transaction_hash']}")
        print(f"From: {row['from_address']}")
        print(f"To: {row['to_address']}")
        print(f"Value: {row['value']}")
else:
    print("No ETH transactions found")