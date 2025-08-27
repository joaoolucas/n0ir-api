#!/usr/bin/env python3
"""Mark existing deposits from router as AERO swaps."""

import asyncio
import asyncpg
import json
from decimal import Decimal

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"
AERO_SWAP_ROUTER = "0xa4fdd479eda160671636e2ecf8f993cbf86258a8"

async def mark_aero_swaps():
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
        
        print("🔍 Finding and marking AERO swaps...")
        print("=" * 60)
        
        # Find all deposits from the router address
        deposits = await conn.fetch("""
            SELECT 
                id,
                tx_hash,
                block_number,
                event_data
            FROM transactions 
            WHERE user_id = $1
            AND tx_type = 'DEPOSIT'
            AND event_data::text ILIKE $2
            ORDER BY block_number ASC
        """, user_id, f'%{AERO_SWAP_ROUTER}%')
        
        print(f"Found {len(deposits)} deposits from AERO swap router")
        
        total_aero = Decimal('0')
        for deposit in deposits:
            event_data = json.loads(deposit['event_data']) if isinstance(deposit['event_data'], str) else deposit['event_data']
            amount = Decimal(str(event_data.get('amount_usdc', 0)))
            total_aero += amount
            
            print(f"  Block {deposit['block_number']}: {amount:.6f} USDC (tx: {deposit['tx_hash'][:10]}...)")
            
            # Update to AERO_SWAP type
            await conn.execute("""
                UPDATE transactions 
                SET tx_type = 'AERO_SWAP'
                WHERE id = $1
            """, deposit['id'])
        
        print(f"\n✅ Marked {len(deposits)} transactions as AERO_SWAP")
        print(f"📊 Total AERO proceeds: {total_aero:.6f} USDC")
        
        # Now check the complete picture
        print("\n💰 Recalculating totals...")
        
        totals = await conn.fetchrow("""
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
        
        total_in = Decimal(str(totals['total_in'] or 0))
        total_out = Decimal(str(totals['total_out'] or 0))
        total_aero_check = Decimal(str(totals['total_aero'] or 0))
        
        print(f"  Money IN (positions): {total_in:.6f} USDC")
        print(f"  Money OUT (closes): {total_out:.6f} USDC")
        print(f"  AERO swaps: {total_aero_check:.6f} USDC")
        print(f"  ─────────────────────────")
        print(f"  Trading PnL: {(total_out + total_aero_check - total_in):+.6f} USDC")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(mark_aero_swaps())