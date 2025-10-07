#!/usr/bin/env python3
"""
Decode log 15 specifically.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


def decode_log15():
    """Decode log 15."""

    rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')
    w3 = Web3(Web3.HTTPProvider(rpc_url))

    tx_hash = '0x6760b89cbe37d7441dd49de1e1239f9362f0f9741c024f0ac93dec4b7bc46d00'
    cdp_wallet = '0x680214379083fa0d66d1EC030A045beEFB8Ec43f'

    print(f"Decoding ERC721 Transfer from gauge contract...")

    try:
        receipt = w3.eth.get_transaction_receipt(tx_hash)

        # Get log 15 (0-indexed)
        log = receipt.logs[15]

        print(f"\n📝 Log 15 (Gauge ERC721 Transfer):")
        print(f"   Contract: {log.address}")
        print(f"   Topics: {len(log.topics)}")

        if len(log.topics) == 4:
            # ERC721 Transfer
            event_sig = log.topics[0].hex()
            from_addr = '0x' + log.topics[1].hex()[-40:]
            to_addr = '0x' + log.topics[2].hex()[-40:]
            token_id = int(log.topics[3].hex(), 16)

            print(f"\n   Event: {event_sig}")
            print(f"   From: {from_addr}")
            print(f"   To: {to_addr}")
            print(f"   Token ID: {token_id}")

            if from_addr == '0x' + '0' * 40:
                print(f"\n   🎨 This is a MINT event!")
                print(f"   Minted NFT #{token_id} to {to_addr}")

                if to_addr.lower() == cdp_wallet.lower():
                    print(f"   🎯 MINTED TO CDP WALLET!")
                    print(f"\n✅ Position {token_id} was created and minted to CDP wallet {cdp_wallet}")
                    return token_id

                # Check if to_addr is another CDP wallet for the same user
                print(f"\n   Checking if {to_addr} is a CDP wallet...")
                # We'd need to check if this address is associated with the user

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

    return None


if __name__ == "__main__":
    token_id = decode_log15()
    if token_id:
        print(f"\n✅ Found position {token_id} minted by gauge contract")
        print("This is an unusual pattern - NFT minted by gauge instead of Position Manager")