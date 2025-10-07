#!/usr/bin/env python3
"""
Check all contracts involved in the transaction.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


def check_contracts():
    """Check contracts."""
    
    rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    tx_hash = '0x6760b89cbe37d7441dd49de1e1239f9362f0f9741c024f0ac93dec4b7bc46d00'
    
    print("CHECKING TRANSACTION CONTRACTS")
    print("="*60)
    
    try:
        tx = w3.eth.get_transaction(tx_hash)
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        
        print(f"\nTransaction:")
        print(f"   From: {tx['from']}")
        print(f"   To: {tx['to']}")
        
        # Check what the 'to' address is
        to_addr = tx['to'].lower()
        print(f"\nTo Address Analysis:")
        if to_addr == "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1".lower():
            print(f"   ✅ NFT Position Manager")
        elif to_addr == "0x827922686190790b37229fd06084350e74485b72".lower():
            print(f"   ✅ WETH/USDC Gauge")
        elif to_addr == "0xBeb749B7F1149b75E79C1d818Ad3587060A3805D".lower():
            print(f"   ✅ Liquidity Manager")
        else:
            print(f"   ❓ Unknown: {to_addr}")
        
        print(f"\nAll unique log addresses:")
        log_addresses = set()
        for log in receipt.logs:
            log_addresses.add(log.address.lower())
        
        for addr in sorted(log_addresses):
            if addr == "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1".lower():
                print(f"   {addr} - NFT Position Manager")
            elif addr == "0x827922686190790b37229fd06084350e74485b72".lower():
                print(f"   {addr} - WETH/USDC Gauge")
            elif addr == "0xBeb749B7F1149b75E79C1d818Ad3587060A3805D".lower():
                print(f"   {addr} - Liquidity Manager")
            elif addr == "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913".lower():
                print(f"   {addr} - USDC")
            elif addr == "0x4200000000000000000000000000000000000006".lower():
                print(f"   {addr} - WETH")
            else:
                print(f"   {addr}")
        
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    check_contracts()
