#!/usr/bin/env python3
"""
Decode the gauge NFT transfer.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


def decode():
    """Decode gauge NFT."""
    
    rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    tx_hash = '0x6760b89cbe37d7441dd49de1e1239f9362f0f9741c024f0ac93dec4b7bc46d00'
    
    print("DECODING GAUGE NFT TRANSFER")
    print("="*60)
    
    try:
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        
        # Get log #15 specifically
        log = receipt.logs[15]
        
        print(f"\nLog #15 (Gauge NFT Transfer):")
        print(f"   Address: {log.address}")
        print(f"   Topics: {len(log.topics)}")
        
        if len(log.topics) == 4:
            # Decode the transfer
            from_addr = '0x' + log.topics[1].hex()[-40:]
            to_addr = '0x' + log.topics[2].hex()[-40:]
            token_id = int(log.topics[3].hex(), 16)
            
            print(f"\nDecoded Transfer:")
            print(f"   From: {from_addr}")
            print(f"   To: {to_addr}")
            print(f"   Token ID: {token_id}")
            
            if from_addr.lower() == '0x' + '0' * 40:
                print(f"\n✅ This is a MINT!")
                print(f"   NFT #{token_id} was minted by the gauge")
                print(f"   And sent to: {to_addr}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    decode()
