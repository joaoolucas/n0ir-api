#!/usr/bin/env python3
"""Analyze deposit patterns after position closes - likely AERO swaps."""

import asyncio
import asyncpg
import json
from decimal import Decimal

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def analyze_deposits():
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        # Get position closes with nearby deposits
        results = await conn.fetch("""
            WITH position_closes AS (
                SELECT 
                    event_data,
                    block_number,
                    tx_hash,
                    created_at
                FROM transactions 
                WHERE user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
                AND tx_type = 'POSITION_CLOSED'
                AND status = 'confirmed'
                AND block_number IS NOT NULL
            ),
            nearby_deposits AS (
                SELECT 
                    d.event_data,
                    d.block_number,
                    d.tx_hash,
                    pc.block_number as close_block,
                    pc.event_data as close_data
                FROM transactions d
                JOIN position_closes pc ON d.block_number BETWEEN pc.block_number AND pc.block_number + 10
                WHERE d.user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
                AND d.tx_type = 'DEPOSIT'
                AND d.event_data::text LIKE '%0xa4fdd479eda160671636e2ecf8f993cbf86258a8%'
            )
            SELECT * FROM nearby_deposits
            ORDER BY close_block DESC
        """)
        
        print("🔍 Analysis of deposits after position closes:")
        print("=" * 60)
        
        total_aero_usdc = Decimal('0')
        
        for row in results:
            close_data = json.loads(row['close_data']) if isinstance(row['close_data'], str) else row['close_data']
            deposit_data = json.loads(row['event_data']) if isinstance(row['event_data'], str) else row['event_data']
            
            token_id = close_data.get('tokenId', 'Unknown')
            usdc_from_close = Decimal(str(close_data.get('usdcOut', 0))) / Decimal('1000000')
            usdc_from_deposit = Decimal(str(deposit_data.get('amount_usdc', 0)))
            
            print(f"\nPosition {token_id}:")
            print(f"  Close block: {row['close_block']}")
            print(f"  Deposit block: {row['block_number']} (+{row['block_number'] - row['close_block']} blocks)")
            print(f"  USDC from position close: {usdc_from_close:.6f}")
            print(f"  USDC from deposit (likely AERO swap): {usdc_from_deposit:.6f}")
            print(f"  Total return: {usdc_from_close + usdc_from_deposit:.6f}")
            
            total_aero_usdc += usdc_from_deposit
        
        print(f"\n📊 Summary:")
        print(f"Total USDC from suspected AERO swaps: {total_aero_usdc:.6f}")
        
        # Now calculate the corrected PnL
        position_data = await conn.fetch("""
            SELECT 
                SUM(CASE WHEN tx_type = 'POSITION_CREATED' 
                    THEN CAST(event_data->>'usdcIn' AS NUMERIC) / 1000000 
                    ELSE 0 END) as total_in,
                SUM(CASE WHEN tx_type = 'POSITION_CLOSED' 
                    THEN CAST(event_data->>'usdcOut' AS NUMERIC) / 1000000 
                    ELSE 0 END) as total_out
            FROM transactions 
            WHERE user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
            AND tx_type IN ('POSITION_CREATED', 'POSITION_CLOSED')
            AND status = 'confirmed'
        """)
        
        pos = position_data[0]
        total_in = Decimal(str(pos['total_in'] or 0))
        total_out = Decimal(str(pos['total_out'] or 0))
        
        print(f"\n💰 Complete PnL Calculation:")
        print(f"  Money IN to positions: {total_in:.6f} USDC")
        print(f"  Money OUT from closes: {total_out:.6f} USDC")
        print(f"  Money from AERO swaps: {total_aero_usdc:.6f} USDC")
        print(f"  ─────────────────────────────────")
        print(f"  Total OUT: {total_out + total_aero_usdc:.6f} USDC")
        print(f"  Real PnL: {(total_out + total_aero_usdc - total_in):+.6f} USDC")
        
        # Check wallet balance
        user = await conn.fetchrow("""
            SELECT usdc_balance, total_deposits_usdc, total_withdrawals_usdc
            FROM users 
            WHERE user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
        """)
        
        balance = Decimal(str(user['usdc_balance']))
        deposits = Decimal(str(user['total_deposits_usdc']))
        withdrawals = Decimal(str(user['total_withdrawals_usdc']))
        
        expected = deposits - withdrawals - total_in + total_out + total_aero_usdc
        
        print(f"\n✅ Verification:")
        print(f"  Expected balance: {expected:.6f} USDC")
        print(f"  Actual balance: {balance:.6f} USDC")
        print(f"  Match: {'YES ✓' if abs(expected - balance) < 0.01 else 'NO ✗'}")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(analyze_deposits())