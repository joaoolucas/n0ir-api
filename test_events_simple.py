#!/usr/bin/env python3
"""Test simplified queries on base.events table."""

import httpx
import json

CDP_API_KEY = "PgSu2QFE67b4koEsqfe6yp831l7KCKgH"
CDP_BASE_URL = "https://api.cdp.coinbase.com/platform/v2"
WALLET = "0x7b3106f56447c9c313c19f519b290ff4e293d573"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"

def execute_query(sql: str, test_name: str):
    """Execute a SQL query against CDP API."""
    print(f"\n{'='*60}")
    print(f"Test: {test_name}")
    print(f"{'='*60}")
    
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
                    # Print first result in detail
                    if result['result']:
                        print("\nFirst result:")
                        for k, v in result['result'][0].items():
                            if k == 'topics' and isinstance(v, list):
                                print(f"  {k}:")
                                for i, topic in enumerate(v):
                                    print(f"    [{i}]: {topic}")
                            else:
                                print(f"  {k}: {str(v)[:100]}...")
                else:
                    print("✗ No results found")
                return result
            else:
                print(f"✗ Error: {response.text[:500]}")
                return None
                
    except Exception as e:
        print(f"✗ Request failed: {e}")
        return None

# Test 1: Get any Transfer events from USDC
sql1 = f"""
SELECT 
    transaction_hash,
    topics
FROM base.events
WHERE address = '{USDC.lower()}'
LIMIT 3
"""
result1 = execute_query(sql1, "Get any events from USDC contract")

# Test 2: Get Transfer events with event_signature
sql2 = f"""
SELECT 
    transaction_hash,
    topics,
    data
FROM base.events
WHERE address = '{USDC.lower()}'
    AND event_signature = 'Transfer(address,address,uint256)'
LIMIT 3
"""
result2 = execute_query(sql2, "Get Transfer events from USDC")

# If we got results, let's analyze the topics structure
if result2 and result2.get('result') and len(result2['result']) > 0:
    print("\n" + "="*60)
    print("Analyzing topic structure for wallet matching")
    print("="*60)
    
    wallet_lower = WALLET.lower()
    wallet_no_prefix = wallet_lower[2:]  # Remove 0x
    
    for i, event in enumerate(result2['result'][:2]):
        print(f"\nEvent {i+1}:")
        topics = event.get('topics', [])
        if len(topics) >= 3:
            # Topic[0] is event signature hash
            # Topic[1] is from address (padded to 32 bytes)
            # Topic[2] is to address (padded to 32 bytes)
            from_topic = topics[1] if len(topics) > 1 else ""
            to_topic = topics[2] if len(topics) > 2 else ""
            
            print(f"  From topic: {from_topic}")
            print(f"  To topic: {to_topic}")
            
            # Check different extraction methods
            if from_topic:
                print(f"    - Last 40 chars: 0x{from_topic[-40:]}")
                print(f"    - After 0x000....: {from_topic[26:] if len(from_topic) >= 66 else 'N/A'}")
            
            print(f"  Looking for wallet: {wallet_lower}")
            print(f"  Wallet without 0x: {wallet_no_prefix}")

# Test 3: Try matching with last 40 characters
wallet_no_prefix = WALLET.lower()[2:]  # Define it here
sql3 = f"""
SELECT 
    transaction_hash,
    topics[1] as topic1,
    topics[2] as topic2
FROM base.events
WHERE address = '{USDC.lower()}'
    AND event_signature = 'Transfer(address,address,uint256)'
    AND (topics[1] LIKE '%{wallet_no_prefix}' 
         OR topics[2] LIKE '%{wallet_no_prefix}')
LIMIT 5
"""
result3 = execute_query(sql3, "Match wallet in topics using LIKE")

# Test 4: Try with substring
sql4 = f"""
SELECT 
    transaction_hash,
    SUBSTRING(topics[1], 27) as from_addr,
    SUBSTRING(topics[2], 27) as to_addr
FROM base.events
WHERE address = '{USDC.lower()}'
    AND event_signature = 'Transfer(address,address,uint256)'
LIMIT 3
"""
result4 = execute_query(sql4, "Extract addresses using SUBSTRING")

# Test 5: Count USDC transfers in general
sql5 = f"""
SELECT COUNT(*) as total_transfers
FROM base.events
WHERE address = '{USDC.lower()}'
    AND event_signature = 'Transfer(address,address,uint256)'
"""
result5 = execute_query(sql5, "Count total USDC transfers")