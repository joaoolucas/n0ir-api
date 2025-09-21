#!/usr/bin/env python3
"""
Find NFT mint in transaction for CDP wallet.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


def find_nft_mint():
    """Find NFT mint in the transaction."""

    rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')
    w3 = Web3(Web3.HTTPProvider(rpc_url))

    tx_hash = '0x6760b89cbe37d7441dd49de1e1239f9362f0f9741c024f0ac93dec4b7bc46d00'
    user_wallet = '0xAC65e18F7f4e5eDEA297b9E5433C153f1d9a7764'
    cdp_wallet = '0x680214379083fa0d66d1EC030A045beEFB8Ec43f'  # Known CDP wallet for this user

    print(f"\n{'='*60}")
    print(f"FINDING NFT MINT FOR CDP WALLET")
    print(f"{'='*60}")
    print(f"TX Hash: {tx_hash}")
    print(f"User: {user_wallet}")
    print(f"CDP Wallet: {cdp_wallet}")

    try:
        tx = w3.eth.get_transaction(tx_hash)
        receipt = w3.eth.get_transaction_receipt(tx_hash)

        print(f"\n📊 Transaction:")
        print(f"   From: {tx['from']}")
        print(f"   To: {tx['to']}")

        # ERC721 Transfer event
        ERC721_TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'

        # Check ALL contracts, not just NFT Position Manager
        print(f"\n🔍 Checking all ERC721 Transfer events...")

        for i, log in enumerate(receipt.logs):
            if len(log.topics) > 0 and log.topics[0].hex() == ERC721_TRANSFER:
                print(f"\n📝 ERC721 Transfer in log {i}:")
                print(f"   Contract: {log.address}")

                if len(log.topics) >= 4:
                    from_addr = '0x' + log.topics[1].hex()[-40:]
                    to_addr = '0x' + log.topics[2].hex()[-40:]
                    token_id = int(log.topics[3].hex(), 16)

                    print(f"   From: {from_addr}")
                    print(f"   To: {to_addr}")
                    print(f"   Token ID: {token_id}")

                    # Check if this is a mint to CDP wallet
                    if from_addr == '0x' + '0' * 40:  # Mint (from 0x0)
                        print(f"   ✅ This is a MINT!")
                        if to_addr.lower() == cdp_wallet.lower():
                            print(f"   🎯 FOUND IT! NFT #{token_id} minted to CDP wallet!")
                            return token_id, log.address
                        else:
                            print(f"   Minted to: {to_addr} (not CDP wallet)")

        # Also check for USDC flows
        USDC_ADDRESS = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'
        ERC20_TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'

        print(f"\n💰 Checking USDC flows...")
        for log in receipt.logs:
            if log.address.lower() == USDC_ADDRESS.lower():
                if len(log.topics) >= 3 and log.topics[0].hex() == ERC20_TRANSFER:
                    from_addr = '0x' + log.topics[1].hex()[-40:]
                    to_addr = '0x' + log.topics[2].hex()[-40:]
                    amount = int(log.data.hex(), 16) / 1e6

                    # Check if involves CDP wallet
                    if from_addr.lower() == cdp_wallet.lower() or to_addr.lower() == cdp_wallet.lower():
                        print(f"   {from_addr[:10]}... → {to_addr[:10]}...: {amount:.2f} USDC")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None, None


if __name__ == "__main__":
    token_id, contract = find_nft_mint()
    if token_id:
        print(f"\n✅ Position {token_id} was created from contract {contract}")
        print(f"This transaction should be saved as POSITION_CREATED")
    else:
        print(f"\n❌ No NFT mint to CDP wallet found")