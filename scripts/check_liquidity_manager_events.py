#!/usr/bin/env python3
"""
Check events from Liquidity Manager.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


def check_lm_events():
    """Check Liquidity Manager events."""
    
    rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    tx_hash = '0x6760b89cbe37d7441dd49de1e1239f9362f0f9741c024f0ac93dec4b7bc46d00'
    LIQUIDITY_MANAGER = '0xBeb749B7F1149b75E79C1d818Ad3587060A3805D'.lower()
    
    print("LIQUIDITY MANAGER EVENTS")
    print("="*60)
    
    try:
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        
        print(f"\nEvents from Liquidity Manager ({LIQUIDITY_MANAGER}):")
        
        for i, log in enumerate(receipt.logs):
            if log.address.lower() == LIQUIDITY_MANAGER:
                print(f"\nLog #{i}:")
                print(f"   Topics: {len(log.topics)}")
                if log.topics:
                    event_sig = log.topics[0].hex()
                    print(f"   Event sig: {event_sig}")
                    
                    # Try to decode known events
                    if event_sig == '0x8d53117d19441d0a7f168d2728ff066eed66d078efdaf9bf249eef6e20887ae5':
                        print(f"   ✅ This might be PositionCreated event")
                        # Decode the event data
                        if len(log.topics) == 4:
                            # Topics usually: event_sig, indexed_param1, indexed_param2, indexed_param3
                            print(f"   Topic 1: {log.topics[1].hex()}")
                            print(f"   Topic 2: {log.topics[2].hex()}")
                            print(f"   Topic 3: {log.topics[3].hex()}")
                            
                            # Try to decode as potential token ID
                            try:
                                potential_id = int(log.topics[1].hex(), 16)
                                print(f"   Potential ID in topic 1: {potential_id}")
                            except:
                                pass
                            try:
                                potential_id = int(log.topics[2].hex(), 16)
                                print(f"   Potential ID in topic 2: {potential_id}")
                            except:
                                pass
                            try:
                                potential_id = int(log.topics[3].hex(), 16)
                                print(f"   Potential ID in topic 3: {potential_id}")
                            except:
                                pass
                        
                        # Check data field
                        if log.data and len(log.data) > 2:
                            print(f"   Data length: {len(log.data)} bytes")
                            # Try to decode data as uint256 values
                            data_hex = log.data.hex() if hasattr(log.data, 'hex') else log.data
                            # Remove 0x prefix
                            data_hex = data_hex.replace('0x', '')
                            # Split into 32-byte chunks (64 hex chars)
                            chunks = [data_hex[i:i+64] for i in range(0, len(data_hex), 64)]
                            for j, chunk in enumerate(chunks):
                                if chunk:
                                    try:
                                        value = int(chunk, 16)
                                        print(f"   Data chunk {j}: {value}")
                                        if value == 26256789:
                                            print(f"   ✅ Found NFT token ID: {value}")
                                    except:
                                        pass
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    check_lm_events()
