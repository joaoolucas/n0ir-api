#!/usr/bin/env python3
"""
Check logs for STAKING transaction to find NFT token ID.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


def check_staking_logs():
    """Check transaction logs for NFT transfer."""

    rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')
    w3 = Web3(Web3.HTTPProvider(rpc_url))

    tx_hash = '0xc0a86e089b66af75094f83a2dad6680801ef5e8efefb5ba25e24654e41d5a5be'
    cdp_wallet = '0x680214379083fa0d66d1EC030A045beEFB8Ec43f'

    print(f"\n{'='*60}")
    print(f"CHECKING STAKING TRANSACTION LOGS")
    print(f"{'='*60}")
    print(f"TX Hash: {tx_hash}")

    try:
        # Get transaction receipt
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        print(f"\n✅ Transaction found with {len(receipt.logs)} logs")

        # ERC721 Transfer event signature
        ERC721_TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
        NFT_POSITION_MANAGER = '0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1'

        # Check each log
        for i, log in enumerate(receipt.logs):
            print(f"\n📝 Log {i}:")
            print(f"   Address: {log.address}")
            print(f"   Topics: {len(log.topics)}")

            if len(log.topics) > 0:
                event_sig = log.topics[0].hex() if hasattr(log.topics[0], 'hex') else log.topics[0]
                print(f"   Event Signature: {event_sig}")

                # Debug: show if this matches ERC721 Transfer
                if event_sig.lower() == ERC721_TRANSFER.lower():
                    print(f"   >>> MATCHES ERC721 TRANSFER!")

                # Check if this is an ERC721 Transfer
                if event_sig.lower() == ERC721_TRANSFER.lower():
                    print(f"   ✅ This is an ERC721 Transfer event!")
                    print(f"   Contract: {log.address}")

                    # ERC721 can have 3 or 4 topics depending on if tokenId is indexed
                    if len(log.topics) >= 3:
                        # Extract from and to addresses
                        from_addr = '0x' + log.topics[1].hex()[-40:]
                        to_addr = '0x' + log.topics[2].hex()[-40:]

                        # Token ID might be in topics[3] or in data
                        if len(log.topics) >= 4:
                            token_id = int(log.topics[3].hex(), 16)
                        else:
                            # Try to get from data field
                            if log.data and len(log.data) > 2:
                                token_id = int(log.data.hex(), 16)
                            else:
                                token_id = None

                        print(f"   From: {from_addr}")
                        print(f"   To: {to_addr}")
                        if token_id is not None:
                            print(f"   Token ID: {token_id}")
                        else:
                            print(f"   Token ID: Could not parse")

                        if from_addr.lower() == cdp_wallet.lower() and token_id:
                            print(f"\n   🎯 FOUND IT! NFT {token_id} staked from CDP wallet!")
                            return token_id

        print(f"\n❌ No NFT transfer from CDP wallet found")
        return None

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    token_id = check_staking_logs()
    if token_id:
        print(f"\n✅ The NFT token ID that should be in the STAKING transaction is: {token_id}")
    else:
        print(f"\n❌ Could not determine NFT token ID from transaction logs")