#!/usr/bin/env python3
"""
Trace the exact source of the NFT mint.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


def trace_nft():
    """Trace NFT source."""
    
    rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    tx_hash = '0x6760b89cbe37d7441dd49de1e1239f9362f0f9741c024f0ac93dec4b7bc46d00'
    
    print("TRACING NFT SOURCE")
    print("="*60)
    
    try:
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        
        # Check for ERC721 Transfer events
        ERC721_TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
        
        print(f"\nChecking all ERC721 Transfer events:")
        
        for i, log in enumerate(receipt.logs):
            if len(log.topics) > 0 and log.topics[0].hex() == ERC721_TRANSFER:
                contract_address = log.address.lower()
                
                if len(log.topics) >= 4:
                    from_addr = '0x' + log.topics[1].hex()[-40:]
                    to_addr = '0x' + log.topics[2].hex()[-40:]
                    token_id = int(log.topics[3].hex(), 16)
                    
                    print(f"\n#{i}: ERC721 Transfer")
                    print(f"   Contract: {contract_address}")
                    print(f"   From: {from_addr}")
                    print(f"   To: {to_addr}")
                    print(f"   Token ID: {token_id}")
                    
                    # Check what contract this is
                    if contract_address == "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1".lower():
                        print(f"   ✅ This is from NFT Position Manager!")
                    elif contract_address == "0x827922686190790b37229fd06084350e74485b72".lower():
                        print(f"   ✅ This is from WETH/USDC Gauge!")
                    elif contract_address == "0xBeb749B7F1149b75E79C1d818Ad3587060A3805D".lower():
                        print(f"   ✅ This is from Liquidity Manager!")
                    else:
                        print(f"   ❓ Unknown contract")
                    
                    if from_addr == '0x' + '0' * 40:
                        print(f"   🎨 This is a MINT!")
        
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    trace_nft()
