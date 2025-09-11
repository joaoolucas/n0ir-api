#!/usr/bin/env python3
"""Backfill script to detect and record historical AERO swaps."""

import asyncio
import asyncpg
import json
from decimal import Decimal
from datetime import datetime

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

# Known AERO swap router address
AERO_SWAP_ROUTER = "0xa4fdd479eda160671636e2ecf8f993cbf86258a8"

async def backfill_aero_swaps():
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
        
        print("🔍 Backfilling AERO swaps...")
        print("=" * 60)
        
        # 1. Get all position closes
        position_closes = await conn.fetch("""
            SELECT 
                event_data,
                block_number,
                tx_hash,
                created_at
            FROM transactions 
            WHERE user_id = $1
            AND tx_type = 'POSITION_CLOSED'
            AND status IN ('CONFIRMED', 'confirmed')
            AND block_number IS NOT NULL
            ORDER BY block_number ASC
        """, user_id)
        
        print(f"Found {len(position_closes)} position closes to check")
        
        # 2. For each position close, look for AERO swap deposits
        aero_swaps_created = 0
        
        for close in position_closes:
            event_data = json.loads(close['event_data']) if isinstance(close['event_data'], str) else close['event_data']
            token_id = event_data.get('tokenId', 'Unknown')
            usdc_out = Decimal(str(event_data.get('usdcOut', 0))) / Decimal('1000000')
            close_block = close['block_number']
            
            if not close_block:
                continue
                
            print(f"\nChecking position {token_id} closed at block {close_block}")
            
            # Look for deposits from router within 20 blocks
            deposits = await conn.fetch("""
                SELECT 
                    tx_hash,
                    block_number,
                    event_data,
                    created_at
                FROM transactions 
                WHERE user_id = $1
                AND tx_type = 'DEPOSIT'
                AND block_number BETWEEN $2 AND $3
                AND event_data::text ILIKE $4
                ORDER BY block_number ASC
            """, user_id, close_block, close_block + 20, f'%{AERO_SWAP_ROUTER}%')
            
            if deposits:
                for deposit in deposits:
                    deposit_data = json.loads(deposit['event_data']) if isinstance(deposit['event_data'], str) else deposit['event_data']
                    amount_usdc = Decimal(str(deposit_data.get('amount_usdc', 0)))
                    
                    print(f"  Found AERO swap: {amount_usdc:.6f} USDC at block {deposit['block_number']}")
                    
                    # Check if AERO_SWAP transaction already exists
                    existing = await conn.fetchrow("""
                        SELECT id FROM transactions 
                        WHERE tx_hash = $1 AND tx_type = 'AERO_SWAP'
                    """, deposit['tx_hash'])
                    
                    if not existing:
                        # Create AERO_SWAP transaction
                        await conn.execute("""
                            INSERT INTO transactions (
                                user_id, tx_hash, tx_type, status, block_number, 
                                event_data
                            ) VALUES ($1, $2, $3, $4, $5, $6)
                        """, user_id, deposit['tx_hash'], 'AERO_SWAP', 'CONFIRMED',
                            deposit['block_number'],
                            json.dumps({
                                'position_token_id': str(token_id),
                                'amount_usdc': float(amount_usdc),
                                'from_router': AERO_SWAP_ROUTER,
                                'blocks_after_close': deposit['block_number'] - close_block
                            }))
                        
                        aero_swaps_created += 1
                        print(f"    ✅ Created AERO_SWAP transaction")
                    
                    # Update the position close with AERO swap info
                    updated_close_data = event_data.copy()
                    updated_close_data['aero_swap_usdc'] = float(amount_usdc)
                    updated_close_data['total_return_usdc'] = float(usdc_out) + float(amount_usdc)
                    
                    await conn.execute("""
                        UPDATE transactions 
                        SET event_data = $1
                        WHERE tx_hash = $2 AND tx_type = 'POSITION_CLOSED'
                    """, json.dumps(updated_close_data), close['tx_hash'])
                    
                    print(f"    ✅ Updated position close with total return: {updated_close_data['total_return_usdc']:.6f} USDC")
        
        print(f"\n📊 Summary:")
        print(f"  Created {aero_swaps_created} AERO_SWAP transactions")
        
        # 3. Recalculate user PnL
        print("\n💰 Recalculating user PnL with AERO swaps...")
        
        # Get totals
        position_data = await conn.fetch("""
            SELECT 
                SUM(CASE WHEN tx_type = 'POSITION_CREATED' 
                    THEN CAST(event_data->>'usdcIn' AS NUMERIC) / 1000000 
                    ELSE 0 END) as total_in,
                SUM(CASE WHEN tx_type = 'POSITION_CLOSED' 
                    THEN CAST(event_data->>'usdcOut' AS NUMERIC) / 1000000 
                    ELSE 0 END) as total_out,
                SUM(CASE WHEN tx_type = 'AERO_SWAP' 
                    THEN CAST(event_data->>'amount_usdc' AS NUMERIC) 
                    ELSE 0 END) as total_aero
            FROM transactions 
            WHERE user_id = $1
            AND tx_type IN ('POSITION_CREATED', 'POSITION_CLOSED', 'AERO_SWAP')
            AND status IN ('CONFIRMED', 'confirmed')
        """, user_id)
        
        pos = position_data[0]
        total_in = Decimal(str(pos['total_in'] or 0))
        total_out = Decimal(str(pos['total_out'] or 0))
        total_aero = Decimal(str(pos['total_aero'] or 0))
        
        print(f"  Money IN (positions): {total_in:.6f} USDC")
        print(f"  Money OUT (closes): {total_out:.6f} USDC")
        print(f"  AERO swaps: {total_aero:.6f} USDC")
        
        trading_pnl = total_out + total_aero - total_in
        print(f"  Trading PnL: {trading_pnl:+.6f} USDC")
        
        # Get wallet totals
        user = await conn.fetchrow("""
            SELECT total_deposits_usdc, total_withdrawals_usdc
            FROM users WHERE user_id = $1
        """, user_id)
        
        deposits = Decimal(str(user['total_deposits_usdc']))
        withdrawals = Decimal(str(user['total_withdrawals_usdc']))
        
        # Calculate realized PnL
        realized_pnl = (withdrawals - deposits) + trading_pnl
        
        # Update user PnL
        await conn.execute("""
            UPDATE users 
            SET realized_pnl_usd = $1
            WHERE user_id = $2
        """, float(realized_pnl), user_id)
        
        print(f"\n✅ Updated user realized PnL to: {realized_pnl:.6f} USDC")
        
        # Verify balance
        expected_balance = deposits - withdrawals - total_in + total_out + total_aero
        print(f"\n📊 Expected balance: {expected_balance:.6f} USDC")
        
    finally:
        await conn.close()
        print("\n✅ Backfill complete")

if __name__ == "__main__":
    asyncio.run(backfill_aero_swaps())