#!/usr/bin/env python3
"""Check events in a specific transaction using web3."""

import json
from web3 import Web3

# Connect to Base mainnet
RPC_URL = "https://base-mainnet.g.alchemy.com/v2/demo"  # Public RPC
w3 = Web3(Web3.HTTPProvider(RPC_URL))

def check_transaction(tx_hash):
    """Check transaction details and events."""
    try:
        # Get transaction
        tx = w3.eth.get_transaction(tx_hash)
        print(f"Transaction: {tx_hash}")
        print(f"  From: {tx['from']}")
        print(f"  To: {tx['to']}")
        print(f"  Value: {tx['value']} wei")

        # Get transaction receipt for logs
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        print(f"  Status: {'Success' if receipt['status'] == 1 else 'Failed'}")
        print(f"  Gas used: {receipt['gasUsed']}")

        # Check logs/events
        print(f"\n  Events ({len(receipt['logs'])} total):")

        # Known event signatures
        DECREASE_LIQUIDITY = "0x26f6a048ee9138f2c0ce266f322cb99228e8d619ae2bff30c67f8dcf9d2377b4"
        INCREASE_LIQUIDITY = "0x3067048beee31b25b2f1681f88dac838c8bba36af25bfb2b7cf7473a5847e35f"
        COLLECT = "0x40d0efd1a53d60ecbf40971b9daf7dc90178c3aadc7aab1765632738fa8b8f01"
        TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

        for i, log in enumerate(receipt['logs']):
            topics = log['topics']
            if topics:
                event_sig = topics[0].hex() if hasattr(topics[0], 'hex') else str(topics[0])
                print(f"\n  Log #{i}:")
                print(f"    Address: {log['address']}")
                print(f"    Event signature: {event_sig}")

                # Identify known events
                if event_sig == DECREASE_LIQUIDITY.lower():
                    print(f"    → DecreaseLiquidity event detected!")
                    if len(topics) > 1:
                        token_id = int(topics[1].hex(), 16)
                        print(f"    Token ID: {token_id}")
                elif event_sig == COLLECT.lower():
                    print(f"    → Collect event detected!")
                    if len(topics) > 1:
                        token_id = int(topics[1].hex(), 16)
                        print(f"    Token ID: {token_id}")
                elif event_sig.lower() == INCREASE_LIQUIDITY.lower():
                    print(f"    → IncreaseLiquidity event")
                elif event_sig.lower() == TRANSFER.lower():
                    print(f"    → Transfer event")

                # Show data if present
                if log['data'] and log['data'] != '0x':
                    print(f"    Data length: {len(log['data'])} chars")

        return True

    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    # The missing transaction
    tx_hash = "0x63f8cc21dd3ecf759a533a608836cb942c3a9d61178d6c7fe4f7fd824abb43ca"
    print(f"Checking transaction on Base mainnet...")
    print("=" * 60)
    check_transaction(tx_hash)