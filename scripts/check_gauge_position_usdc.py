#!/usr/bin/env python3
"""
Check the actual USDC amount for gauge-minted position.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


def check_usdc_amount():
    """Check USDC flows in the transaction."""

    rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')
    w3 = Web3(Web3.HTTPProvider(rpc_url))

    tx_hash = '0x6760b89cbe37d7441dd49de1e1239f9362f0f9741c024f0ac93dec4b7bc46d00'
    cdp_wallet = '0x680214379083fa0d66d1EC030A045beEFB8Ec43f'
    owner_wallet = '0xAC65e18F7f4e5eDEA297b9E5433C153f1d9a7764'

    print("="*60)
    print("CHECKING USDC FLOWS FOR GAUGE POSITION")
    print("="*60)
    print(f"TX Hash: {tx_hash}")

    try:
        tx = w3.eth.get_transaction(tx_hash)
        receipt = w3.eth.get_transaction_receipt(tx_hash)

        print(f"\n📊 Transaction:")
        print(f"   From: {tx['from']}")
        print(f"   To: {tx['to']}")

        # Check USDC transfers
        USDC_ADDRESS = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'
        ERC20_TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'

        usdc_in_to_cdp = 0
        usdc_out_from_cdp = 0
        usdc_from_owner = 0

        print(f"\n💰 USDC Transfers:")

        for log in receipt.logs:
            if log.address.lower() == USDC_ADDRESS.lower():
                if len(log.topics) >= 3 and log.topics[0].hex() == ERC20_TRANSFER:
                    from_addr = '0x' + log.topics[1].hex()[-40:]
                    to_addr = '0x' + log.topics[2].hex()[-40:]
                    amount = int(log.data.hex(), 16) / 1e6  # Convert to USDC

                    print(f"   From {from_addr[:10]}... to {to_addr[:10]}...: {amount:.2f} USDC")

                    # Track flows
                    if to_addr.lower() == cdp_wallet.lower():
                        usdc_in_to_cdp += amount
                        if from_addr.lower() == owner_wallet.lower():
                            usdc_from_owner += amount
                            print(f"      ↳ This is from OWNER wallet")
                    elif from_addr.lower() == cdp_wallet.lower():
                        usdc_out_from_cdp += amount
                        print(f"      ↳ This is from CDP wallet")

        net_usdc = usdc_out_from_cdp - usdc_in_to_cdp

        print(f"\n📈 Summary:")
        print(f"   USDC OUT from CDP: {usdc_out_from_cdp:.2f}")
        print(f"   USDC IN to CDP: {usdc_in_to_cdp:.2f}")
        print(f"   Net USDC invested: {net_usdc:.2f}")
        print(f"   From owner wallet: {usdc_from_owner:.2f}")

        # Check WETH transfers too
        WETH_ADDRESS = '0x4200000000000000000000000000000000000006'

        print(f"\n💎 WETH Transfers:")
        for log in receipt.logs:
            if log.address.lower() == WETH_ADDRESS.lower():
                if len(log.topics) >= 3 and log.topics[0].hex() == ERC20_TRANSFER:
                    from_addr = '0x' + log.topics[1].hex()[-40:]
                    to_addr = '0x' + log.topics[2].hex()[-40:]
                    amount = int(log.data.hex(), 16) / 1e18  # Convert to WETH

                    if from_addr.lower() == cdp_wallet.lower() or to_addr.lower() == cdp_wallet.lower():
                        print(f"   From {from_addr[:10]}... to {to_addr[:10]}...: {amount:.6f} WETH")

        return net_usdc if net_usdc > 0 else usdc_from_owner

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 0


if __name__ == "__main__":
    amount = check_usdc_amount()
    print(f"\n✅ The position entry amount should be: {amount:.2f} USDC")