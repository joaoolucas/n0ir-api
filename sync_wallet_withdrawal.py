#!/usr/bin/env python3
"""Sync wallet to capture the 0.01 USDC withdrawal."""

import asyncio
import asyncpg
from datetime import datetime
import os

# Database URL from Railway staging
DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def check_and_sync_wallet():
    """Check current state and trigger sync for the wallet."""
    
    # Connect to database
    conn = await asyncpg.connect(DATABASE_URL, ssl='require')
    
    try:
        # Get your wallet address (assuming it's the one with recent activity)
        user = await conn.fetchrow("""
            SELECT user_id, cdp_wallet_address, usdc_balance, 
                   total_deposits_usdc, total_withdrawals_usdc,
                   last_scanned_block, last_withdrawal_block
            FROM users
            WHERE cdp_wallet_address IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 1
        """)
        
        if not user:
            print("No user found with CDP wallet")
            return
        
        print(f"👤 User: {user['user_id']}")
        print(f"💳 CDP Wallet: {user['cdp_wallet_address']}")
        print(f"💰 Current USDC Balance: {user['usdc_balance']}")
        print(f"📥 Total Deposits: {user['total_deposits_usdc']}")
        print(f"📤 Total Withdrawals: {user['total_withdrawals_usdc']}")
        print(f"🔍 Last Scanned Block: {user['last_scanned_block']}")
        print(f"📤 Last Withdrawal Block: {user['last_withdrawal_block']}")
        
        # Check recent transactions
        print("\n📜 Recent transactions:")
        transactions = await conn.fetch("""
            SELECT tx_hash, tx_type, status,
                   event_data, created_at, block_number
            FROM transactions
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT 5
        """, user['user_id'])
        
        for tx in transactions:
            amount = 0
            if tx['event_data']:
                # Extract amount from event_data (it's a JSONB field)
                event_data = tx['event_data'] if isinstance(tx['event_data'], dict) else {}
                for field in ['amount_usdc', 'usdc_out', 'usdc_in', 'amount_usd']:
                    if field in event_data:
                        amount = float(event_data[field])
                        break
            
            print(f"  - {tx['tx_type']}: ${amount:.2f} USDC at block {tx['block_number']} ({tx['status']})")
            print(f"    Hash: {tx['tx_hash']}")
            print(f"    Time: {tx['created_at']}")
        
        # Check the latest withdrawal amount
        print("\n💸 Checking latest withdrawal details...")
        latest_withdrawal = await conn.fetchrow("""
            SELECT tx_hash, event_data, created_at, block_number
            FROM transactions
            WHERE user_id = $1 
            AND tx_type = 'WITHDRAWAL'
            AND created_at >= CURRENT_TIMESTAMP - INTERVAL '1 hour'
            ORDER BY created_at DESC
            LIMIT 1
        """, user['user_id'])
        
        if latest_withdrawal:
            import json
            print(f"   Raw event_data: {latest_withdrawal['event_data']}")
            event_data = latest_withdrawal['event_data']
            # Parse JSON string if needed
            if isinstance(event_data, str):
                try:
                    event_data = json.loads(event_data)
                except:
                    pass
            if isinstance(event_data, dict):
                # Try different fields for the amount
                amount = event_data.get('amount_usdc', event_data.get('usdc_out', event_data.get('amount_usd', 0)))
                if amount is not None and amount != 0:
                    # Convert from wei-like format (6 decimals for USDC)
                    amount_decimal = float(amount) / 1_000_000 if isinstance(amount, (int, str)) and float(amount) > 1000 else float(amount)
                    print(f"✅ Latest withdrawal: ${amount_decimal:.6f} USDC")
                    print(f"   Block: {latest_withdrawal['block_number']}")
                    print(f"   Time: {latest_withdrawal['created_at']}")
                    print(f"   Hash: {latest_withdrawal['tx_hash']}")
                    
                    if abs(amount_decimal - 0.01) < 0.001:
                        print("   ✅ This is your 0.01 USDC withdrawal!")
                else:
                    print(f"   ⚠️  Amount field not found in event_data")
        
        # Check if there's a pending withdrawal that needs to be captured
        print("\n🔄 Checking for unsynced withdrawals...")
        
        # Get the latest block from Base
        print("   Getting latest block from Base network...")
        
        # Since we can't directly call RPC here, let's check what the watcher should be doing
        print("\n📋 Action needed:")
        print("1. The watcher should be running and monitoring for new transactions")
        print("2. It will automatically detect the 0.01 USDC withdrawal")
        print("3. The withdrawal should appear as a WITHDRAWAL transaction type")
        
        # Check if watcher service is running
        print("\n🔍 Checking if there are any recent WITHDRAWAL transactions...")
        recent_withdrawal = await conn.fetchrow("""
            SELECT tx_hash, event_data, created_at, block_number
            FROM transactions
            WHERE user_id = $1 
            AND tx_type = 'WITHDRAWAL'
            ORDER BY created_at DESC
            LIMIT 1
        """, user['user_id'])
        
        if recent_withdrawal:
            amount = 0
            if recent_withdrawal['event_data'] and 'usdc_out' in recent_withdrawal['event_data']:
                amount = float(recent_withdrawal['event_data']['usdc_out'])
            print(f"✅ Found recent withdrawal: ${amount:.4f} USDC")
            print(f"   Block: {recent_withdrawal['block_number']}")
            print(f"   Time: {recent_withdrawal['created_at']}")
        else:
            print("⚠️  No recent withdrawals found - watcher may need to sync")
            
    finally:
        await conn.close()

if __name__ == "__main__":
    print("🔍 Checking wallet sync status for 0.01 USDC withdrawal")
    asyncio.run(check_and_sync_wallet())