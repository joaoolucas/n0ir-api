#!/usr/bin/env python3
"""
Check ALL events in the transaction.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


def check_all():
    """Check all events."""
    
    rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    tx_hash = '0x6760b89cbe37d7441dd49de1e1239f9362f0f9741c024f0ac93dec4b7bc46d00'
    
    print("ALL EVENTS IN TRANSACTION")
    print("="*60)
    
    try:
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        
        print(f"\nTotal logs: {len(receipt.logs)}")
        
        for i, log in enumerate(receipt.logs):
            print(f"\nLog #{i}:")
            print(f"   Address: {log.address}")
            print(f"   Topics: {len(log.topics)}")
            if log.topics:
                print(f"   Event sig: {log.topics[0].hex()}")
                
                # Check for known events
                sig = log.topics[0].hex()
                if sig == '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef':
                    print(f"   ✅ Transfer event")
                    if len(log.topics) == 4:
                        token_id = int(log.topics[3].hex(), 16)
                        print(f"   Token ID: {token_id}")
                elif sig == '0x3067048beee31b25b2f1681f88dac838c8bba36af25bfb2b7cf7473a5847e35f':
                    print(f"   ✅ IncreaseLiquidity event")
                    if len(log.topics) > 1:
                        try:
                            token_id = int(log.topics[1].hex(), 16)
                            print(f"   Token ID: {token_id}")
                        except:
                            pass
                        
            if log.data and len(log.data) > 2:
                print(f"   Data length: {len(log.data)} bytes")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    check_all()
