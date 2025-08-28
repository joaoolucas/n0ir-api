#!/usr/bin/env python3
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from decimal import Decimal
from datetime import datetime

DATABASE_URL = 'postgresql+asyncpg://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway'

async def check_recent_transactions():
    engine = create_async_engine(DATABASE_URL)
    
    user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
    
    async with engine.begin() as conn:
        # Get all transactions in chronological order
        result = await conn.execute(text('''
            SELECT tx_type, event_data, created_at, status, tx_hash
            FROM transactions
            WHERE user_id = :user_id
            AND status = 'CONFIRMED'
            ORDER BY created_at DESC
            LIMIT 20
        '''), {'user_id': user_id})
        
        print(f'Recent transactions for {user_id}:\n')
        for tx_type, event_data, created_at, status, tx_hash in result:
            amount = Decimal(str(event_data.get('amount_usdc', 0))) if event_data else Decimal(0)
            usdc_returned = Decimal(str(event_data.get('usdc_returned', 0))) if event_data and event_data.get('usdc_returned') else Decimal(0)
            
            print(f'{created_at.strftime("%Y-%m-%d %H:%M:%S")} - {tx_type:20} Amount: {amount:12.6f} USDC')
            if usdc_returned > 0:
                print(f'{"":23}   └─ Returned: {usdc_returned:12.6f} USDC')
                print(f'{"":23}   └─ Net:      {amount - usdc_returned:12.6f} USDC')
            if tx_hash:
                print(f'{"":23}   └─ Hash: {tx_hash[:16]}...')
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_recent_transactions())
