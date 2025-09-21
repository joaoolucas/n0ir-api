#!/usr/bin/env python3
"""
Test why RPC parsing is not working.
"""

import asyncio
from web3 import Web3
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')

async def test_parsing():
    """Test RPC log parsing."""
    
    rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    tx_hash = '0x6760b89cbe37d7441dd49de1e1239f9362f0f9741c024f0ac93dec4b7bc46d00'
    LIQUIDITY_MANAGER = '0xBeb749B7F1149b75E79C1d818Ad3587060A3805D'.lower()
    
    print("TESTING RPC LOG PARSING")
    print("="*60)
    
    # Simulate what the code does
    position_event = None  # Start with no position event
    
    if not position_event and tx_hash:
        print(f"✓ Condition met: position_event={position_event}, tx_hash exists")
        
        # Fetch logs
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        rpc_logs = []
        for log in receipt.logs:
            rpc_logs.append({
                "address": log.address.lower(),
                "topics": [topic.hex() if hasattr(topic, 'hex') else str(topic) for topic in log.topics],
                "data": log.data.hex() if hasattr(log.data, 'hex') else log.data
            })
        
        print(f"✓ Fetched {len(rpc_logs)} logs")
        
        # This should execute
        liquidity_manager_lower = LIQUIDITY_MANAGER
        print(f"✓ Looking for events from: {liquidity_manager_lower}")
        
        found_event = False
        for i, log in enumerate(rpc_logs):
            if not log.get("topics"):
                continue
                
            event_sig = log["topics"][0].lower() if log["topics"] else None
            log_address = log["address"].lower()
            
            if log_address == liquidity_manager_lower:
                print(f"  Log #{i} from LM: sig={event_sig[:10]}...")
                
            if event_sig == "0x8d53117d19441d0a7f168d2728ff066eed66d078efdaf9bf249eef6e20887ae5" and log_address == liquidity_manager_lower:
                print(f"✓✓✓ FOUND PositionCreated event!")
                found_event = True
                break
        
        if not found_event:
            print(f"✗ No PositionCreated event found")
    else:
        print(f"✗ Condition not met: position_event={position_event}")

if __name__ == "__main__":
    asyncio.run(test_parsing())
