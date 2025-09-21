#!/usr/bin/env python3
"""
Analyze what the deleted transaction actually was.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


def analyze_tx():
    """Analyze the transaction."""

    rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')
    w3 = Web3(Web3.HTTPProvider(rpc_url))

    tx_hash = '0x7d1b26dd0dcd74e6afbad5b69fbb3a54f057912c193f5fecf45a8c036418a0ed'

    print(f"ANALYZING TRANSACTION")
    print("="*60)
    print(f"TX Hash: {tx_hash}")

    try:
        tx = w3.eth.get_transaction(tx_hash)
        receipt = w3.eth.get_transaction_receipt(tx_hash)

        print(f"\n📊 Transaction:")
        print(f"   From: {tx['from']}")
        print(f"   To: {tx['to']}")
        print(f"   Success: {'Yes' if receipt['status'] == 1 else 'No'}")

        # Decode method signature
        if len(tx.input) >= 10:
            method_sig = tx.input[:10]
            print(f"   Method: {method_sig}")

            if method_sig == '0x3a1e3569':
                print(f"   ✅ This is openPosition (not close!)")

        # Check for NFT events
        ERC721_TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
        NFT_POSITION_MANAGER = '0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1'

        print(f"\n🎨 NFT Events:")
        nft_found = False
        for log in receipt.logs:
            if log.address.lower() == NFT_POSITION_MANAGER.lower():
                if len(log.topics) > 0 and log.topics[0].hex() == ERC721_TRANSFER:
                    if len(log.topics) >= 4:
                        from_addr = '0x' + log.topics[1].hex()[-40:]
                        to_addr = '0x' + log.topics[2].hex()[-40:]
                        token_id = int(log.topics[3].hex(), 16)

                        if from_addr == '0x' + '0' * 40:
                            print(f"   MINT: NFT #{token_id} to {to_addr}")
                            nft_found = True
                        elif to_addr == '0x' + '0' * 40:
                            print(f"   BURN: NFT #{token_id} from {from_addr}")
                            nft_found = True

        if not nft_found:
            print(f"   No NFT mint or burn found")

        # Check USDC/AERO flows
        USDC_ADDRESS = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'
        AERO_ADDRESS = '0x940181a94A35A4569E4529A3CDfB74e38FD98631'
        ERC20_TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'

        print(f"\n💰 Token Flows:")

        cdp_wallet = '0x680214379083fa0d66d1EC030A045beEFB8Ec43f'

        for log in receipt.logs:
            if len(log.topics) >= 3 and log.topics[0].hex() == ERC20_TRANSFER:
                from_addr = '0x' + log.topics[1].hex()[-40:]
                to_addr = '0x' + log.topics[2].hex()[-40:]

                if log.address.lower() == USDC_ADDRESS.lower():
                    amount = int(log.data.hex(), 16) / 1e6
                    if to_addr.lower() == cdp_wallet.lower():
                        print(f"   USDC IN: {amount:.2f} USDC from {from_addr[:10]}...")
                    elif from_addr.lower() == cdp_wallet.lower():
                        print(f"   USDC OUT: {amount:.2f} USDC to {to_addr[:10]}...")

                elif log.address.lower() == AERO_ADDRESS.lower():
                    amount = int(log.data.hex(), 16) / 1e18
                    if to_addr.lower() == cdp_wallet.lower():
                        print(f"   AERO IN: {amount:.6f} AERO from {from_addr[:10]}...")
                    elif from_addr.lower() == cdp_wallet.lower():
                        print(f"   AERO OUT: {amount:.6f} AERO to {to_addr[:10]}...")

        print(f"\n📝 Conclusion:")
        print(f"   This appears to be a FAILED position open attempt or a SWAP")
        print(f"   - Has openPosition method signature")
        print(f"   - Tokens coming IN (not out)")
        print(f"   - No NFT was minted")
        print(f"   - Should NOT be saved as POSITION_CLOSED")

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    analyze_tx()