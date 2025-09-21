#!/usr/bin/env python3
"""
Re-sync a specific STAKING transaction to debug why NFT token ID is missing.
"""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3
import json

# Load .env from project root
root_dir = Path(__file__).parent.parent
sys.path.append(str(root_dir))
load_dotenv(root_dir / '.env')

from app.services.wallet_transaction_service import WalletTransactionService
from app.database.session import AsyncSessionLocal


async def resync_staking_tx():
    """Re-sync the STAKING transaction."""

    rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')
    w3 = Web3(Web3.HTTPProvider(rpc_url))

    tx_hash = '0xc0a86e089b66af75094f83a2dad6680801ef5e8efefb5ba25e24654e41d5a5be'
    user_id = '0xAC65e18F7f4e5eDEA297b9E5433C153f1d9a7764'
    cdp_wallet = '0x680214379083fa0d66d1EC030A045beEFB8Ec43f'

    print(f"\n{'='*60}")
    print(f"RE-SYNCING STAKING TRANSACTION")
    print(f"{'='*60}")
    print(f"TX Hash: {tx_hash}")
    print(f"User: {user_id}")
    print(f"CDP Wallet: {cdp_wallet}")

    try:
        # Get transaction receipt to check logs
        print(f"\n📊 Fetching transaction receipt...")
        receipt = w3.eth.get_transaction_receipt(tx_hash)

        print(f"✅ Transaction found with {len(receipt.logs)} logs")

        # ERC721 Transfer event signature
        ERC721_TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'

        # Check for ERC721 Transfer events
        print(f"\n🔍 Checking for ERC721 Transfer events...")
        for i, log in enumerate(receipt.logs):
            if len(log.topics) > 0:
                event_sig = log.topics[0].hex() if hasattr(log.topics[0], 'hex') else log.topics[0]

                if event_sig.lower() == ERC721_TRANSFER.lower():
                    print(f"\n✅ Found ERC721 Transfer event in log {i}:")
                    print(f"   Contract: {log.address}")

                    if len(log.topics) >= 4:
                        # Extract from, to, and tokenId
                        from_addr = '0x' + log.topics[1].hex()[-40:]
                        to_addr = '0x' + log.topics[2].hex()[-40:]
                        token_id = int(log.topics[3].hex(), 16)

                        print(f"   From: {from_addr}")
                        print(f"   To: {to_addr}")
                        print(f"   Token ID: {token_id}")

                        # Check if this is from CDP wallet (staking)
                        if from_addr.lower() == cdp_wallet.lower():
                            print(f"   ✅ This is a STAKING transaction!")
                            print(f"   NFT {token_id} staked from CDP wallet to {to_addr}")

        # Now use the transaction service to re-categorize
        print(f"\n🔄 Re-categorizing transaction with WalletTransactionService...")

        async with AsyncSessionLocal() as db:
            service = WalletTransactionService(db)

            # Get traces for the transaction
            traces = service.web3_service.get_transaction_traces(tx_hash)
            print(f"   Got {len(traces)} traces")

            # Analyze the transaction
            tx_type, details = await service._analyze_transaction(
                traces, user_id, cdp_wallet
            )

            print(f"\n📋 Analysis Result:")
            print(f"   Type: {tx_type}")
            print(f"   Details:")
            for key, value in details.items():
                if key != 'description':
                    print(f"     {key}: {value}")

            if 'nft_token_id' not in details:
                print(f"\n❌ NFT token ID not detected!")
                print(f"   This is the issue - the ERC721 event parsing isn't working")
            else:
                print(f"\n✅ NFT token ID detected: {details['nft_token_id']}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(resync_staking_tx())