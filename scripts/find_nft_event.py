#!/usr/bin/env python3
"""
Find the NFT mint event more carefully.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


def find_nft():
    """Find NFT event."""
    
    rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    tx_hash = '0x6760b89cbe37d7441dd49de1e1239f9362f0f9741c024f0ac93dec4b7bc46d00'
    cdp_wallet = '0x680214379083fa0d66d1EC030A045beEFB8Ec43f'.lower()
    
    print("SEARCHING FOR NFT EVENTS")
    print("="*60)
    
    try:
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        
        # Look for ALL Transfer events (ERC20 and ERC721 have same signature)
        TRANSFER_EVENT = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
        
        print(f"\nAll Transfer events:")
        
        for i, log in enumerate(receipt.logs):
            if len(log.topics) > 0 and log.topics[0].hex() == TRANSFER_EVENT:
                contract_address = log.address.lower()
                
                # ERC721 has 3 topics (event, from, to, tokenId)
                # ERC20 has 2 topics (event, from, to) and amount in data
                if len(log.topics) == 4:
                    # This looks like ERC721
                    from_addr = '0x' + log.topics[1].hex()[-40:].lower()
                    to_addr = '0x' + log.topics[2].hex()[-40:].lower()
                    token_id = int(log.topics[3].hex(), 16)
                    
                    print(f"\n#{i}: ERC721 Transfer")
                    print(f"   Contract: {contract_address}")
                    
                    # Identify the contract
                    if contract_address == "0xbeb749b7f1149b75e79c1d818ad3587060a3805d":
                        print(f"   ✅ FROM LIQUIDITY MANAGER!")
                    elif contract_address == "0x827922686190790b37229fd06084350e74485b72":
                        print(f"   ✅ FROM GAUGE!")
                    
                    print(f"   From: {from_addr}")
                    print(f"   To: {to_addr}")
                    print(f"   Token ID: {token_id}")
                    
                    if from_addr == '0x' + '0' * 40:
                        print(f"   🎨 MINT!")
                    
                    if to_addr == cdp_wallet:
                        print(f"   🎯 TO CDP WALLET!")
        
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    find_nft()
