#!/usr/bin/env python3
"""
Fix misclassified AERO swap transaction.
Updates the DEPOSIT to AERO_SWAP and links it to the POSITION_CLOSED.
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

DATABASE_URL = 'postgresql+asyncpg://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway'

async def fix_aero_swap():
    engine = create_async_engine(DATABASE_URL)
    
    async with engine.begin() as conn:
        print("Fixing misclassified AERO swap...")
        
        # 1. Update the misclassified DEPOSIT to AERO_SWAP
        result = await conn.execute(text('''
            UPDATE transactions 
            SET tx_type = 'AERO_SWAP',
                event_data = jsonb_set(
                    jsonb_set(
                        event_data,
                        '{position_token_id}',
                        '"23896392"'
                    ),
                    '{from_router}',
                    '"0xa4fdd479eda160671636e2ecf8f993cbf86258a8"'
                )
            WHERE tx_hash = '0xfb517dc0c503f5936f3e62dd76aecae40c509899b4f2e7f5f0de22057f4a6118'
            RETURNING tx_hash, tx_type, event_data
        '''))
        
        row = result.fetchone()
        if row:
            print(f"✅ Updated transaction to AERO_SWAP")
            print(f"   tx_hash: {row[0]}")
            print(f"   tx_type: {row[1]}")
        else:
            print("⚠️  Transaction not found or already updated")
        
        # 2. Update the POSITION_CLOSED to include aero_swap_usdc
        result = await conn.execute(text('''
            UPDATE transactions 
            SET event_data = jsonb_set(
                event_data,
                '{aero_swap_usdc}',
                '0.064046'
            )
            WHERE tx_hash = '0x7873a086ac7d1643f4367aaccff63733f275289f9faa0d771b82e688eaca31a1'
            RETURNING tx_hash, event_data->>'aero_swap_usdc' as aero_amount
        '''))
        
        row = result.fetchone()
        if row:
            print(f"✅ Updated POSITION_CLOSED with aero_swap_usdc")
            print(f"   tx_hash: {row[0]}")
            print(f"   aero_swap_usdc: {row[1]}")
        else:
            print("⚠️  POSITION_CLOSED transaction not found")
        
        # 3. Verify the fix
        print("\nVerifying the fix...")
        
        # Check AERO_SWAP
        result = await conn.execute(text('''
            SELECT tx_type, event_data
            FROM transactions
            WHERE tx_hash = '0xfb517dc0c503f5936f3e62dd76aecae40c509899b4f2e7f5f0de22057f4a6118'
        '''))
        
        row = result.fetchone()
        if row:
            print(f"AERO_SWAP transaction:")
            print(f"  Type: {row[0]}")
            print(f"  Position token ID: {row[1].get('position_token_id')}")
            print(f"  Amount: {row[1].get('amount_usdc')} USDC")
        
        # Check POSITION_CLOSED
        result = await conn.execute(text('''
            SELECT 
                event_data->>'amount_usdc' as position_value,
                event_data->>'aero_swap_usdc' as aero_value
            FROM transactions
            WHERE tx_hash = '0x7873a086ac7d1643f4367aaccff63733f275289f9faa0d771b82e688eaca31a1'
        '''))
        
        row = result.fetchone()
        if row:
            position_value = float(row[0] or 0)
            aero_value = float(row[1] or 0)
            total = position_value + aero_value
            print(f"\nPOSITION_CLOSED totals:")
            print(f"  Position value: {position_value:.6f} USDC")
            print(f"  AERO swap value: {aero_value:.6f} USDC")
            print(f"  Total returned: {total:.6f} USDC")
    
    await engine.dispose()
    print("\n✅ Fix complete!")

if __name__ == "__main__":
    asyncio.run(fix_aero_swap())