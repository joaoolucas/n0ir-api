#!/usr/bin/env python3
"""
Decode the PositionCreated event from Liquidity Manager.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


def decode_event():
    """Decode PositionCreated event."""
    
    rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    tx_hash = '0x6760b89cbe37d7441dd49de1e1239f9362f0f9741c024f0ac93dec4b7bc46d00'
    
    print("DECODING POSITIONCREATED EVENT")
    print("="*60)
    
    try:
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        
        # Get log #19 (PositionCreated from Liquidity Manager)
        log = receipt.logs[19]
        
        print(f"\nPositionCreated Event:")
        print(f"   Contract: {log.address}")
        print(f"   Topics: {len(log.topics)}")
        
        # Decode topics (indexed parameters)
        if len(log.topics) >= 4:
            print(f"\nIndexed Parameters:")
            # Topic 0 is event signature
            # Topics 1-3 are indexed parameters
            for i in range(1, len(log.topics)):
                topic_hex = log.topics[i].hex()
                print(f"   Topic {i}: {topic_hex}")
                
                # Try to decode as address (last 40 hex chars)
                addr = '0x' + topic_hex[-40:]
                print(f"      As address: {addr}")
                
                # Try to decode as uint256
                try:
                    value = int(topic_hex, 16)
                    print(f"      As uint256: {value}")
                    if value == 26256789:
                        print(f"      ✅ This is the NFT token ID!")
                except:
                    pass
        
        # Decode data (non-indexed parameters)
        if log.data:
            data_hex = log.data.hex() if hasattr(log.data, 'hex') else log.data
            data_hex = data_hex.replace('0x', '')
            
            print(f"\nNon-indexed Parameters (data):")
            print(f"   Raw data: {data_hex}")
            
            # Split into 32-byte chunks
            chunks = [data_hex[i:i+64] for i in range(0, len(data_hex), 64)]
            for i, chunk in enumerate(chunks):
                if chunk:
                    try:
                        value = int(chunk, 16)
                        print(f"   Param {i}: {value}")
                        if value == 26256789:
                            print(f"      ✅ Found NFT token ID in data!")
                        # Check if it's a pool address pattern
                        if len(chunk) == 64 and chunk[:24] == '0' * 24:
                            addr = '0x' + chunk[24:]
                            print(f"      As address: {addr}")
                    except:
                        print(f"   Param {i}: {chunk}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    decode_event()
