#!/usr/bin/env python3
"""Force balance sync with actual on-chain balance."""

import asyncio
import asyncpg
from urllib.parse import urlparse
from web3 import Web3
from decimal import Decimal

# Database URL from Railway staging
DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

# Base Mainnet RPC
BASE_RPC = "https://base-mainnet.g.alchemy.com/v2/PbEIlFPXdZpA6ld_nxViZD73mlaupBrY"

# USDC contract on Base
USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

# USDC ABI for balanceOf
USDC_ABI = [
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    }
]


async def force_sync():
    """Force sync balance with blockchain."""
    
    # Connect to Web3
    w3 = Web3(Web3.HTTPProvider(BASE_RPC))
    print(f"Connected to Base: {w3.is_connected()}")
    
    # USDC contract
    usdc = w3.eth.contract(address=USDC_ADDRESS, abi=USDC_ABI)
    
    # Parse database URL
    parsed = urlparse(DATABASE_URL)
    
    # Connect to database
    conn = await asyncpg.connect(
        host=parsed.hostname,
        port=parsed.port,
        user=parsed.username,
        password=parsed.password,
        database=parsed.path.lstrip('/'),
        ssl='require'
    )
    
    print("Connected to staging database")
    
    try:
        # Get user info
        user = await conn.fetchrow("""
            SELECT 
                user_id,
                cdp_wallet_address,
                usdc_balance,
                total_deposits_usdc,
                total_withdrawals_usdc
            FROM users 
            WHERE user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
        """)
        
        print(f"\n=== User: {user['user_id']} ===")
        print(f"CDP Wallet: {user['cdp_wallet_address']}")
        print(f"Current DB Balance: {user['usdc_balance']} USDC")
        
        # Get actual on-chain balance
        cdp_wallet = user['cdp_wallet_address']
        if cdp_wallet:
            balance_wei = usdc.functions.balanceOf(cdp_wallet).call()
            balance_usdc = Decimal(balance_wei) / Decimal(10 ** 6)
            print(f"Actual On-Chain Balance: {balance_usdc} USDC")
            
            # Update database with actual balance
            print(f"\n🔧 Updating database to match on-chain...")
            
            # Calculate the adjustment needed
            calculated = user['total_deposits_usdc'] - user['total_withdrawals_usdc']
            adjustment = balance_usdc - calculated
            
            if adjustment > 0:
                # Need to add to deposits
                new_deposits = user['total_deposits_usdc'] + adjustment
                await conn.execute("""
                    UPDATE users 
                    SET 
                        usdc_balance = $1,
                        total_deposits_usdc = $2
                    WHERE user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
                """, balance_usdc, new_deposits)
                print(f"✅ Added {adjustment} to deposits to match actual balance")
            else:
                # Need to add to withdrawals
                new_withdrawals = user['total_withdrawals_usdc'] - adjustment
                await conn.execute("""
                    UPDATE users 
                    SET 
                        usdc_balance = $1,
                        total_withdrawals_usdc = $2
                    WHERE user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
                """, balance_usdc, new_withdrawals)
                print(f"✅ Added {-adjustment} to withdrawals to match actual balance")
            
            print(f"✅ Balance synced to {balance_usdc} USDC")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise
    finally:
        await conn.close()
        print("\n✅ Complete")


if __name__ == "__main__":
    print("🔧 Forcing balance sync with blockchain")
    asyncio.run(force_sync())