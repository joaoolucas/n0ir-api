#!/usr/bin/env python3
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from decimal import Decimal

DATABASE_URL = 'postgresql+asyncpg://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway'

async def test_balance():
    engine = create_async_engine(DATABASE_URL)
    
    user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
    
    async with engine.begin() as conn:
        # Get all confirmed transactions
        result = await conn.execute(text('''
            SELECT tx_type, event_data
            FROM transactions
            WHERE user_id = :user_id
            AND status = 'CONFIRMED'
        '''), {'user_id': user_id})
        
        deposits = Decimal(0)
        withdrawals = Decimal(0)
        position_created = Decimal(0)
        position_closed = Decimal(0)
        aero_swaps = Decimal(0)
        
        for tx_type, event_data in result:
            amount = Decimal(str(event_data.get('amount_usdc', 0))) if event_data else Decimal(0)
            
            if tx_type == 'DEPOSIT':
                deposits += amount
            elif tx_type in ['WITHDRAWAL', 'WITHDRAW']:
                withdrawals += amount
            elif tx_type == 'POSITION_CREATED':
                # Account for USDC returns
                usdc_returned = Decimal(str(event_data.get('usdc_returned', 0))) if event_data and event_data.get('usdc_returned') else Decimal(0)
                net_amount = amount - usdc_returned
                position_created += net_amount
            elif tx_type == 'POSITION_CLOSED':
                position_closed += amount
            elif tx_type == 'AERO_SWAP':
                aero_swaps += amount
        
        # Calculate balance
        balance = deposits + position_closed + aero_swaps - withdrawals - position_created
        
        print(f'Balance calculation for {user_id}:')
        print(f'  Deposits:         +{deposits}')
        print(f'  Position Closed:  +{position_closed}')
        print(f'  AERO Swaps:       +{aero_swaps}')
        print(f'  Position Created: -{position_created}')
        print(f'  Withdrawals:      -{withdrawals}')
        print(f'')
        print(f'  Available Balance: {balance} USDC')
        
        # Get active position info
        result = await conn.execute(text('''
            SELECT t.event_data
            FROM transactions t
            WHERE t.tx_type = 'POSITION_CREATED'
            AND t.event_data->>'tokenId' = '23896392'
            AND t.user_id = :user_id
        '''), {'user_id': user_id})
        
        active_position = result.fetchone()
        if active_position:
            event_data = active_position[0]
            amount = Decimal(str(event_data.get('amount_usdc', 0)))
            returned = Decimal(str(event_data.get('usdc_returned', 0))) if event_data.get('usdc_returned') else Decimal(0)
            net = amount - returned
            print(f'')
            print(f'  Active Position:')
            print(f'    Amount sent:    {amount}')
            print(f'    USDC returned:  {returned}')
            print(f'    Net invested:   {net}')
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(test_balance())