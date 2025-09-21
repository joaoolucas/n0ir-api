#!/usr/bin/env python3
"""
Check event signature issue.
"""

from web3 import Web3
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')

rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')
w3 = Web3(Web3.HTTPProvider(rpc_url))

tx_hash = '0x6760b89cbe37d7441dd49de1e1239f9362f0f9741c024f0ac93dec4b7bc46d00'
receipt = w3.eth.get_transaction_receipt(tx_hash)

# Check log #19 specifically
log = receipt.logs[19]
event_sig = log.topics[0].hex() if hasattr(log.topics[0], 'hex') else str(log.topics[0])

print(f"Log #19 event signature:")
print(f"  Raw: {log.topics[0]}")
print(f"  Hex: {event_sig}")
print(f"  Lower: {event_sig.lower()}")
print(f"\nExpected signature:")
print(f"  0x8d53117d19441d0a7f168d2728ff066eed66d078efdaf9bf249eef6e20887ae5")
print(f"\nMatch: {event_sig.lower() == '0x8d53117d19441d0a7f168d2728ff066eed66d078efdaf9bf249eef6e20887ae5'}")

# Without 0x prefix?
print(f"\nWithout 0x:")
print(f"  event_sig: {event_sig.lower()}")
print(f"  expected:  8d53117d19441d0a7f168d2728ff066eed66d078efdaf9bf249eef6e20887ae5")
print(f"  Match: {event_sig.lower() == '8d53117d19441d0a7f168d2728ff066eed66d078efdaf9bf249eef6e20887ae5'}")
