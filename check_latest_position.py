#!/usr/bin/env python3
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from web3 import Web3
from decimal import Decimal

DATABASE_URL = 'postgresql+asyncpg://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway'
RPC_URL = 'https://base-mainnet.g.alchemy.com/v2/L6lYa5sOH4CajbU6t7pp5'

async def check_latest_position():
    engine = create_async_engine(DATABASE_URL)
    
    web3 = Web3(Web3.HTTPProvider(RPC_URL))
    USDC_ADDRESS = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'
    TRANSFER_TOPIC = web3.keccak(text='Transfer(address,address,uint256)').hex()
    
    async with engine.begin() as conn:
        # Get the transaction hash for the latest position
        result = await conn.execute(text('''
            SELECT tx_hash, event_data
            FROM transactions
            WHERE tx_type = 'POSITION_CREATED'
            AND event_data->>'tokenId' = '23896392'
        '''))
        
        row = result.fetchone()
        if row:
            tx_hash = row[0]
            event_data = row[1]
            print(f'Checking transaction: {tx_hash}')
            print(f'Current amount_usdc: {event_data.get("amount_usdc")}')
            print()
            
            # Check for USDC returns
            receipt = web3.eth.get_transaction_receipt(tx_hash)
            smart_wallet = '0xa449F944aD033D8083564556Fd918C45B716f79c'.lower()
            
            returned_amount = Decimal(0)
            for log in receipt.logs:
                if (log['address'].lower() == USDC_ADDRESS.lower() and 
                    len(log['topics']) > 0 and 
                    log['topics'][0].hex() == TRANSFER_TOPIC):
                    
                    if len(log['topics']) >= 3:
                        to_address = '0x' + log['topics'][2].hex()[-40:]
                        
                        if to_address.lower() == smart_wallet:
                            from_address = '0x' + log['topics'][1].hex()[-40:]
                            
                            if from_address.lower() != smart_wallet:
                                amount_raw = int(log['data'].hex(), 16) if log['data'] else 0
                                amount_usdc = Decimal(amount_raw) / Decimal(1e6)
                                returned_amount += amount_usdc
                                print(f'Found USDC return: {amount_usdc} USDC')
            
            if returned_amount > 0:
                net_amount = Decimal(str(event_data.get('amount_usdc', 0))) - returned_amount
                print(f'\nTotal returned: {returned_amount} USDC')
                print(f'Net position cost: {net_amount} USDC')
                
                # Update the transaction
                await conn.execute(text('''
                    UPDATE transactions
                    SET event_data = event_data || 
                        jsonb_build_object(
                            'usdc_returned', CAST(:returned AS NUMERIC)
                        )
                    WHERE tx_hash = :tx_hash
                '''), {'returned': float(returned_amount), 'tx_hash': tx_hash})
                print('\n✅ Updated transaction with usdc_returned')
            else:
                print('No USDC returns found')
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_latest_position())