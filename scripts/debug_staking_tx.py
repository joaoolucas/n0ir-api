#!/usr/bin/env python3
"""Debug a specific staking transaction to see why NFT ID extraction fails."""

import json
from web3 import Web3

# Recent staking tx without position_id
tx_hash = "0xba842e5961184faa149c8ca4c08dee9afaf09c975c1053b912986e9df295c513"

rpc_url = "https://base-mainnet.g.alchemy.com/v2/PbEIlFPXdZpA6ld_nxViZD73mlaupBrY"
w3 = Web3(Web3.HTTPProvider(rpc_url))

print(f"Analyzing transaction: {tx_hash}")
print("-" * 60)

# Get transaction receipt
receipt = w3.eth.get_transaction_receipt(tx_hash)

print(f"Transaction from: {receipt['from']}")
print(f"Transaction to: {receipt['to']}")
print(f"Number of logs: {len(receipt['logs'])}")
print("-" * 60)

# ERC721 Transfer event signature
transfer_sig = Web3.keccak(text="Transfer(address,address,uint256)").hex()
print(f"Looking for ERC721 Transfer event: {transfer_sig}")
print("-" * 60)

# Look for ERC721 Transfer events
found_nft_transfer = False
for i, log in enumerate(receipt['logs']):
    if len(log['topics']) > 0:
        event_sig = log['topics'][0].hex()

        # Check if this is an ERC721 Transfer
        if len(log['topics']) == 4 and event_sig == transfer_sig:
            from_addr = Web3.to_checksum_address('0x' + log['topics'][1].hex()[-40:])
            to_addr = Web3.to_checksum_address('0x' + log['topics'][2].hex()[-40:])
            token_id = int(log['topics'][3].hex(), 16)

            print(f"Log {i}: ERC721 Transfer Found!")
            print(f"  Contract: {log['address']}")
            print(f"  From: {from_addr}")
            print(f"  To: {to_addr}")
            print(f"  Token ID: {token_id}")
            print(f"  Topics: {[t.hex() for t in log['topics']]}")
            found_nft_transfer = True
            print("-" * 60)

if not found_nft_transfer:
    print("NO ERC721 Transfer events found!")
    print("\nAll events in transaction:")
    for i, log in enumerate(receipt['logs']):
        if len(log['topics']) > 0:
            print(f"Log {i}:")
            print(f"  Contract: {log['address']}")
            print(f"  Event signature: {log['topics'][0].hex()}")
            print(f"  Number of topics: {len(log['topics'])}")
            if len(log['topics']) > 1:
                print(f"  Topics: {[t.hex()[:10] + '...' for t in log['topics'][1:]]}")
            print()