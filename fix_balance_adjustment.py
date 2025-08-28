#!/usr/bin/env python3
"""
Fix balance discrepancy by adding an adjustment transaction.
This corrects for historical withdrawal calculation errors.
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from decimal import Decimal
from datetime import datetime
import uuid

DATABASE_URL = 'postgresql+asyncpg://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway'

async def fix_balance():
    engine = create_async_engine(DATABASE_URL)
    
    user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
    adjustment_amount = Decimal('0.036442')  # Amount to remove from balance
    
    async with engine.begin() as conn:
        # First, verify current balance
        result = await conn.execute(text('''
            WITH balance_calc AS (
                SELECT 
                    COALESCE(SUM(CASE 
                        WHEN tx_type = 'DEPOSIT' THEN CAST(event_data->>'amount_usdc' AS NUMERIC)
                        WHEN tx_type = 'POSITION_CLOSED' THEN CAST(event_data->>'amount_usdc' AS NUMERIC)
                        WHEN tx_type = 'AERO_SWAP' THEN CAST(event_data->>'amount_usdc' AS NUMERIC)
                        ELSE 0
                    END), 0) as credits,
                    COALESCE(SUM(CASE 
                        WHEN tx_type IN ('WITHDRAWAL', 'WITHDRAW') THEN CAST(event_data->>'amount_usdc' AS NUMERIC)
                        WHEN tx_type = 'POSITION_CREATED' THEN 
                            CAST(event_data->>'amount_usdc' AS NUMERIC) - 
                            COALESCE(CAST(event_data->>'usdc_returned' AS NUMERIC), 0)
                        ELSE 0
                    END), 0) as debits
                FROM transactions
                WHERE user_id = :user_id
                AND status = 'CONFIRMED'
            )
            SELECT credits - debits as balance FROM balance_calc
        '''), {'user_id': user_id})
        
        current_balance = result.scalar()
        print(f"Current balance: {current_balance} USDC")
        
        if abs(float(current_balance) - 0.058985) < 0.001:
            print(f"Balance matches expected 0.058985 USDC, proceeding with adjustment...")
            
            # Create adjustment transaction
            tx_id = str(uuid.uuid4())
            
            await conn.execute(text('''
                INSERT INTO transactions (
                    id,
                    user_id,
                    tx_type,
                    status,
                    event_data,
                    tx_hash,
                    created_at,
                    updated_at,
                    tx_metadata
                ) VALUES (
                    :id,
                    :user_id,
                    'WITHDRAWAL',
                    'CONFIRMED',
                    jsonb_build_object(
                        'amount_usdc', :amount,
                        'type', 'balance_adjustment',
                        'reason', 'Correction for historical withdrawal calculation error',
                        'note', 'Withdrawal was 49.777673 but should have been 49.741231 (0.036442 difference)'
                    ),
                    :tx_hash,
                    :created_at,
                    :created_at,
                    jsonb_build_object(
                        'adjustment', true,
                        'original_issue', 'withdrawal_calculation_error'
                    )
                )
            '''), {
                'id': tx_id,
                'user_id': user_id,
                'amount': float(adjustment_amount),
                'tx_hash': f'adjustment-{tx_id[:8]}',
                'created_at': datetime.utcnow()
            })
            
            print(f"✅ Added balance adjustment transaction: -{adjustment_amount} USDC")
            
            # Verify new balance
            result = await conn.execute(text('''
                WITH balance_calc AS (
                    SELECT 
                        COALESCE(SUM(CASE 
                            WHEN tx_type = 'DEPOSIT' THEN CAST(event_data->>'amount_usdc' AS NUMERIC)
                            WHEN tx_type = 'POSITION_CLOSED' THEN CAST(event_data->>'amount_usdc' AS NUMERIC)
                            WHEN tx_type = 'AERO_SWAP' THEN CAST(event_data->>'amount_usdc' AS NUMERIC)
                            ELSE 0
                        END), 0) as credits,
                        COALESCE(SUM(CASE 
                            WHEN tx_type IN ('WITHDRAWAL', 'WITHDRAW') THEN CAST(event_data->>'amount_usdc' AS NUMERIC)
                            WHEN tx_type = 'POSITION_CREATED' THEN 
                                CAST(event_data->>'amount_usdc' AS NUMERIC) - 
                                COALESCE(CAST(event_data->>'usdc_returned' AS NUMERIC), 0)
                            ELSE 0
                        END), 0) as debits
                    FROM transactions
                    WHERE user_id = :user_id
                    AND status = 'CONFIRMED'
                )
                SELECT credits - debits as balance FROM balance_calc
            '''), {'user_id': user_id})
            
            new_balance = result.scalar()
            print(f"New balance: {new_balance} USDC")
            print(f"Target balance: 0.022543 USDC")
            print(f"Match: {abs(float(new_balance) - 0.022543) < 0.001}")
        else:
            print(f"⚠️  Current balance {current_balance} doesn't match expected 0.058985")
            print("Skipping adjustment to avoid further issues")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(fix_balance())