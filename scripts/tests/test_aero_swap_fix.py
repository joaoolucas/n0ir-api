#!/usr/bin/env python3
"""Test AERO swap detection and PnL calculation fix."""

import asyncio
import asyncpg
import json
from decimal import Decimal

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def test_aero_swap_fix():
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
        
        print("🔍 Testing AERO swap detection and PnL calculation fix")
        print("=" * 60)
        
        # 1. Check for AERO_SWAP transactions
        aero_swaps = await conn.fetch("""
            SELECT 
                tx_hash,
                block_number,
                event_data,
                created_at
            FROM transactions 
            WHERE user_id = $1
            AND tx_type = 'AERO_SWAP'
            ORDER BY block_number DESC
        """, user_id)
        
        total_aero = Decimal('0')
        if aero_swaps:
            print(f"\n✅ Found {len(aero_swaps)} AERO_SWAP transactions:")
            for swap in aero_swaps:
                event_data = json.loads(swap['event_data']) if isinstance(swap['event_data'], str) else swap['event_data']
                amount = Decimal(str(event_data.get('amount_usdc', 0)))
                token_id = event_data.get('position_token_id', 'Unknown')
                total_aero += amount
                print(f"  Position {token_id}: {amount:.6f} USDC at block {swap['block_number']}")
        else:
            print("\n⚠️ No AERO_SWAP transactions found yet")
        
        print(f"\n📊 Total AERO swaps: {total_aero:.6f} USDC")
        
        # 2. Check position closes with AERO swap info
        position_closes = await conn.fetch("""
            SELECT 
                event_data,
                block_number,
                tx_hash
            FROM transactions 
            WHERE user_id = $1
            AND tx_type = 'POSITION_CLOSED'
            AND status IN ('CONFIRMED', 'confirmed')
            ORDER BY block_number DESC
        """, user_id)
        
        print(f"\n📈 Position closes with AERO tracking:")
        for close in position_closes:
            event_data = json.loads(close['event_data']) if isinstance(close['event_data'], str) else close['event_data']
            token_id = event_data.get('tokenId', 'Unknown')
            usdc_out = Decimal(str(event_data.get('usdcOut', 0))) / Decimal('1000000')
            aero_swap = Decimal(str(event_data.get('aero_swap_usdc', 0)))
            total_return = Decimal(str(event_data.get('total_return_usdc', 0)))
            
            print(f"\nPosition {token_id}:")
            print(f"  USDC from close: {usdc_out:.6f}")
            if aero_swap > 0:
                print(f"  AERO swap: {aero_swap:.6f}")
                print(f"  Total return: {total_return:.6f}")
            else:
                print(f"  AERO swap: Not tracked in event_data yet")
        
        # 3. Calculate complete PnL
        print("\n💰 Complete PnL Calculation:")
        
        # Get position opens and closes
        position_data = await conn.fetch("""
            SELECT 
                SUM(CASE WHEN tx_type = 'POSITION_CREATED' 
                    THEN CAST(event_data->>'usdcIn' AS NUMERIC) / 1000000 
                    ELSE 0 END) as total_in,
                SUM(CASE WHEN tx_type = 'POSITION_CLOSED' 
                    THEN CAST(event_data->>'usdcOut' AS NUMERIC) / 1000000 
                    ELSE 0 END) as total_out
            FROM transactions 
            WHERE user_id = $1
            AND tx_type IN ('POSITION_CREATED', 'POSITION_CLOSED')
            AND status IN ('CONFIRMED', 'confirmed')
        """, user_id)
        
        pos = position_data[0]
        total_in = Decimal(str(pos['total_in'] or 0))
        total_out = Decimal(str(pos['total_out'] or 0))
        
        print(f"  Money IN (positions): {total_in:.6f} USDC")
        print(f"  Money OUT (closes): {total_out:.6f} USDC")
        print(f"  AERO swaps: {total_aero:.6f} USDC")
        print(f"  ─────────────────────────")
        
        trading_pnl = total_out + total_aero - total_in
        print(f"  Trading PnL: {trading_pnl:+.6f} USDC")
        
        # 4. Check wallet balance
        user = await conn.fetchrow("""
            SELECT 
                usdc_balance, 
                total_deposits_usdc, 
                total_withdrawals_usdc,
                realized_pnl_usd,
                unrealized_pnl_usd
            FROM users 
            WHERE user_id = $1
        """, user_id)
        
        deposits = Decimal(str(user['total_deposits_usdc']))
        withdrawals = Decimal(str(user['total_withdrawals_usdc']))
        balance = Decimal(str(user['usdc_balance']))
        realized_pnl = Decimal(str(user['realized_pnl_usd'] or 0))
        unrealized_pnl = Decimal(str(user['unrealized_pnl_usd'] or 0))
        
        print(f"\n📊 User Statistics:")
        print(f"  Deposits: {deposits:.6f} USDC")
        print(f"  Withdrawals: {withdrawals:.6f} USDC")
        print(f"  Current balance: {balance:.6f} USDC")
        print(f"  Realized PnL (DB): {realized_pnl:.6f} USDC")
        print(f"  Unrealized PnL (DB): {unrealized_pnl:.6f} USDC")
        
        # Expected balance calculation
        expected = deposits - withdrawals - total_in + total_out + total_aero
        print(f"\n✅ Balance Verification:")
        print(f"  Expected: {expected:.6f} USDC")
        print(f"  Actual: {balance:.6f} USDC")
        print(f"  Match: {'YES ✓' if abs(expected - balance) < 0.01 else 'NO ✗'}")
        
        # Expected PnL
        expected_realized_pnl = (withdrawals - deposits) + trading_pnl
        print(f"\n✅ PnL Verification:")
        print(f"  Expected realized PnL: {expected_realized_pnl:.6f} USDC")
        print(f"  Actual realized PnL: {realized_pnl:.6f} USDC")
        print(f"  Match: {'YES ✓' if abs(expected_realized_pnl - realized_pnl) < 0.01 else 'NO ✗'}")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(test_aero_swap_fix())