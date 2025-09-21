#!/usr/bin/env python3
"""Check if a transaction has an NFT burn event."""

from web3 import Web3

# Transaction that's being misclassified as POSITION_CLOSED
tx_hash = "0x67769015f86fbf3ebea854e0aa6e0006a760bfe5eee48bfa89cfedc1e5e065df"

rpc_url = "https://base-mainnet.g.alchemy.com/v2/PbEIlFPXdZpA6ld_nxViZD73mlaupBrY"
w3 = Web3(Web3.HTTPProvider(rpc_url))

print(f"Checking transaction: {tx_hash}")
print("-" * 60)

# Get transaction receipt
receipt = w3.eth.get_transaction_receipt(tx_hash)

print(f"Transaction from: {receipt['from']}")
print(f"Transaction to: {receipt['to']}")
print(f"Number of logs: {len(receipt['logs'])}")
print("-" * 60)

# ERC721 Transfer event signature
transfer_sig = Web3.keccak(text="Transfer(address,address,uint256)").hex()

# Look for NFT burns (transfers to 0x0)
found_burn = False
found_transfer = False

for i, log in enumerate(receipt['logs']):
    if len(log['topics']) == 4:
        event_sig = log['topics'][0].hex()

        if event_sig == transfer_sig:
            from_addr = Web3.to_checksum_address('0x' + log['topics'][1].hex()[-40:])
            to_addr = Web3.to_checksum_address('0x' + log['topics'][2].hex()[-40:])
            token_id = int(log['topics'][3].hex(), 16)

            print(f"Log {i}: ERC721 Transfer Found!")
            print(f"  Contract: {log['address']}")
            print(f"  From: {from_addr}")
            print(f"  To: {to_addr}")
            print(f"  Token ID: {token_id}")

            if to_addr == "0x0000000000000000000000000000000000000000":
                print(f"  ⚠️ THIS IS A BURN EVENT - Position actually closed")
                found_burn = True
            else:
                print(f"  ✅ NOT a burn - Token transferred to {to_addr}")
                found_transfer = True
            print()

print("-" * 60)
if found_burn:
    print("CONCLUSION: This IS a position close (NFT was burned)")
elif found_transfer:
    print("CONCLUSION: This is NOT a position close (NFT was transferred, not burned)")
else:
    print("CONCLUSION: No ERC721 Transfer events found - likely NOT a position operation")