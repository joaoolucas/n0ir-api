#!/usr/bin/env python3
"""Find AERO swap events near position closes."""

import asyncio
import asyncpg
import json
from decimal import Decimal
from datetime import timedelta

DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def find_aero_swaps():
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        # Get all position closes
        closes = await conn.fetch("""
            SELECT 
                event_data,
                block_number,
                tx_hash,
                created_at
            FROM transactions 
            WHERE user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
            AND tx_type = 'POSITION_CLOSED'
            AND status = 'confirmed'
            ORDER BY block_number DESC
        """)
        
        print(f"Found {len(closes)} position closes\n")
        
        for close in closes:
            event_data = json.loads(close['event_data']) if isinstance(close['event_data'], str) else close['event_data']
            token_id = event_data.get('tokenId', 'Unknown')
            usdc_out = Decimal(str(event_data.get('usdcOut', 0))) / Decimal('1000000')
            block = close['block_number']
            
            print(f"Position {token_id} closed at block {block}")
            print(f"  USDC out: {usdc_out:.6f}")
            print(f"  TX: {close['tx_hash']}")
            
            # Look for transactions in surrounding blocks
            if block:
                nearby = await conn.fetch("""
                    SELECT 
                        tx_type,
                        block_number,
                        tx_hash,
                        event_data,
                        created_at
                    FROM transactions 
                    WHERE user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
                    AND block_number BETWEEN $1 AND $2
                    AND tx_hash != $3
                    ORDER BY block_number
                """, block - 2, block + 10, close['tx_hash'])
                
                if nearby:
                    print(f"  Transactions within -2/+10 blocks:")
                    for tx in nearby:
                        # Check if this could be an AERO swap
                        event_str = str(tx['event_data']).lower() if tx['event_data'] else ''
                        if 'aero' in event_str or 'swap' in tx['tx_type'].lower():
                            print(f"    🔄 POTENTIAL SWAP at block {tx['block_number']}: {tx['tx_type']}")
                        else:
                            print(f"    Block {tx['block_number']}: {tx['tx_type']}")
                        
                        # Show event data if interesting
                        if tx['event_data'] and ('amount' in event_str or 'usdc' in event_str):
                            print(f"      Data: {tx['event_data']}")
            
            print()
        
        # Also check for any orphaned transactions that might be swaps
        print("\nChecking for potential swap patterns in all transactions...")
        
        # Get all transactions for this user
        all_txs = await conn.fetch("""
            SELECT DISTINCT tx_hash, block_number
            FROM transactions 
            WHERE user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
            AND block_number IS NOT NULL
            ORDER BY block_number DESC
            LIMIT 100
        """)
        
        # Check on-chain data for these transactions to find swaps
        print(f"Found {len(all_txs)} unique transactions to analyze")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(find_aero_swaps())