#!/usr/bin/env python3
"""Verify all data in database matches real on-chain transactions."""

import asyncio
import asyncpg
from urllib.parse import urlparse
from web3 import Web3
from decimal import Decimal
import json

# Database URL from Railway staging
DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

# Base Mainnet RPC
BASE_RPC = "https://base-mainnet.g.alchemy.com/v2/PbEIlFPXdZpA6ld_nxViZD73mlaupBrY"

# Contract addresses
USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
LIQUIDITY_MANAGER = "0x09cEB55ecbc32f201fCadf795eC49Ce2b6070A5C"
AERODROME_ROUTER = "0xa4fdd479eda160671636e2ecf8f993cbf86258a8"

async def verify_onchain_data():
    """Verify all database transactions match real on-chain data."""
    
    # Connect to Web3
    w3 = Web3(Web3.HTTPProvider(BASE_RPC))
    print(f"Connected to Base Mainnet: {w3.is_connected()}")
    print(f"Current block: {w3.eth.block_number}")
    print("=" * 80)
    
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
        
        # Get user's CDP wallet
        user = await conn.fetchrow("""
            SELECT cdp_wallet_address 
            FROM users 
            WHERE user_id = $1
        """, user_id)
        
        cdp_wallet = user['cdp_wallet_address']
        print(f"User: {user_id}")
        print(f"CDP Wallet: {cdp_wallet}\n")
        
        # 1. Verify DEPOSIT transactions
        print("🔍 VERIFYING DEPOSIT TRANSACTIONS...")
        print("-" * 40)
        
        deposits = await conn.fetch("""
            SELECT 
                tx_hash,
                block_number,
                event_data->>'amount_usdc' as amount,
                event_data->>'from_address' as from_addr,
                event_data->>'to_address' as to_addr
            FROM transactions 
            WHERE user_id = $1
            AND tx_type = 'DEPOSIT'
            AND status = 'CONFIRMED'
            AND tx_hash IS NOT NULL
            ORDER BY block_number DESC
            LIMIT 5
        """, user_id)
        
        for dep in deposits:
            if not dep['tx_hash']:
                continue
                
            try:
                # Get actual transaction receipt
                receipt = w3.eth.get_transaction_receipt(dep['tx_hash'])
                tx = w3.eth.get_transaction(dep['tx_hash'])
                
                print(f"\n📄 TX: {dep['tx_hash'][:10]}...")
                print(f"  DB Block: {dep['block_number']}")
                print(f"  Chain Block: {receipt.blockNumber}")
                print(f"  Match: {'✅' if dep['block_number'] == receipt.blockNumber else '❌'}")
                print(f"  DB Amount: {dep['amount']} USDC")
                print(f"  To Address: {dep['to_addr']}")
                print(f"  Status: {'✅ SUCCESS' if receipt.status == 1 else '❌ FAILED'}")
                
                # Check if this is a real USDC transfer by looking at logs
                usdc_transfer_found = False
                for log in receipt.logs:
                    if log['address'].lower() == USDC_ADDRESS.lower():
                        # This is a USDC contract event
                        if len(log['topics']) >= 3:
                            # Transfer event has 3 topics: signature, from, to
                            to_address = '0x' + log['topics'][2].hex()[-40:]
                            if to_address.lower() == cdp_wallet.lower():
                                usdc_transfer_found = True
                                # Decode amount from data field
                                amount_wei = int(log['data'].hex(), 16)
                                amount_usdc = Decimal(amount_wei) / Decimal(10**6)
                                print(f"  Chain Amount: {amount_usdc:.6f} USDC")
                                db_amount = Decimal(dep['amount'])
                                print(f"  Amount Match: {'✅' if abs(amount_usdc - db_amount) < 0.01 else '❌'}")
                                break
                
                if not usdc_transfer_found:
                    print(f"  ⚠️ No USDC transfer to CDP wallet found in this TX")
                    
            except Exception as e:
                print(f"  ❌ Error verifying TX: {e}")
        
        # 2. Verify WITHDRAWAL transactions
        print("\n\n🔍 VERIFYING WITHDRAWAL TRANSACTIONS...")
        print("-" * 40)
        
        withdrawals = await conn.fetch("""
            SELECT 
                tx_hash,
                block_number,
                event_data->>'amount_usdc' as amount
            FROM transactions 
            WHERE user_id = $1
            AND tx_type = 'WITHDRAWAL'
            AND status = 'CONFIRMED'
            AND tx_hash IS NOT NULL
            ORDER BY block_number DESC
            LIMIT 5
        """, user_id)
        
        for wd in withdrawals:
            if not wd['tx_hash']:
                continue
                
            try:
                receipt = w3.eth.get_transaction_receipt(wd['tx_hash'])
                
                print(f"\n📄 TX: {wd['tx_hash'][:10]}...")
                print(f"  DB Block: {wd['block_number']}")
                print(f"  Chain Block: {receipt.blockNumber}")
                print(f"  Match: {'✅' if wd['block_number'] == receipt.blockNumber else '❌'}")
                print(f"  Status: {'✅ SUCCESS' if receipt.status == 1 else '❌ FAILED'}")
                
            except Exception as e:
                print(f"  ❌ Error verifying TX: {e}")
        
        # 3. Verify POSITION transactions
        print("\n\n🔍 VERIFYING POSITION TRANSACTIONS...")
        print("-" * 40)
        
        positions = await conn.fetch("""
            SELECT 
                tx_hash,
                tx_type,
                block_number,
                event_data->>'tokenId' as token_id,
                event_data->>'usdcIn' as usdc_in,
                event_data->>'usdcOut' as usdc_out
            FROM transactions 
            WHERE user_id = $1
            AND tx_type IN ('POSITION_CREATED', 'POSITION_CLOSED')
            AND status = 'CONFIRMED'
            AND tx_hash IS NOT NULL
            ORDER BY block_number DESC
            LIMIT 5
        """, user_id)
        
        for pos in positions:
            if not pos['tx_hash']:
                continue
                
            try:
                receipt = w3.eth.get_transaction_receipt(pos['tx_hash'])
                
                print(f"\n📄 TX: {pos['tx_hash'][:10]}... ({pos['tx_type']})")
                print(f"  Token ID: {pos['token_id']}")
                print(f"  DB Block: {pos['block_number']}")
                print(f"  Chain Block: {receipt.blockNumber}")
                print(f"  Match: {'✅' if pos['block_number'] == receipt.blockNumber else '❌'}")
                print(f"  From Contract: {receipt['from'][:10]}...")
                print(f"  To Contract: {receipt['to'][:10]}...")
                
                # Check if liquidity manager contract was involved
                liquidity_manager_involved = False
                for log in receipt.logs:
                    if log['address'].lower() == LIQUIDITY_MANAGER.lower():
                        liquidity_manager_involved = True
                        break
                
                print(f"  Liquidity Manager: {'✅ Involved' if liquidity_manager_involved else '⚠️ Not found'}")
                print(f"  Status: {'✅ SUCCESS' if receipt.status == 1 else '❌ FAILED'}")
                
            except Exception as e:
                print(f"  ❌ Error verifying TX: {e}")
        
        # 4. Verify AERO_SWAP transactions
        print("\n\n🔍 VERIFYING AERO SWAP TRANSACTIONS...")
        print("-" * 40)
        
        aero_swaps = await conn.fetch("""
            SELECT 
                tx_hash,
                block_number,
                event_data->>'amount_usdc' as amount,
                event_data->>'position_token_id' as token_id,
                event_data->>'from_address' as from_addr
            FROM transactions 
            WHERE user_id = $1
            AND tx_type = 'AERO_SWAP'
            AND status = 'CONFIRMED'
            ORDER BY block_number DESC
        """, user_id)
        
        print(f"\nFound {len(aero_swaps)} AERO_SWAP transactions\n")
        
        for swap in aero_swaps:
            if not swap['tx_hash']:
                print(f"  ⚠️ AERO_SWAP for position {swap['token_id']} has no tx_hash")
                continue
                
            try:
                receipt = w3.eth.get_transaction_receipt(swap['tx_hash'])
                
                print(f"\n📄 TX: {swap['tx_hash'][:10]}...")
                print(f"  Position Token ID: {swap['token_id']}")
                print(f"  DB Block: {swap['block_number']}")
                print(f"  Chain Block: {receipt.blockNumber}")
                print(f"  Match: {'✅' if swap['block_number'] == receipt.blockNumber else '❌'}")
                print(f"  Amount: {swap['amount']} USDC")
                print(f"  From Address: {swap['from_addr']}")
                
                # Check if Aerodrome router was involved
                aerodrome_involved = swap['from_addr'] and swap['from_addr'].lower() == AERODROME_ROUTER.lower()
                print(f"  Aerodrome Router: {'✅ Confirmed' if aerodrome_involved else '⚠️ Different router'}")
                
                # Verify USDC transfer in logs
                usdc_transfer_found = False
                for log in receipt.logs:
                    if log['address'].lower() == USDC_ADDRESS.lower():
                        if len(log['topics']) >= 3:
                            to_address = '0x' + log['topics'][2].hex()[-40:]
                            if to_address.lower() == cdp_wallet.lower():
                                usdc_transfer_found = True
                                amount_wei = int(log['data'].hex(), 16)
                                amount_usdc = Decimal(amount_wei) / Decimal(10**6)
                                print(f"  Chain USDC Transfer: {amount_usdc:.6f} USDC")
                                break
                
                print(f"  USDC Transfer: {'✅ Found' if usdc_transfer_found else '❌ Not found'}")
                print(f"  Status: {'✅ SUCCESS' if receipt.status == 1 else '❌ FAILED'}")
                
            except Exception as e:
                print(f"  ❌ Error verifying TX: {e}")
        
        # 5. Summary
        print("\n\n📊 DATA VERIFICATION SUMMARY")
        print("=" * 80)
        
        # Count all transaction types
        tx_counts = await conn.fetch("""
            SELECT 
                tx_type,
                COUNT(*) as count,
                COUNT(tx_hash) as with_hash,
                COUNT(block_number) as with_block
            FROM transactions 
            WHERE user_id = $1
            AND status = 'CONFIRMED'
            GROUP BY tx_type
            ORDER BY count DESC
        """, user_id)
        
        print("\nTransaction Type Breakdown:")
        for tc in tx_counts:
            print(f"  {tc['tx_type']:20} Total: {tc['count']:3}  With Hash: {tc['with_hash']:3}  With Block: {tc['with_block']:3}")
        
        # Check for any mocked data (transactions without hashes or blocks)
        mocked = await conn.fetch("""
            SELECT tx_type, COUNT(*) as count
            FROM transactions 
            WHERE user_id = $1
            AND status = 'CONFIRMED'
            AND (tx_hash IS NULL OR block_number IS NULL)
            GROUP BY tx_type
        """, user_id)
        
        if mocked:
            print("\n⚠️ POTENTIAL MOCKED DATA FOUND:")
            for m in mocked:
                print(f"  {m['tx_type']}: {m['count']} transactions without hash or block")
        else:
            print("\n✅ All confirmed transactions have tx_hash and block_number")
        
        # Final balance check
        print("\n💰 FINAL BALANCE VERIFICATION:")
        
        # Get actual on-chain balance
        usdc_abi = [{
            "inputs": [{"name": "account", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "", "type": "uint256"}],
            "type": "function"
        }]
        usdc_contract = w3.eth.contract(address=USDC_ADDRESS, abi=usdc_abi)
        balance_wei = usdc_contract.functions.balanceOf(cdp_wallet).call()
        actual_balance = Decimal(balance_wei) / Decimal(10**6)
        
        db_user = await conn.fetchrow("""
            SELECT usdc_balance 
            FROM users 
            WHERE user_id = $1
        """, user_id)
        
        print(f"  On-Chain Balance: {actual_balance:.6f} USDC")
        print(f"  Database Balance: {db_user['usdc_balance']:.6f} USDC")
        print(f"  Match: {'✅ EXACT MATCH' if abs(actual_balance - Decimal(str(db_user['usdc_balance']))) < 0.000001 else '❌ MISMATCH'}")
        
        print("\n" + "=" * 80)
        print("VERIFICATION COMPLETE")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise
    finally:
        await conn.close()
        print("\nDisconnected from database")


if __name__ == "__main__":
    print("🔍 VERIFYING ALL DATABASE DATA AGAINST ON-CHAIN")
    print("=" * 80)
    asyncio.run(verify_onchain_data())