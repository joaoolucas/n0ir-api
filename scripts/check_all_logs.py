#!/usr/bin/env python3
"""
Check all logs in the transaction.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


def check_logs():
    """Check all logs."""

    rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')
    w3 = Web3(Web3.HTTPProvider(rpc_url))

    tx_hash = '0x6760b89cbe37d7441dd49de1e1239f9362f0f9741c024f0ac93dec4b7bc46d00'
    cdp_wallet = '0x680214379083fa0d66d1EC030A045beEFB8Ec43f'

    print(f"\n{'='*60}")
    print(f"CHECKING ALL LOGS")
    print(f"{'='*60}")

    try:
        receipt = w3.eth.get_transaction_receipt(tx_hash)

        print(f"Total logs: {len(receipt.logs)}")

        # Known event signatures
        ERC721_TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
        ERC20_TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'

        for i, log in enumerate(receipt.logs):
            print(f"\n📝 Log {i}:")
            print(f"   Address: {log.address}")
            print(f"   Topics: {len(log.topics)}")

            if len(log.topics) > 0:
                event_sig = log.topics[0].hex()
                print(f"   Event: {event_sig}")

                # Check if it's a Transfer event (ERC20 or ERC721)
                if event_sig == ERC721_TRANSFER:
                    print(f"   ✅ This is a Transfer event!")

                    # Try to decode based on number of topics
                    if len(log.topics) == 3:
                        # ERC20 Transfer (from, to in topics, amount in data)
                        from_addr = '0x' + log.topics[1].hex()[-40:]
                        to_addr = '0x' + log.topics[2].hex()[-40:]
                        print(f"   Type: ERC20 Transfer")
                        print(f"   From: {from_addr}")
                        print(f"   To: {to_addr}")
                        if log.data:
                            amount = int(log.data.hex(), 16)
                            print(f"   Data: {amount}")

                    elif len(log.topics) == 4:
                        # ERC721 Transfer (from, to, tokenId in topics)
                        from_addr = '0x' + log.topics[1].hex()[-40:]
                        to_addr = '0x' + log.topics[2].hex()[-40:]
                        token_id = int(log.topics[3].hex(), 16)
                        print(f"   Type: ERC721 Transfer")
                        print(f"   From: {from_addr}")
                        print(f"   To: {to_addr}")
                        print(f"   Token ID: {token_id}")

                        # Check if to CDP wallet or from zero (mint)
                        if to_addr.lower() == cdp_wallet.lower():
                            print(f"   🎯 TO CDP WALLET!")
                            if from_addr == '0x' + '0' * 40:
                                print(f"   🎨 MINTED TO CDP WALLET!")
                        elif from_addr == '0x' + '0' * 40:
                            print(f"   🎨 MINTED to {to_addr}")
                            if token_id == 26256789:
                                print(f"   🎯 This is position 26256789!")

            # Also show raw data
            if log.data:
                print(f"   Data length: {len(log.data.hex())} chars")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    check_logs()