#!/usr/bin/env python3
"""Comprehensive fix for USDC balance calculation issues."""

import asyncio
import asyncpg
from decimal import Decimal
from urllib.parse import urlparse
import json

# Database URL from Railway staging
DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def fix_balance():
    """Fix USDC balance calculation comprehensively."""
    
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
    print("=" * 80)
    
    try:
        # Focus on our test user
        user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
        
        # 1. Get all transactions for proper calculation
        print(f"\n📊 Analyzing transactions for user {user_id}...")
        
        # Get deposits and withdrawals (case-insensitive status check)
        deposits = await conn.fetch("""
            SELECT 
                tx_hash,
                block_number,
                event_data->>'amount_usdc' as amount,
                status
            FROM transactions 
            WHERE user_id = $1
            AND tx_type = 'DEPOSIT'
            AND UPPER(status) = 'CONFIRMED'
            ORDER BY block_number DESC NULLS LAST
        """, user_id)
        
        withdrawals = await conn.fetch("""
            SELECT 
                tx_hash,
                block_number,
                event_data->>'amount_usdc' as amount,
                status
            FROM transactions 
            WHERE user_id = $1
            AND tx_type = 'WITHDRAWAL'
            AND UPPER(status) = 'CONFIRMED'
            ORDER BY block_number DESC NULLS LAST
        """, user_id)
        
        # Calculate totals
        total_deposits = sum(Decimal(d['amount'] or '0') for d in deposits)
        total_withdrawals = sum(Decimal(w['amount'] or '0') for w in withdrawals)
        
        print(f"  Deposits: {len(deposits)} transactions, total: {total_deposits:.6f} USDC")
        print(f"  Withdrawals: {len(withdrawals)} transactions, total: {total_withdrawals:.6f} USDC")
        
        # Get position opens and closes
        position_opens = await conn.fetch("""
            SELECT 
                tx_hash,
                block_number,
                event_data->>'usdcIn' as usdc_in,
                event_data->>'tokenId' as token_id,
                status
            FROM transactions 
            WHERE user_id = $1
            AND tx_type = 'POSITION_CREATED'
            AND UPPER(status) = 'CONFIRMED'
            ORDER BY block_number DESC NULLS LAST
        """, user_id)
        
        position_closes = await conn.fetch("""
            SELECT 
                tx_hash,
                block_number,
                event_data->>'usdcOut' as usdc_out,
                event_data->>'tokenId' as token_id,
                event_data->>'aero_swap_usdc' as aero_swap,
                status
            FROM transactions 
            WHERE user_id = $1
            AND tx_type = 'POSITION_CLOSED'
            AND UPPER(status) = 'CONFIRMED'
            ORDER BY block_number DESC NULLS LAST
        """, user_id)
        
        # Calculate position totals (convert from wei to USDC)
        total_position_in = sum(Decimal(p['usdc_in'] or '0') / Decimal('1000000') for p in position_opens)
        total_position_out = sum(Decimal(p['usdc_out'] or '0') / Decimal('1000000') for p in position_closes)
        
        print(f"\n  Position Opens: {len(position_opens)} positions, total IN: {total_position_in:.6f} USDC")
        print(f"  Position Closes: {len(position_closes)} positions, total OUT: {total_position_out:.6f} USDC")
        
        # Get AERO swaps
        aero_swaps = await conn.fetch("""
            SELECT 
                tx_hash,
                block_number,
                event_data->>'amount_usdc' as amount,
                event_data->>'position_token_id' as token_id,
                status
            FROM transactions 
            WHERE user_id = $1
            AND tx_type = 'AERO_SWAP'
            AND UPPER(status) = 'CONFIRMED'
            ORDER BY block_number DESC NULLS LAST
        """, user_id)
        
        total_aero = sum(Decimal(a['amount'] or '0') for a in aero_swaps)
        print(f"\n  AERO Swaps: {len(aero_swaps)} swaps, total: {total_aero:.6f} USDC")
        
        # Calculate correct balance using the full formula
        # Balance = Deposits - Withdrawals - PositionsIN + PositionsOUT + AeroSwaps
        calculated_balance = total_deposits - total_withdrawals - total_position_in + total_position_out + total_aero
        
        print(f"\n💰 Balance Calculation:")
        print(f"  Deposits:        +{total_deposits:.6f} USDC")
        print(f"  Withdrawals:     -{total_withdrawals:.6f} USDC")
        print(f"  Positions IN:    -{total_position_in:.6f} USDC")
        print(f"  Positions OUT:   +{total_position_out:.6f} USDC")
        print(f"  AERO Swaps:      +{total_aero:.6f} USDC")
        print(f"  ─────────────────────────────────")
        print(f"  CALCULATED:      {calculated_balance:.6f} USDC")
        
        # Get current DB values
        user_record = await conn.fetchrow("""
            SELECT 
                cdp_wallet_address,
                usdc_balance,
                total_deposits_usdc,
                total_withdrawals_usdc
            FROM users 
            WHERE user_id = $1
        """, user_id)
        
        print(f"\n📊 Current Database Values:")
        print(f"  DB Balance: {user_record['usdc_balance']:.6f} USDC")
        print(f"  DB Deposits Total: {user_record['total_deposits_usdc']:.6f}")
        print(f"  DB Withdrawals Total: {user_record['total_withdrawals_usdc']:.6f}")
        
        # 2. Fix the totals and balance
        print(f"\n🔧 Fixing database values...")
        
        # Update the user record with correct values
        await conn.execute("""
            UPDATE users 
            SET 
                total_deposits_usdc = $2,
                total_withdrawals_usdc = $3,
                usdc_balance = $4
            WHERE user_id = $1
        """, user_id, float(total_deposits), float(total_withdrawals), float(calculated_balance))
        
        print(f"  ✅ Updated totals and balance")
        
        # 3. Fix any status inconsistencies (lowercase vs uppercase)
        print(f"\n🔧 Fixing transaction status inconsistencies...")
        
        result = await conn.execute("""
            UPDATE transactions 
            SET status = 'CONFIRMED'
            WHERE user_id = $1
            AND LOWER(status) = 'confirmed'
            AND status != 'CONFIRMED'
        """, user_id)
        
        count = int(result.split()[-1]) if result else 0
        if count > 0:
            print(f"  ✅ Fixed {count} transactions with lowercase status")
        else:
            print(f"  ✅ All transaction statuses already uppercase")
        
        # 4. Verify the fix
        print(f"\n✅ Verifying the fix...")
        
        updated_user = await conn.fetchrow("""
            SELECT 
                usdc_balance,
                total_deposits_usdc,
                total_withdrawals_usdc
            FROM users 
            WHERE user_id = $1
        """, user_id)
        
        print(f"\n📊 Updated Database Values:")
        print(f"  Balance: {updated_user['usdc_balance']:.6f} USDC")
        print(f"  Total Deposits: {updated_user['total_deposits_usdc']:.6f} USDC")
        print(f"  Total Withdrawals: {updated_user['total_withdrawals_usdc']:.6f} USDC")
        
        # Check against expected values
        if abs(Decimal(str(updated_user['usdc_balance'])) - calculated_balance) < Decimal('0.000001'):
            print(f"\n✅ Balance correctly set to {calculated_balance:.6f} USDC")
        else:
            print(f"\n⚠️ Balance mismatch! Expected {calculated_balance:.6f} but got {updated_user['usdc_balance']:.6f}")
        
        # 5. Ensure wallet monitor won't reset it
        print(f"\n🔧 Updating last_scanned_block to prevent immediate rescan...")
        
        # Get current block (approximate)
        max_block = await conn.fetchval("""
            SELECT MAX(block_number) 
            FROM transactions 
            WHERE user_id = $1
            AND block_number IS NOT NULL
        """, user_id)
        
        if max_block:
            await conn.execute("""
                UPDATE users 
                SET last_scanned_block = $2
                WHERE user_id = $1
            """, user_id, max_block)
            print(f"  ✅ Set last_scanned_block to {max_block}")
        
        print(f"\n✨ Comprehensive fix completed!")
        
        # Final check
        print(f"\n📊 FINAL CHECK:")
        final_user = await conn.fetchrow("""
            SELECT 
                usdc_balance,
                total_deposits_usdc,
                total_withdrawals_usdc,
                last_scanned_block
            FROM users 
            WHERE user_id = $1
        """, user_id)
        
        print(f"  Balance: {final_user['usdc_balance']:.6f} USDC")
        print(f"  Expected: {calculated_balance:.6f} USDC")
        print(f"  Match: {'YES ✅' if abs(Decimal(str(final_user['usdc_balance'])) - calculated_balance) < Decimal('0.000001') else 'NO ❌'}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise
    finally:
        await conn.close()
        print("\nDisconnected from database")


if __name__ == "__main__":
    print("🔧 Running comprehensive USDC balance fix")
    print("=" * 80)
    asyncio.run(fix_balance())