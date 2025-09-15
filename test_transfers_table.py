#!/usr/bin/env python3
"""Test querying the base.transfers table for USDC transfers."""

import httpx
import json
from datetime import datetime

CDP_API_KEY = "PgSu2QFE67b4koEsqfe6yp831l7KCKgH"
CDP_BASE_URL = "https://api.cdp.coinbase.com/platform/v2"
WALLET = "0x7b3106f56447c9c313c19f519b290ff4e293d573"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"

def execute_query(sql: str, test_name: str):
    """Execute a SQL query against CDP API."""
    print(f"\n{'='*60}")
    print(f"Test: {test_name}")
    print(f"{'='*60}")
    print(f"Query:\n{sql}\n")
    
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
                if result.get('result'):
                    print(f"✓ Found {len(result['result'])} results")
                    for i, row in enumerate(result['result'][:3]):
                        print(f"\nRow {i+1}:")
                        for k, v in row.items():
                            print(f"  {k}: {v}")
                else:
                    print("✗ No results found")
                return result
            else:
                print(f"✗ Error: {response.text[:500]}")
                return None
                
    except Exception as e:
        print(f"✗ Request failed: {e}")
        return None

# Test 1: Query base.transfers table directly
sql1 = f"""
SELECT *
FROM base.transfers
WHERE LOWER(from_address) = LOWER('{WALLET}')
   OR LOWER(to_address) = LOWER('{WALLET}')
ORDER BY timestamp DESC
LIMIT 5
"""
execute_query(sql1, "Query base.transfers for wallet")

# Test 2: Filter USDC transfers specifically
sql2 = f"""
SELECT 
    transaction_hash,
    block_number,
    timestamp,
    from_address,
    to_address,
    token_address,
    value
FROM base.transfers
WHERE (LOWER(from_address) = LOWER('{WALLET}')
   OR LOWER(to_address) = LOWER('{WALLET}'))
   AND LOWER(token_address) = LOWER('{USDC}')
ORDER BY timestamp DESC
LIMIT 5
"""
execute_query(sql2, "Query USDC transfers from base.transfers")

# Test 3: Count total transfers for wallet
sql3 = f"""
SELECT 
    COUNT(*) as total_transfers,
    COUNT(DISTINCT token_address) as unique_tokens
FROM base.transfers
WHERE LOWER(from_address) = LOWER('{WALLET}')
   OR LOWER(to_address) = LOWER('{WALLET}')
"""
execute_query(sql3, "Count total transfers for wallet")

# Test 4: Get recent transfers without LOWER function
sql4 = f"""
SELECT 
    transaction_hash,
    from_address,
    to_address,
    token_address,
    value
FROM base.transfers
WHERE from_address = '{WALLET}'
   OR to_address = '{WALLET}'
LIMIT 5
"""
execute_query(sql4, "Query transfers without LOWER function")

# Test 5: Simple test - just get any USDC transfers
sql5 = f"""
SELECT 
    transaction_hash,
    from_address,
    to_address,
    value
FROM base.transfers
WHERE token_address = '{USDC}'
ORDER BY timestamp DESC
LIMIT 5
"""
execute_query(sql5, "Get any USDC transfers (not filtered by wallet)")

print("\n" + "="*60)
print("Test Summary")
print("="*60)
print(f"Wallet: {WALLET}")
print(f"USDC: {USDC}")