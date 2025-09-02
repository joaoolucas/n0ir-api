import asyncio
from web3 import Web3
from app.core.config import settings
import json

async def check():
    # Connect to Base
    import os
    base_rpc = os.getenv("BASE_RPC_URL", "https://base-mainnet.g.alchemy.com/v2/PbEIlFPXdZpA6ld_nxViZD73mlaupBrY")
    w3 = Web3(Web3.HTTPProvider(base_rpc))
    
    cdp_wallet = '0x1409f9dfb8C05a31A5fb4b3fFEEA60298bEF30Bb'
    
    # Position Manager contract address on Base
    position_manager_address = "0x00c1Bc0CA9F703919C2BA320e5f200865F778AaE"
    
    # Minimal ABI for balanceOf and tokenOfOwnerByIndex
    abi = [
        {
            "inputs": [{"name": "owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "", "type": "uint256"}],
            "type": "function"
        },
        {
            "inputs": [
                {"name": "owner", "type": "address"},
                {"name": "index", "type": "uint256"}
            ],
            "name": "tokenOfOwnerByIndex",
            "outputs": [{"name": "", "type": "uint256"}],
            "type": "function"
        }
    ]
    
    position_manager = w3.eth.contract(
        address=Web3.to_checksum_address(position_manager_address),
        abi=abi
    )
    
    # Check balance
    balance = position_manager.functions.balanceOf(
        Web3.to_checksum_address(cdp_wallet)
    ).call()
    
    print(f"CDP Wallet {cdp_wallet}")
    print(f"Position NFT Balance: {balance}")
    
    if balance > 0:
        print("\nPosition NFT Token IDs:")
        for i in range(min(balance, 5)):
            token_id = position_manager.functions.tokenOfOwnerByIndex(
                Web3.to_checksum_address(cdp_wallet), 
                i
            ).call()
            print(f"  - Token ID: {token_id}")
    
    # Also check the LiquidityManager for staked positions
    liquidity_manager_address = "0xEBdf3F9c9136b77d02114c32f1dE5Ff2e6f6Da78"
    lm_abi = [
        {
            "inputs": [{"name": "user", "type": "address"}],
            "name": "getUserPositions",
            "outputs": [{"name": "", "type": "uint256[]"}],
            "type": "function"
        }
    ]
    
    liquidity_manager = w3.eth.contract(
        address=Web3.to_checksum_address(liquidity_manager_address),
        abi=lm_abi
    )
    
    try:
        staked_positions = liquidity_manager.functions.getUserPositions(
            Web3.to_checksum_address(cdp_wallet)
        ).call()
        print(f"\nStaked positions: {staked_positions}")
    except Exception as e:
        print(f"\nCould not check staked positions: {e}")

if __name__ == "__main__":
    asyncio.run(check())