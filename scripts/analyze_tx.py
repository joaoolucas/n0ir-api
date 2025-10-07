#!/usr/bin/env python3
"""
Analyze a specific transaction to understand its structure
"""

import requests
import json
from decimal import Decimal

# Transaction to analyze
TX_HASH = "0xd52a3f8ba9b39b3a4191dc0297d5cb15790cd6f6bc4590588a6b4911923bdd31"

# Base chain explorer API
BASE_SCAN_API = "https://api.basescan.org/api"
# You might need an API key for Basescan - using public endpoint
ETHERSCAN_API_KEY = "YourAPIKeyHere"  # Replace if you have one

# Known addresses
USER_WALLET = "0xAC65e18F7f4e5eDEA297b9E5433C153f1d9a7764".lower()
CDP_WALLET = "0x680214379083fa0d66d1EC030A045beEFB8Ec43f".lower()
USDC_ADDRESS = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913".lower()
LIQUIDITY_MANAGER = "0x827922686190790b37229fd06084350e74485b72".lower()
NFT_POSITION_MANAGER = "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1".lower()

def analyze_transaction():
    """Fetch and analyze the transaction"""

    # Using public RPC endpoint for Base
    rpc_url = "https://mainnet.base.org"

    # Get transaction details via RPC
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_getTransactionByHash",
        "params": [TX_HASH],
        "id": 1
    }

    response = requests.post(rpc_url, json=payload)
    tx_data = response.json().get("result", {})

    print("=" * 80)
    print(f"TRANSACTION ANALYSIS: {TX_HASH}")
    print("=" * 80)

    if tx_data:
        print("\n📊 BASIC INFO:")
        print(f"  From: {tx_data.get('from')}")
        print(f"  To: {tx_data.get('to')}")
        print(f"  Value: {int(tx_data.get('value', '0x0'), 16) / 10**18} ETH")
        print(f"  Gas: {int(tx_data.get('gas', '0x0'), 16)}")

        # Check if it's from CDP wallet
        from_addr = tx_data.get('from', '').lower()
        to_addr = tx_data.get('to', '').lower()

        print("\n🔍 WALLET ANALYSIS:")
        print(f"  From CDP Wallet: {from_addr == CDP_WALLET}")
        print(f"  From User Wallet: {from_addr == USER_WALLET}")
        print(f"  To CDP Wallet: {to_addr == CDP_WALLET}")
        print(f"  To User Wallet: {to_addr == USER_WALLET}")
        print(f"  To USDC Contract: {to_addr == USDC_ADDRESS}")
        print(f"  To Liquidity Manager: {to_addr == LIQUIDITY_MANAGER}")
        print(f"  To NFT Position Manager: {to_addr == NFT_POSITION_MANAGER}")

        # Decode input data if present
        input_data = tx_data.get('input', '0x')
        if len(input_data) > 10:
            method_sig = input_data[:10]
            print(f"\n📝 METHOD SIGNATURE: {method_sig}")

            # Known method signatures
            known_methods = {
                "0xa9059cbb": "transfer(address,uint256)",
                "0x23b872dd": "transferFrom(address,address,uint256)",
                "0x095ea7b3": "approve(address,uint256)",
                "0x3a1e3569": "openPosition",
                "0x2b17db59": "openPosition (alt)",
                "0xe0891d91": "closePosition",
                "0xb6b55f25": "deposit(uint256)",
                "0x2e1a7d4d": "withdraw(uint256)",
                "0x853828b6": "withdrawAll()",
            }

            if method_sig in known_methods:
                print(f"  Method: {known_methods[method_sig]}")
            else:
                print(f"  Method: Unknown")

            # Try to decode parameters for common methods
            if method_sig == "0xa9059cbb":  # transfer
                if len(input_data) >= 138:  # 10 + 64 + 64
                    to_param = "0x" + input_data[34:74]
                    amount_hex = input_data[74:138]
                    amount = int(amount_hex, 16) if amount_hex else 0
                    print(f"  Transfer To: {to_param}")
                    print(f"  Amount: {amount / 10**6:.2f} USDC")
                    print(f"  To User Wallet: {to_param.lower() == USER_WALLET}")

    # Get transaction receipt for logs
    receipt_payload = {
        "jsonrpc": "2.0",
        "method": "eth_getTransactionReceipt",
        "params": [TX_HASH],
        "id": 2
    }

    receipt_response = requests.post(rpc_url, json=receipt_payload)
    receipt = receipt_response.json().get("result", {})

    if receipt:
        print(f"\n✅ TRANSACTION STATUS: {'Success' if receipt.get('status') == '0x1' else 'Failed'}")
        print(f"  Block Number: {int(receipt.get('blockNumber', '0x0'), 16)}")
        print(f"  Gas Used: {int(receipt.get('gasUsed', '0x0'), 16)}")

        logs = receipt.get('logs', [])
        print(f"\n📋 LOGS: {len(logs)} events")

        # ERC20 Transfer event signature
        transfer_sig = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

        usdc_transfers = []
        for i, log in enumerate(logs):
            if log.get('address', '').lower() == USDC_ADDRESS:
                topics = log.get('topics', [])
                if topics and topics[0] == transfer_sig:
                    # Decode Transfer event
                    from_addr = "0x" + topics[1][-40:] if len(topics) > 1 else "0x0"
                    to_addr = "0x" + topics[2][-40:] if len(topics) > 2 else "0x0"
                    amount_data = log.get('data', '0x0')
                    amount = int(amount_data, 16) if amount_data != '0x' else 0

                    usdc_transfers.append({
                        'from': from_addr.lower(),
                        'to': to_addr.lower(),
                        'amount': amount / 10**6  # USDC has 6 decimals
                    })

        if usdc_transfers:
            print("\n💵 USDC TRANSFERS FOUND:")
            for i, transfer in enumerate(usdc_transfers, 1):
                print(f"\n  Transfer #{i}:")
                print(f"    From: {transfer['from']}")
                print(f"    To: {transfer['to']}")
                print(f"    Amount: ${transfer['amount']:.2f}")

                # Identify the wallets
                from_type = "CDP Wallet" if transfer['from'] == CDP_WALLET else \
                           "User Wallet" if transfer['from'] == USER_WALLET else \
                           "Unknown"
                to_type = "CDP Wallet" if transfer['to'] == CDP_WALLET else \
                         "User Wallet" if transfer['to'] == USER_WALLET else \
                         "Unknown"

                print(f"    From Type: {from_type}")
                print(f"    To Type: {to_type}")

                # Check if this is a withdrawal
                if transfer['to'] == USER_WALLET:
                    print(f"    ✅ THIS IS A WITHDRAWAL TO USER WALLET!")
        else:
            print("\n❌ No USDC transfers found in logs")

        # Check for NFT burns (position closes)
        nft_transfer_found = False
        for log in logs:
            if log.get('address', '').lower() == NFT_POSITION_MANAGER:
                topics = log.get('topics', [])
                if topics and topics[0] == transfer_sig:  # Same sig for ERC721
                    if len(topics) >= 4:
                        to_addr = topics[2][-40:] if len(topics[2]) > 40 else topics[2]
                        if to_addr == "0" * 40:  # Burn address
                            nft_id = int(topics[3], 16) if topics[3] else 0
                            print(f"\n🔥 NFT BURN DETECTED: Position #{nft_id} was closed")
                            nft_transfer_found = True

    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    analyze_transaction()