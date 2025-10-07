#!/usr/bin/env python3
"""
Analyze why position creation transaction is missing.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3
import json

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


def analyze_transaction():
    """Analyze the transaction that created position 26256789."""

    rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')
    w3 = Web3(Web3.HTTPProvider(rpc_url))

    tx_hash = '0x6760b89cbe37d7441dd49de1e1239f9362f0f9741c024f0ac93dec4b7bc46d00'
    position_id = 26256789

    print(f"\n{'='*60}")
    print(f"ANALYZING POSITION CREATION TRANSACTION")
    print(f"{'='*60}")
    print(f"TX Hash: {tx_hash}")
    print(f"Position ID: {position_id}")

    try:
        # Get transaction details
        tx = w3.eth.get_transaction(tx_hash)
        receipt = w3.eth.get_transaction_receipt(tx_hash)

        print(f"\n📊 Transaction Details:")
        print(f"   From: {tx['from']}")
        print(f"   To: {tx['to']}")
        print(f"   Value: {w3.from_wei(tx['value'], 'ether')} ETH")
        print(f"   Gas Used: {receipt['gasUsed']}")
        print(f"   Status: {'Success' if receipt['status'] == 1 else 'Failed'}")
        print(f"   Logs: {len(receipt.logs)}")

        # Check for USDC transfers
        USDC_ADDRESS = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'
        ERC20_TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'

        usdc_in = 0
        usdc_out = 0

        print(f"\n💰 USDC Transfers:")
        for log in receipt.logs:
            if log.address.lower() == USDC_ADDRESS.lower():
                if len(log.topics) > 0 and log.topics[0].hex() == ERC20_TRANSFER:
                    from_addr = '0x' + log.topics[1].hex()[-40:]
                    to_addr = '0x' + log.topics[2].hex()[-40:]
                    amount = int(log.data.hex(), 16) / 1e6  # Convert to USDC

                    print(f"   From {from_addr[:10]}... to {to_addr[:10]}...: {amount:.2f} USDC")

                    # Track flows relative to tx sender
                    if from_addr.lower() == tx['from'].lower():
                        usdc_out += amount
                    elif to_addr.lower() == tx['from'].lower():
                        usdc_in += amount

        net_usdc = usdc_out - usdc_in
        print(f"\n   Net USDC flow: OUT {usdc_out:.2f} - IN {usdc_in:.2f} = {net_usdc:.2f} USDC")

        # Check for NFT mint
        NFT_POSITION_MANAGER = '0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1'
        ERC721_TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'

        print(f"\n🎨 NFT Events:")
        nft_found = False
        for log in receipt.logs:
            if log.address.lower() == NFT_POSITION_MANAGER.lower():
                if len(log.topics) > 0 and log.topics[0].hex() == ERC721_TRANSFER:
                    if len(log.topics) >= 4:
                        from_addr = '0x' + log.topics[1].hex()[-40:]
                        to_addr = '0x' + log.topics[2].hex()[-40:]
                        token_id = int(log.topics[3].hex(), 16)

                        if from_addr == '0x' + '0' * 40:  # Mint event
                            print(f"   ✅ NFT #{token_id} minted to {to_addr}")
                            nft_found = True
                            if token_id == position_id:
                                print(f"   🎯 This matches our position ID!")

        if not nft_found:
            print(f"   ❌ No NFT mint event found")

        # Analyze why it might have been skipped
        print(f"\n⚠️ Possible reasons for missing POSITION_CREATED:")
        if net_usdc <= 0:
            print(f"   1. Net USDC amount is {net_usdc:.2f} (zero or negative)")
            print(f"      The code skips position creation with zero/negative amounts")
        if not nft_found:
            print(f"   2. No NFT mint event detected")
            print(f"      The code requires an NFT token ID")

        # Check method signature
        if len(tx.input) >= 10:
            method_sig = tx.input[:10]
            print(f"\n🔧 Method signature: {method_sig}")
            if method_sig == '0x3a1e3569':
                print(f"   ✅ This is openPosition (0x3a1e3569)")
            else:
                print(f"   ❓ Unknown method signature")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    analyze_transaction()