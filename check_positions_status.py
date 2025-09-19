#!/usr/bin/env python3
"""Check why positions show CLOSED/ERROR but are still ACTIVE."""

import asyncio
import asyncpg
from web3 import Web3

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

# Connect to Base mainnet
RPC_URL = "https://base-mainnet.g.alchemy.com/v2/demo"
w3 = Web3(Web3.HTTPProvider(RPC_URL))

# NonfungiblePositionManager contract on Base
NPM_ADDRESS = "0x827922686190790b37229fd06084350E74485b72"

# Minimal ABI for positions method
NPM_ABI = [
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "positions",
        "outputs": [
            {"internalType": "uint96", "name": "nonce", "type": "uint96"},
            {"internalType": "address", "name": "operator", "type": "address"},
            {"internalType": "address", "name": "token0", "type": "address"},
            {"internalType": "address", "name": "token1", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"},
            {"internalType": "int24", "name": "tickLower", "type": "int24"},
            {"internalType": "int24", "name": "tickUpper", "type": "int24"},
            {"internalType": "uint128", "name": "liquidity", "type": "uint128"},
            {"internalType": "uint256", "name": "feeGrowthInside0LastX128", "type": "uint256"},
            {"internalType": "uint256", "name": "feeGrowthInside1LastX128", "type": "uint256"},
            {"internalType": "uint128", "name": "tokensOwed0", "type": "uint128"},
            {"internalType": "uint128", "name": "tokensOwed1", "type": "uint128"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

async def check_positions():
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        position_ids = [26163662, 26162528]
        user_id = "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51"

        # Get NPM contract
        npm_contract = w3.eth.contract(address=NPM_ADDRESS, abi=NPM_ABI)

        for position_id in position_ids:
            print(f"\n{'='*60}")
            print(f"Checking position {position_id}...")

            # Check database status
            query = """
            SELECT token_id, status, pool_name, current_value_usdc, entry_amount_usdc, exit_date
            FROM positions
            WHERE token_id = $1 AND user_id = $2
            """
            db_position = await conn.fetchrow(query, position_id, user_id)

            if db_position:
                print(f"\nDatabase status:")
                print(f"  Status: {db_position['status']}")
                print(f"  Pool name: {db_position['pool_name']}")
                print(f"  Current value: {db_position['current_value_usdc']}")
                print(f"  Entry amount: {db_position['entry_amount_usdc']}")
                print(f"  Exit date: {db_position['exit_date']}")

            # Check on-chain status
            print(f"\nOn-chain status:")
            try:
                position_data = npm_contract.functions.positions(position_id).call()
                liquidity = position_data[7]
                print(f"  Liquidity: {liquidity}")

                if liquidity == 0:
                    print(f"  → Position is CLOSED on-chain (liquidity = 0)")
                else:
                    print(f"  → Position is ACTIVE on-chain")
                    print(f"  Token0: {position_data[2]}")
                    print(f"  Token1: {position_data[3]}")

            except Exception as e:
                if "execution reverted" in str(e):
                    print(f"  → Position doesn't exist on-chain (burned NFT)")
                else:
                    print(f"  Error checking on-chain: {e}")

            # Check for close transactions
            print(f"\nChecking for close transactions...")
            tx_query = """
            SELECT tx_hash, tx_type, event_data, created_at
            FROM transactions
            WHERE event_data->>'nft_token_id' = $1
            OR (tx_type = 'POSITION_CLOSED' AND event_data @> jsonb_build_object('nft_token_id', $1))
            ORDER BY created_at DESC
            LIMIT 5
            """
            transactions = await conn.fetch(tx_query, str(position_id))

            if transactions:
                for tx in transactions:
                    print(f"  {tx['tx_hash'][:10]}... - {tx['tx_type']} at {tx['created_at']}")
            else:
                print(f"  No transactions found with nft_token_id {position_id}")

        return True

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if conn:
            await conn.close()

async def main():
    print("Checking position status...")
    await check_positions()

if __name__ == "__main__":
    asyncio.run(main())