#!/usr/bin/env python3
"""Fix the 0.01 USDC withdrawal amount in the database."""

import asyncio
import asyncpg
from datetime import datetime
from decimal import Decimal

# Database URL from Railway staging
DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def fix_withdrawal_amount():
    """Fix the withdrawal amount for the recent 0.01 USDC transaction."""
    
    # Connect to database
    conn = await asyncpg.connect(DATABASE_URL, ssl='require')
    
    try:
        # Find the withdrawal at block 34768586
        tx = await conn.fetchrow("""
            SELECT id, tx_hash, event_data, user_id, block_number
            FROM transactions
            WHERE block_number = 34768586
            AND tx_type = 'WITHDRAWAL'
            LIMIT 1
        """)
        
        if tx:
            print(f"Found withdrawal transaction:")
            print(f"  Hash: {tx['tx_hash']}")
            print(f"  User: {tx['user_id']}")
            print(f"  Block: {tx['block_number']}")
            print(f"  Current event_data: {tx['event_data']}")
            
            # Update the event_data to include the proper amount
            # 0.01 USDC = 10000 in 6-decimal format
            updated_event_data = tx['event_data'] or {}
            updated_event_data['usdc_out'] = '10000'  # 0.01 USDC in 6 decimal format
            updated_event_data['amount_usdc'] = 0.01
            
            await conn.execute("""
                UPDATE transactions
                SET event_data = $1
                WHERE id = $2
            """, updated_event_data, tx['id'])
            
            print(f"\n✅ Updated event_data with withdrawal amount: 0.01 USDC")
            
            # Verify the update
            updated = await conn.fetchrow("""
                SELECT event_data
                FROM transactions
                WHERE id = $1
            """, tx['id'])
            
            print(f"  New event_data: {updated['event_data']}")
        else:
            print("❌ Could not find the withdrawal transaction at block 34768586")
            
            # Check if there are any other recent withdrawals
            recent = await conn.fetch("""
                SELECT tx_hash, block_number, event_data, created_at
                FROM transactions
                WHERE tx_type = 'WITHDRAWAL'
                AND created_at >= CURRENT_TIMESTAMP - INTERVAL '2 hours'
                ORDER BY created_at DESC
                LIMIT 5
            """)
            
            print("\nRecent withdrawals:")
            for r in recent:
                print(f"  - Block {r['block_number']}: {r['tx_hash']}")
                print(f"    Data: {r['event_data']}")
                
    finally:
        await conn.close()

if __name__ == "__main__":
    print("🔧 Fixing 0.01 USDC withdrawal amount in database")
    asyncio.run(fix_withdrawal_amount())