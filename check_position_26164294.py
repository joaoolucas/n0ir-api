#!/usr/bin/env python3
"""Check position 26164294 status and transactions."""

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

async def check_position():
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        
        position_id = 26164294
        user_id = "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51"
        
        print(f"Checking position {position_id}...")
        print("=" * 60)
        
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
            npm_contract = w3.eth.contract(address=NPM_ADDRESS, abi=NPM_ABI)
            position_data = npm_contract.functions.positions(position_id).call()
            liquidity = position_data[7]
            print(f"  Liquidity: {liquidity}")
            
            if liquidity == 0:
                print(f"  → Position is CLOSED on-chain (liquidity = 0)")
            else:
                print(f"  → Position is ACTIVE on-chain")
        except Exception as e:
            if "execution reverted" in str(e):
                print(f"  → Position doesn't exist on-chain (burned NFT)")
            else:
                print(f"  Error checking on-chain: {e}")
        
        # Check for POSITION_CLOSED transactions
        print(f"\nChecking for POSITION_CLOSED transactions...")
        tx_query = """
        SELECT tx_hash, tx_type, event_data, created_at
        FROM transactions
        WHERE (tx_type = 'POSITION_CLOSED' AND event_data->>'nft_token_id' = $1)
        OR (event_data->>'nft_token_id' = $1)
        ORDER BY created_at DESC
        """
        transactions = await conn.fetch(tx_query, str(position_id))
        
        if transactions:
            for tx in transactions:
                print(f"  {tx['tx_hash'][:10]}... - {tx['tx_type']} at {tx['created_at']}")
                if tx['tx_type'] == 'POSITION_CLOSED':
                    print(f"    → Found POSITION_CLOSED transaction!")
        else:
            print(f"  No transactions found for position {position_id}")
        
        # If position should be closed, update it
        if db_position and db_position['status'] == 'ACTIVE':
            # Check if there's a POSITION_CLOSED transaction
            closed_tx = next((tx for tx in transactions if tx['tx_type'] == 'POSITION_CLOSED'), None)
            if closed_tx:
                print(f"\n⚠️ Position has POSITION_CLOSED transaction but is still ACTIVE!")
                print(f"   This should be fixed by the new auto-close feature once deployed.")
        
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
    await check_position()

if __name__ == "__main__":
    asyncio.run(main())
