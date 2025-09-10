#!/usr/bin/env python3
"""Check actual on-chain balance and compare with database."""

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
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    }
]


async def check_balance():
    """Check actual balance on chain vs database."""
    
    # Connect to Web3
    w3 = Web3(Web3.HTTPProvider(BASE_RPC))
    print(f"Connected to Base: {w3.is_connected()}")
    
    # USDC contract
    usdc = w3.eth.contract(address=USDC_ADDRESS, abi=USDC_ABI)
    decimals = usdc.functions.decimals().call()
    print(f"USDC decimals: {decimals}")
    
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
    
    print("\nConnected to staging database")
    
    try:
        # Get user info
        user = await conn.fetchrow("""
            SELECT 
                user_id,
                cdp_wallet_address,
                usdc_balance,
                total_deposits_usdc,
                total_withdrawals_usdc,
                last_deposit_block,
                last_withdrawal_block,
                last_scanned_block
            FROM users 
            WHERE user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
        """)
        
        print(f"\n=== User: {user['user_id']} ===")
        print(f"CDP Wallet: {user['cdp_wallet_address']}")
        print(f"\n📊 Database Values:")
        print(f"  DB Balance: {user['usdc_balance']} USDC")
        print(f"  Total Deposits: {user['total_deposits_usdc']} USDC")
        print(f"  Total Withdrawals: {user['total_withdrawals_usdc']} USDC")
        print(f"  Calculated: {user['total_deposits_usdc'] - user['total_withdrawals_usdc']} USDC")
        
        # Check actual on-chain balance
        cdp_wallet = user['cdp_wallet_address']
        if cdp_wallet:
            balance_wei = usdc.functions.balanceOf(cdp_wallet).call()
            balance_usdc = Decimal(balance_wei) / Decimal(10 ** decimals)
            print(f"\n⛓️  Actual On-Chain Balance:")
            print(f"  CDP Wallet {cdp_wallet}: {balance_usdc} USDC")
            
            # Check difference
            db_balance = Decimal(str(user['usdc_balance']))
            difference = db_balance - balance_usdc
            print(f"\n❗ Difference: {difference} USDC")
            if abs(difference) > Decimal('0.000001'):
                print(f"  ⚠️ MISMATCH: DB shows {db_balance} but chain shows {balance_usdc}")
        
        # Get all transactions to analyze
        print("\n📜 Analyzing Transaction History:")
        all_txs = await conn.fetch("""
            SELECT 
                tx_hash,
                tx_type,
                event_data->>'amount_usdc' as amount,
                block_number,
                created_at,
                status
            FROM transactions 
            WHERE user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
            AND tx_type IN ('DEPOSIT', 'WITHDRAWAL')
            ORDER BY block_number DESC NULLS LAST, created_at DESC
        """)
        
        # Calculate totals
        total_deposits = Decimal('0')
        total_withdrawals = Decimal('0')
        
        print(f"\nFound {len(all_txs)} deposit/withdrawal transactions:")
        for tx in all_txs:
            amount = Decimal(tx['amount'] or '0')
            status = tx['status']
            tx_type = tx['tx_type']
            
            print(f"  {tx_type:10} {amount:12.6f} USDC - Block {tx['block_number'] or 'PENDING':8} - Status: {status}")
            
            if status == 'CONFIRMED':
                if tx_type == 'DEPOSIT':
                    total_deposits += amount
                elif tx_type == 'WITHDRAWAL':
                    total_withdrawals += amount
        
        print(f"\n📊 Recalculated from Transactions:")
        print(f"  Total Deposits (CONFIRMED): {total_deposits} USDC")
        print(f"  Total Withdrawals (CONFIRMED): {total_withdrawals} USDC")
        print(f"  Calculated Balance: {total_deposits - total_withdrawals} USDC")
        
        # Check for any non-confirmed transactions
        non_confirmed = [tx for tx in all_txs if tx['status'] != 'CONFIRMED']
        if non_confirmed:
            print(f"\n⚠️ Found {len(non_confirmed)} non-CONFIRMED transactions that might be affecting balance!")
            for tx in non_confirmed:
                print(f"  {tx['tx_type']}: {tx['amount']} USDC - Status: {tx['status']}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise
    finally:
        await conn.close()
        print("\n✅ Analysis complete")


if __name__ == "__main__":
    print("🔍 Checking actual wallet balance vs database")
    asyncio.run(check_balance())