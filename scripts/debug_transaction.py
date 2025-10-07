#!/usr/bin/env python3
"""
Debug why a specific transaction isn't being detected.
"""

import requests
import json

def analyze_transaction():
    """Fetch and analyze the specific transaction from CDP API."""

    tx_hash = "0x49c3e50bc60da811383b20bdae51174c99a137c13a1bba155cda46735f3a908d"
    user_wallet = "0xdbe4e3bcb15b221324b776db6f0cbff24918ea51"
    cdp_wallet = "0x7b3106f56447c9c313c19f519b290ff4e293d573"

    # CDP API configuration
    api_key = "PgSu2QFE67b4koEsqfe6yp831l7KCKgH"  # From staging env vars
    base_url = "https://api.cdp.coinbase.com/platform"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Fetch transactions for the CDP wallet
    print(f"Fetching transactions for CDP wallet: {cdp_wallet}")
    print(f"Looking for transaction: {tx_hash}")
    print("-" * 80)

    # We need to fetch enough transactions to find our target
    all_transactions = []
    next_page = None
    page_count = 0
    max_pages = 10  # Limit to avoid infinite loop

    while page_count < max_pages:
        page_count += 1

        # Build URL with pagination
        url = f"{base_url}/v1/networks/base-mainnet/addresses/{cdp_wallet}/transactions"
        params = {"limit": 20}
        if next_page:
            params["page"] = next_page

        print(f"\nFetching page {page_count}...")

        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            transactions = data.get("data", [])
            print(f"  Found {len(transactions)} transactions")

            # Check each transaction
            for tx in transactions:
                content = tx.get("content", {})
                traces = content.get("flattened_traces", [])

                if traces:
                    tx_hash_found = traces[0].get("transaction_hash", "")
                    if tx_hash_found.lower() == tx_hash.lower():
                        print(f"\n✅ FOUND TRANSACTION!")
                        print(f"  Block: {traces[0].get('block_number', 'unknown')}")
                        print(f"  Timestamp: {content.get('block_timestamp', 'unknown')}")

                        # Analyze the transaction structure
                        print("\n  Transaction structure:")
                        print(f"  Number of traces: {len(traces)}")

                        for i, trace in enumerate(traces):
                            from_addr = trace.get("from", "").lower()
                            to_addr = trace.get("to", "").lower()
                            input_data = trace.get("input", "")

                            print(f"\n  Trace {i}:")
                            print(f"    From: {from_addr}")
                            print(f"    To: {to_addr}")
                            print(f"    Input length: {len(input_data)}")
                            if input_data and len(input_data) >= 10:
                                print(f"    Method signature: {input_data[:10]}")

                            # Check if this is interaction with LiquidityManager
                            liquidity_manager = "0xBeb749B7F1149b75E79C1d818Ad3587060A3805D".lower()
                            if to_addr == liquidity_manager:
                                print(f"    ⚠️ INTERACTION WITH LIQUIDITY MANAGER!")
                                if input_data and len(input_data) >= 10:
                                    method_sig = input_data[:10]
                                    print(f"    Method signature: {method_sig}")

                                    # Known signatures
                                    if method_sig == "0x3a1e3569":
                                        print(f"    ✅ This is openPosition!")
                                    elif method_sig == "0xe0891d91":
                                        print(f"    This is closePosition")
                                    else:
                                        print(f"    ❌ Unknown method signature!")

                        # Save full transaction for analysis
                        with open('/tmp/transaction_debug.json', 'w') as f:
                            json.dump(tx, f, indent=2)
                        print(f"\n  Full transaction saved to /tmp/transaction_debug.json")

                        return tx

            all_transactions.extend(transactions)

            # Check for next page
            next_page = data.get("next_page")
            if not next_page:
                print("\n  No more pages")
                break

        except Exception as e:
            print(f"Error fetching transactions: {e}")
            break

    print(f"\n❌ Transaction not found after checking {len(all_transactions)} transactions")
    print(f"The transaction might be older than the {len(all_transactions)} most recent transactions")

    return None

if __name__ == "__main__":
    result = analyze_transaction()

    if not result:
        print("\nPossible issues:")
        print("1. The transaction is older than the fetched range")
        print("2. The transaction wasn't made from the CDP wallet")
        print("3. The CDP API might not have indexed it yet")
        print("\nTry checking the transaction directly on Basescan:")
        print(f"https://basescan.org/tx/0x49c3e50bc60da811383b20bdae51174c99a137c13a1bba155cda46735f3a908d")