#!/usr/bin/env python3
"""Investigate the balance and transaction issues."""

import asyncio
import asyncpg
from datetime import datetime, timedelta
import json

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def investigate():
    conn = await asyncpg.connect(DATABASE_URL, ssl='require')
    
    try:
        print("=" * 80)
        print("BALANCE AND TRANSACTION INVESTIGATION REPORT")
        print("=" * 80)
        
        # 1. Check user data
        print("\n1️⃣ USER DATA:")
        user = await conn.fetchrow("""
            SELECT user_id, cdp_wallet_address, usdc_balance, 
                   total_deposits_usdc, total_withdrawals_usdc,
                   last_deposit_block, last_withdrawal_block,
                   last_scanned_block, updated_at
            FROM users
            WHERE cdp_wallet_address IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 1
        """)
        
        if user:
            print(f"   User ID: {user['user_id']}")
            print(f"   CDP Wallet: {user['cdp_wallet_address']}")
            print(f"   USDC Balance: {user['usdc_balance']} USDC")
            print(f"   Total Deposits: {user['total_deposits_usdc']} USDC")
            print(f"   Total Withdrawals: {user['total_withdrawals_usdc']} USDC")
            print(f"   Last Deposit Block: {user['last_deposit_block']}")
            print(f"   Last Withdrawal Block: {user['last_withdrawal_block']}")
            print(f"   Last Scanned Block: {user['last_scanned_block']}")
            print(f"   Last Updated: {user['updated_at']}")
            
            # Calculate expected balance
            expected_balance = float(user['total_deposits_usdc'] or 0) - float(user['total_withdrawals_usdc'] or 0)
            print(f"\n   📊 BALANCE CALCULATION:")
            print(f"      Total Deposits: {user['total_deposits_usdc']} USDC")
            print(f"      - Total Withdrawals: {user['total_withdrawals_usdc']} USDC")
            print(f"      = Expected Balance: {expected_balance:.6f} USDC")
            print(f"      Actual Balance: {user['usdc_balance']} USDC")
            if abs(float(user['usdc_balance']) - expected_balance) > 0.001:
                print(f"      ⚠️ MISMATCH: Difference of {float(user['usdc_balance']) - expected_balance:.6f} USDC")
        
        # 2. Check all recent transactions
        print("\n2️⃣ ALL RECENT TRANSACTIONS (Last 48 hours):")
        recent_txs = await conn.fetch("""
            SELECT tx_hash, tx_type, status, event_data, 
                   block_number, created_at, processed_at
            FROM transactions
            WHERE user_id = $1
            AND created_at >= NOW() - INTERVAL '48 hours'
            ORDER BY created_at DESC
        """, user['user_id'])
        
        deposits_count = 0
        withdrawals_count = 0
        deposits_total = 0
        withdrawals_total = 0
        
        for tx in recent_txs:
            # Parse event_data
            event_data = tx['event_data']
            if isinstance(event_data, str):
                try:
                    event_data = json.loads(event_data)
                except:
                    pass
            
            amount = 0
            if isinstance(event_data, dict):
                amount = event_data.get('amount_usdc', 
                        event_data.get('usdc_in', 
                        event_data.get('usdc_out', 
                        event_data.get('amount_usd', 0))))
                
                # Convert from wei format if needed
                if isinstance(amount, str) and amount.isdigit():
                    amount = float(amount) / 1_000_000
                elif amount and amount > 1000:
                    amount = float(amount) / 1_000_000
                else:
                    amount = float(amount) if amount else 0
            
            tx_type_emoji = {
                'DEPOSIT': '💰',
                'WITHDRAWAL': '📤',
                'WITHDRAW': '📤',
                'POSITION_CREATED': '📈',
                'POSITION_CLOSED': '📉',
                'AERO_SWAP': '🔄'
            }.get(tx['tx_type'], '❓')
            
            print(f"\n   {tx_type_emoji} {tx['tx_type']} - Block {tx['block_number']}")
            print(f"      Amount: ${amount:.6f} USDC")
            print(f"      Status: {tx['status']}")
            print(f"      Hash: {tx['tx_hash'][:20]}...")
            print(f"      Created: {tx['created_at']}")
            
            if tx['tx_type'] == 'DEPOSIT':
                deposits_count += 1
                deposits_total += amount
            elif tx['tx_type'] in ['WITHDRAWAL', 'WITHDRAW']:
                withdrawals_count += 1
                withdrawals_total += amount
        
        print(f"\n   📊 TRANSACTION SUMMARY:")
        print(f"      Deposits: {deposits_count} transactions, Total: ${deposits_total:.6f} USDC")
        print(f"      Withdrawals: {withdrawals_count} transactions, Total: ${withdrawals_total:.6f} USDC")
        
        # 3. Check for the specific 0.01 withdrawal
        print("\n3️⃣ SEARCHING FOR 0.01 USDC WITHDRAWAL:")
        
        # Search by amount
        small_withdrawals = await conn.fetch("""
            SELECT tx_hash, block_number, event_data, created_at
            FROM transactions
            WHERE user_id = $1
            AND tx_type IN ('WITHDRAWAL', 'WITHDRAW')
            AND created_at >= NOW() - INTERVAL '24 hours'
        """, user['user_id'])
        
        found_001 = False
        for tx in small_withdrawals:
            event_data = tx['event_data']
            if isinstance(event_data, str):
                try:
                    event_data = json.loads(event_data)
                except:
                    continue
            
            if isinstance(event_data, dict):
                amount = event_data.get('amount_usdc', event_data.get('usdc_out', 0))
                if amount and abs(float(amount) - 0.01) < 0.001:
                    found_001 = True
                    print(f"   ✅ Found 0.01 USDC withdrawal!")
                    print(f"      Block: {tx['block_number']}")
                    print(f"      Hash: {tx['tx_hash']}")
                    print(f"      Time: {tx['created_at']}")
        
        if not found_001:
            print("   ❌ No 0.01 USDC withdrawal found in transactions table")
            
        # 4. Check for the 20 USDC deposit
        print("\n4️⃣ SEARCHING FOR 20 USDC DEPOSIT:")
        
        large_deposits = await conn.fetch("""
            SELECT tx_hash, block_number, event_data, created_at
            FROM transactions
            WHERE user_id = $1
            AND tx_type = 'DEPOSIT'
            AND created_at >= NOW() - INTERVAL '24 hours'
            ORDER BY created_at DESC
        """, user['user_id'])
        
        found_20 = False
        for tx in large_deposits:
            event_data = tx['event_data']
            if isinstance(event_data, str):
                try:
                    event_data = json.loads(event_data)
                except:
                    continue
            
            if isinstance(event_data, dict):
                amount = event_data.get('amount_usdc', event_data.get('usdc_in', 0))
                # Convert if needed
                if isinstance(amount, str) and amount.isdigit() and len(amount) > 4:
                    amount = float(amount) / 1_000_000
                elif amount and amount > 1000:
                    amount = float(amount) / 1_000_000
                else:
                    amount = float(amount) if amount else 0
                    
                if abs(amount - 20.0) < 0.1:
                    found_20 = True
                    print(f"   ✅ Found 20 USDC deposit!")
                    print(f"      Amount: ${amount:.6f} USDC")
                    print(f"      Block: {tx['block_number']}")
                    print(f"      Hash: {tx['tx_hash']}")
                    print(f"      Time: {tx['created_at']}")
        
        if not found_20:
            print("   ❌ No 20 USDC deposit found in transactions table")
            
        # 5. Check wallet_transfers table directly
        print("\n5️⃣ CHECKING WALLET_TRANSFERS TABLE:")
        transfers = await conn.fetch("""
            SELECT direction, amount_usdc, tx_hash, block_number, 
                   block_timestamp, created_at
            FROM wallet_transfers
            WHERE cdp_wallet_address = $1
            AND created_at >= NOW() - INTERVAL '24 hours'
            ORDER BY created_at DESC
            LIMIT 10
        """, user['cdp_wallet_address'])
        
        for transfer in transfers:
            direction_emoji = '💰' if transfer['direction'] == 'IN' else '📤'
            amount = float(transfer['amount_usdc']) / 1_000_000 if transfer['amount_usdc'] > 1000 else float(transfer['amount_usdc'])
            print(f"\n   {direction_emoji} {transfer['direction']} - ${amount:.6f} USDC")
            print(f"      Block: {transfer['block_number']}")
            print(f"      Hash: {transfer['tx_hash']}")
            print(f"      Time: {transfer['created_at']}")
        
        # 6. Check latest blocks
        print("\n6️⃣ BLOCKCHAIN SYNC STATUS:")
        latest_block = await conn.fetchval("""
            SELECT MAX(block_number) FROM transactions
            WHERE created_at >= NOW() - INTERVAL '1 hour'
        """)
        
        print(f"   Latest transaction block: {latest_block}")
        print(f"   User last scanned block: {user['last_scanned_block']}")
        
        if latest_block and user['last_scanned_block']:
            diff = latest_block - user['last_scanned_block']
            if diff > 100:
                print(f"   ⚠️ User is {diff} blocks behind!")
        
        # 7. Final diagnosis
        print("\n" + "=" * 80)
        print("📋 DIAGNOSIS:")
        print("=" * 80)
        
        issues = []
        
        if not found_001:
            issues.append("• 0.01 USDC withdrawal NOT found in transactions table")
            issues.append("  → The wallet_transfers might have it but not synced to transactions")
            
        if not found_20:
            issues.append("• 20 USDC deposit NOT found in recent transactions")
            issues.append("  → Check if it's in wallet_transfers but not in transactions")
            
        if abs(float(user['usdc_balance']) - expected_balance) > 0.001:
            issues.append(f"• Balance mismatch: Shows {user['usdc_balance']} but should be {expected_balance:.6f}")
            issues.append("  → The balance calculation might be out of sync")
            
        if float(user['usdc_balance']) == 0.01:
            issues.append("• Balance shows 0.01 USDC which doesn't account for recent activity")
            issues.append("  → Watcher might not be updating user balance correctly")
        
        if issues:
            print("\n🚨 ISSUES FOUND:")
            for issue in issues:
                print(issue)
        else:
            print("\n✅ No major issues found")
            
    finally:
        await conn.close()

if __name__ == "__main__":
    print("🔍 Starting investigation of balance and transaction issues...")
    asyncio.run(investigate())