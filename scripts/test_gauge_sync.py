#!/usr/bin/env python3
"""
Test if the gauge position transaction is detected correctly.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


def test_detection():
    """Test if transaction would be detected correctly."""

    rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')
    w3 = Web3(Web3.HTTPProvider(rpc_url))

    tx_hash = '0x6760b89cbe37d7441dd49de1e1239f9362f0f9741c024f0ac93dec4b7bc46d00'

    print("TESTING GAUGE POSITION DETECTION")
    print("="*60)

    try:
        receipt = w3.eth.get_transaction_receipt(tx_hash)

        # Check for ERC721 Transfer events
        ERC721_TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'

        gauge_addresses = [
            "0x827922686190790b37229fd06084350e74485b72".lower(),  # WETH/USDC gauge
        ]

        nft_found = False

        for log in receipt.logs:
            if len(log.topics) > 0 and log.topics[0].hex() == ERC721_TRANSFER:
                log_address = log.address.lower()

                if log_address in gauge_addresses:
                    print(f"✅ Found ERC721 Transfer from gauge: {log_address}")

                    if len(log.topics) >= 4:
                        from_addr = '0x' + log.topics[1].hex()[-40:]
                        to_addr = '0x' + log.topics[2].hex()[-40:]
                        token_id = int(log.topics[3].hex(), 16)

                        if from_addr == '0x' + '0' * 40:
                            print(f"✅ NFT #{token_id} minted to {to_addr}")
                            nft_found = True

                            # This should be detected as POSITION_CREATED
                            print(f"\n🎯 This should be detected as POSITION_CREATED:")
                            print(f"   - NFT minted: {token_id}")
                            print(f"   - Minted by: gauge")
                            print(f"   - USDC amount: 0.0")
                            print(f"   - Should NOT be skipped even with 0 USDC")

        if not nft_found:
            print("❌ No NFT mint found - transaction won't be detected")

        # Check method signature
        tx = w3.eth.get_transaction(tx_hash)
        if len(tx.input) >= 10:
            method_sig = tx.input[:10]
            print(f"\n📝 Method signature: {method_sig}")
            print(f"   Note: Gauge mints may have different signatures")

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    test_detection()