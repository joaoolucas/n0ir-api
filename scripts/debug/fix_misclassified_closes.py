#!/usr/bin/env python3
"""Fix misclassified position closes that were recorded as withdrawals."""

import asyncio
from decimal import Decimal
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

DATABASE_URL = 'postgresql+asyncpg://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway'

async def fix_misclassified_closes():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
        
        print("Fixing misclassified position closes...")
        
        # 1. Fix the withdrawal that's actually position 24001518 close
        tx_hash = '8b775ed8bca8fd0714ca60fb2af1c83e96f1efaee1e946c014c5c45b1c95f5e5'
        
        # Update transaction type and add token ID
        result = await conn.execute(text('''
            UPDATE transactions
            SET tx_type = 'POSITION_CLOSED',
                event_data = jsonb_set(
                    COALESCE(event_data, '{}'::jsonb),
                    '{tokenId}',
                    '"24001518"'::jsonb
                )
            WHERE tx_hash = :tx_hash
            AND tx_type = 'WITHDRAWAL'
            RETURNING tx_hash, event_data
        '''), {'tx_hash': tx_hash})
        
        updated = result.fetchone()
        if updated:
            print(f"✅ Fixed transaction {tx_hash[:10]}...")
            print(f"   Changed WITHDRAWAL -> POSITION_CLOSED for token 24001518")
        else:
            print(f"⚠️  Transaction {tx_hash[:10]}... already fixed or not found")
        
        # 2. Update position 24001518 with close details
        await conn.execute(text('''
            UPDATE positions
            SET closed_at = '2025-08-29 15:20:29',
                exit_tx_hash = :tx_hash,
                exit_date = '2025-08-29 15:20:29'
            WHERE token_id = 24001518
        '''), {'tx_hash': tx_hash})
        
        print("✅ Updated position 24001518 with close details")
        
        # 3. Recalculate user balance
        result = await conn.execute(text('''
            SELECT 
                SUM(CASE
                    WHEN tx_type = 'DEPOSIT' THEN CAST(event_data->>'amount_usdc' AS NUMERIC)
                    WHEN tx_type = 'POSITION_CLOSED' THEN CAST(event_data->>'amount_usdc' AS NUMERIC)
                    WHEN tx_type = 'AERO_SWAP' THEN CAST(event_data->>'amount_usdc' AS NUMERIC)
                    WHEN tx_type IN ('WITHDRAWAL', 'WITHDRAW') THEN -CAST(event_data->>'amount_usdc' AS NUMERIC)
                    WHEN tx_type = 'POSITION_CREATED' THEN 
                        -(CAST(event_data->>'amount_usdc' AS NUMERIC) - 
                          COALESCE(CAST(event_data->>'usdc_returned' AS NUMERIC), 0))
                    ELSE 0
                END) as calculated_balance
            FROM transactions
            WHERE user_id = :user_id
            AND status = 'CONFIRMED'
        '''), {'user_id': user_id})
        
        new_balance = result.fetchone()[0] or Decimal(0)
        
        # Update user balance
        await conn.execute(text('''
            UPDATE users
            SET usdc_balance = :balance
            WHERE user_id = :user_id
        '''), {'balance': float(new_balance), 'user_id': user_id})
        
        print(f"\n✅ Updated user balance to: {new_balance:.6f} USDC")
        
        # 4. Verify the fix
        result = await conn.execute(text('''
            SELECT usdc_balance, total_deposits_usdc, total_withdrawals_usdc
            FROM users
            WHERE user_id = :user_id
        '''), {'user_id': user_id})
        
        user = result.fetchone()
        print(f"\nFinal state:")
        print(f"  Balance: {user[0]} USDC")
        print(f"  Total Deposits: {user[1]} USDC")
        print(f"  Total Withdrawals: {user[2]} USDC")
    
    await engine.dispose()
    print("\n✅ Fix complete!")

if __name__ == "__main__":
    asyncio.run(fix_misclassified_closes())