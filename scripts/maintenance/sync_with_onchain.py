#!/usr/bin/env python3
"""Sync database balance with actual on-chain balance."""

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
USDC_ABI = [{
    "inputs": [{"name": "account", "type": "address"}],
    "name": "balanceOf",
    "outputs": [{"name": "", "type": "uint256"}],
    "type": "function"
}]

async def sync_balance():
    """Sync database balance with actual on-chain balance."""
    
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
    
    print("Connected to staging database\n")
    
    try:
        user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
        
        # Get user info
        user = await conn.fetchrow("""
            SELECT 
                user_id,
                cdp_wallet_address,
                usdc_balance
            FROM users 
            WHERE user_id = $1
        """, user_id)
        
        if not user or not user['cdp_wallet_address']:
            print(f"❌ User {user_id} not found or has no CDP wallet")
            return
        
        cdp_wallet = user['cdp_wallet_address']
        current_db_balance = Decimal(str(user['usdc_balance']))
        
        print(f"User: {user_id}")
        print(f"CDP Wallet: {cdp_wallet}")
        print(f"Current DB Balance: {current_db_balance:.6f} USDC")
        
        # Get actual on-chain balance
        balance_wei = usdc.functions.balanceOf(cdp_wallet).call()
        actual_balance = Decimal(balance_wei) / Decimal(10 ** 6)
        
        print(f"Actual On-Chain Balance: {actual_balance:.6f} USDC")
        
        difference = current_db_balance - actual_balance
        print(f"Difference: {difference:.6f} USDC")
        
        if abs(difference) > Decimal('0.000001'):
            print(f"\n🔧 Syncing database with on-chain balance...")
            
            # Update database with actual balance
            await conn.execute("""
                UPDATE users 
                SET usdc_balance = $2
                WHERE user_id = $1
            """, user_id, float(actual_balance))
            
            print(f"✅ Balance synced to {actual_balance:.6f} USDC")
        else:
            print(f"✅ Balance already in sync")
        
        # Verify the update
        updated = await conn.fetchrow("""
            SELECT usdc_balance 
            FROM users 
            WHERE user_id = $1
        """, user_id)
        
        print(f"\n📊 Final Database Balance: {updated['usdc_balance']:.6f} USDC")
        print(f"   Actual On-Chain Balance: {actual_balance:.6f} USDC")
        print(f"   Match: {'YES ✅' if abs(Decimal(str(updated['usdc_balance'])) - actual_balance) < Decimal('0.000001') else 'NO ❌'}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise
    finally:
        await conn.close()
        print("\nDisconnected from database")


if __name__ == "__main__":
    print("🔄 Syncing database balance with on-chain balance")
    print("=" * 60)
    asyncio.run(sync_balance())