#!/usr/bin/env python3
"""
Find the close event.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


def find_event():
    """Find close event."""
    
    rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    tx_hash = '0xdc1d362097733e8f59bbb3543673501b37ad35d6afccb261c269b490ab9fd4d2'
    
    print("FINDING CLOSE EVENT")
    print("="*60)
    
    try:
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        
        LIQUIDITY_MANAGER = '0xBeb749B7F1149b75E79C1d818Ad3587060A3805D'.lower()
        
        print(f"Liquidity Manager: {LIQUIDITY_MANAGER}")
        print(f"\nAll events from Liquidity Manager:")
        
        for i, log in enumerate(receipt.logs):
            if log.address.lower() == LIQUIDITY_MANAGER:
                if log.topics:
                    event_sig = log.topics[0].hex() if hasattr(log.topics[0], 'hex') else str(log.topics[0])
                    print(f"\nLog #{i}:")
                    print(f"  Event signature: {event_sig}")
                    print(f"  Topics count: {len(log.topics)}")
                    
                    # Try to decode topics
                    for j, topic in enumerate(log.topics[1:], 1):
                        topic_hex = topic.hex() if hasattr(topic, 'hex') else str(topic)
                        print(f"  Topic {j}: {topic_hex}")
                        
                        # Try to decode as address or number
                        if len(topic_hex) == 64:
                            # Could be address (last 40 chars) or number
                            addr = '0x' + topic_hex[-40:]
                            num = int(topic_hex, 16)
                            print(f"    As address: {addr}")
                            print(f"    As number: {num}")
                            
                            # Check if it's a known position ID
                            if num == 26256789:
                                print(f"    ✅ This is position 26256789!")
                    
                    # Check data field
                    if log.data:
                        print(f"  Data length: {len(log.data)} bytes")
        
        # Also check NFT Position Manager for any events
        NFT_MANAGER = '0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1'.lower()
        print(f"\n\nEvents from NFT Position Manager ({NFT_MANAGER}):")
        
        found_nft_event = False
        for i, log in enumerate(receipt.logs):
            if log.address.lower() == NFT_MANAGER:
                found_nft_event = True
                if log.topics:
                    event_sig = log.topics[0].hex() if hasattr(log.topics[0], 'hex') else str(log.topics[0])
                    print(f"\nLog #{i}: Event signature: {event_sig[:10]}...")
        
        if not found_nft_event:
            print("  No events from NFT Position Manager")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    find_event()
