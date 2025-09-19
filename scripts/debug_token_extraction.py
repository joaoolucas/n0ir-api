#!/usr/bin/env python3
"""
Debug token_id extraction from transaction logs.
"""

from web3 import Web3
import json

def debug_transaction_logs():
    """Debug the transaction to find where the token_id is."""

    # Connect to RPC
    rpc_url = "https://api.developer.coinbase.com/rpc/v1/base/PgSu2QFE67b4koEsqfe6yp831l7KCKgH"
    w3 = Web3(Web3.HTTPProvider(rpc_url))

    tx_hash = "0x49c3e50bc60da811383b20bdae51174c99a137c13a1bba155cda46735f3a908d"
    position_manager_address = "0x827922686190790b37229fd06084350E74485b72".lower()

    print(f"Fetching transaction receipt for: {tx_hash}")
    print("=" * 80)

    # Get transaction receipt
    receipt = w3.eth.get_transaction_receipt(tx_hash)

    print(f"Transaction status: {'Success' if receipt.status == 1 else 'Failed'}")
    print(f"Total logs: {len(receipt.logs)}")
    print()

    # Known event signatures
    increase_liquidity_topic = "0x3067048beee31b25b2f1681f88dac838c8bba36af25bfb2b7cf7473a5847e35f"
    transfer_topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

    # Look for ALL logs from PositionManager
    position_manager_logs = []

    for i, log in enumerate(receipt.logs):
        log_address = log.address.lower()

        if log_address == position_manager_address:
            position_manager_logs.append((i, log))

    print(f"Found {len(position_manager_logs)} logs from PositionManager")
    print()

    for idx, (log_idx, log) in enumerate(position_manager_logs):
        print(f"PositionManager Log #{idx} (overall log #{log_idx}):")
        print(f"  Address: {log.address}")
        print(f"  Topics count: {len(log.topics)}")

        if len(log.topics) > 0:
            topic0 = log.topics[0].hex()
            print(f"  Topic[0] (event sig): {topic0}")

            # Check what event this is
            if topic0 == increase_liquidity_topic:
                print(f"  ✅ This is IncreaseLiquidity event!")
                if len(log.topics) >= 2:
                    token_id = int(log.topics[1].hex(), 16)
                    print(f"  🎯 TOKEN_ID: {token_id}")

            elif topic0 == transfer_topic:
                print(f"  ✅ This is Transfer event!")
                if len(log.topics) >= 4:
                    from_addr = log.topics[1].hex()
                    to_addr = log.topics[2].hex()
                    token_id = int(log.topics[3].hex(), 16)
                    print(f"  From: {from_addr}")
                    print(f"  To: {to_addr}")
                    print(f"  🎯 TOKEN_ID: {token_id}")

                    # Check if it's a mint
                    if from_addr == "0x" + "0" * 64:
                        print(f"  ✨ This is a MINT (from zero address)!")
            else:
                print(f"  Unknown event")

            # Print all topics for debugging
            for j, topic in enumerate(log.topics):
                print(f"  Topic[{j}]: {topic.hex()}")

        # Print data field if present
        if log.data and log.data != "0x":
            print(f"  Data (first 100 chars): {log.data[:100]}...")

        print()

    # Also check for any Transfer events in ANY contract (not just PositionManager)
    print("\nLooking for ANY Transfer events in the transaction:")
    print("-" * 40)

    for i, log in enumerate(receipt.logs):
        if len(log.topics) > 0 and log.topics[0].hex() == transfer_topic:
            print(f"Transfer event in log #{i}:")
            print(f"  Contract: {log.address}")

            if len(log.topics) >= 4:
                # Standard ERC721 Transfer has 4 topics
                from_addr = log.topics[1].hex()
                to_addr = log.topics[2].hex()
                token_id_hex = log.topics[3].hex()

                # Try to parse as token ID
                try:
                    token_id = int(token_id_hex, 16)
                    print(f"  From: {from_addr}")
                    print(f"  To: {to_addr}")
                    print(f"  TokenID: {token_id}")

                    if log.address.lower() == position_manager_address:
                        print(f"  ✅ This is from PositionManager!")
                except:
                    pass

            elif len(log.topics) == 3 and log.data and log.data != "0x":
                # ERC20 Transfer has 3 topics, amount in data
                from_addr = log.topics[1].hex()
                to_addr = log.topics[2].hex()
                print(f"  From: {from_addr}")
                print(f"  To: {to_addr}")
                print(f"  Data (amount): {log.data}")
            print()

if __name__ == "__main__":
    debug_transaction_logs()