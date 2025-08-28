#!/usr/bin/env python3
"""
Recalculate POSITION_CREATED amounts to account for USDC returns.
This fixes historical transactions that were processed before the fix.
"""

import asyncio
from decimal import Decimal
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from web3 import Web3
import aiohttp
import json

DATABASE_URL = "postgresql+asyncpg://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"
RPC_URL = "https://base-mainnet.g.alchemy.com/v2/L6lYa5sOH4CajbU6t7pp5"
USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # Base USDC

web3 = Web3(Web3.HTTPProvider(RPC_URL))
TRANSFER_TOPIC = web3.keccak(text="Transfer(address,address,uint256)").hex()

async def get_usdc_returned_in_tx(tx_hash: str, user_address: str) -> Decimal:
    """Check for USDC return transfers in the same transaction."""
    try:
        receipt = web3.eth.get_transaction_receipt(tx_hash)
        returned_amount = Decimal(0)
        
        for log in receipt.logs:
            # Check if this is a USDC Transfer event
            if (log['address'].lower() == USDC_ADDRESS.lower() and 
                len(log['topics']) > 0 and 
                log['topics'][0].hex() == TRANSFER_TOPIC):
                
                if len(log['topics']) >= 3:
                    # Get the 'to' address (remove padding)
                    to_address = '0x' + log['topics'][2].hex()[-40:]
                    
                    # Check if this transfer is TO the user
                    if to_address.lower() == user_address.lower():
                        # Get the 'from' address
                        from_address = '0x' + log['topics'][1].hex()[-40:]
                        
                        # If it's not FROM the user (i.e., it's a return)
                        if from_address.lower() != user_address.lower():
                            # Parse amount from data
                            amount_raw = int(log['data'].hex(), 16) if log['data'] else 0
                            amount_usdc = Decimal(amount_raw) / Decimal(1e6)
                            returned_amount += amount_usdc
                            print(f"    Found USDC return: {amount_usdc} USDC")
        
        return returned_amount
        
    except Exception as e:
        print(f"    Error checking tx {tx_hash}: {e}")
        return Decimal(0)

async def recalculate_positions():
    engine = create_async_engine(DATABASE_URL)
    
    async with engine.begin() as conn:
        # First get the smart wallet address for the user
        user_result = await conn.execute(text("""
            SELECT cdp_wallet_address
            FROM users
            WHERE user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
        """))
        smart_wallet = user_result.fetchone()[0]
        print(f"User smart wallet: {smart_wallet}\n")
        
        # Get all POSITION_CREATED transactions
        result = await conn.execute(text("""
            SELECT id, user_id, tx_hash, event_data
            FROM transactions
            WHERE tx_type = 'POSITION_CREATED'
            AND user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
            ORDER BY created_at
        """))
        
        transactions = result.fetchall()
        print(f"Found {len(transactions)} POSITION_CREATED transactions to check\n")
        
        total_correction = Decimal(0)
        updates = []
        
        for tx_id, user_id, tx_hash, event_data in transactions:
            current_amount = Decimal(str(event_data.get('amount_usdc', 0)))
            print(f"Checking tx {tx_hash[:10]}...")
            print(f"  Current amount: {current_amount} USDC")
            
            # Check for USDC returns to the smart wallet
            returned = await get_usdc_returned_in_tx(tx_hash, smart_wallet)
            
            if returned > 0:
                # Calculate net amount
                net_amount = current_amount - returned
                print(f"  Net amount: {net_amount} USDC (returned {returned})")
                
                # Prepare update
                updates.append({
                    'id': tx_id,
                    'net_amount': float(net_amount),
                    'returned': float(returned)
                })
                
                total_correction += returned
            else:
                print(f"  No returns found")
            print()
        
        # Apply updates
        if updates:
            print(f"\nApplying corrections for {len(updates)} transactions...")
            for update in updates:
                # Update event_data with correct amount
                await conn.execute(text("""
                    UPDATE transactions
                    SET event_data = event_data || 
                        jsonb_build_object(
                            'amount_usdc', CAST(:net_amount AS NUMERIC),
                            'usdc_returned', CAST(:returned AS NUMERIC)
                        )
                    WHERE id = :id
                """), update)
            
            print(f"✅ Updated {len(updates)} transactions")
            print(f"Total correction: {total_correction} USDC")
        else:
            print("No corrections needed")
        
        # Verify new balance
        print("\n📊 Verifying new balance...")
        result = await conn.execute(text("""
            SELECT 
                SUM(CASE WHEN tx_type = 'DEPOSIT' THEN CAST(event_data->>'amount_usdc' as DECIMAL) ELSE 0 END) as deposits,
                SUM(CASE WHEN tx_type IN ('WITHDRAWAL','WITHDRAW') THEN CAST(event_data->>'amount_usdc' as DECIMAL) ELSE 0 END) as withdrawals,
                SUM(CASE WHEN tx_type = 'POSITION_CREATED' THEN CAST(event_data->>'amount_usdc' as DECIMAL) ELSE 0 END) as pos_created,
                SUM(CASE WHEN tx_type = 'POSITION_CLOSED' THEN CAST(event_data->>'amount_usdc' as DECIMAL) ELSE 0 END) as pos_closed,
                SUM(CASE WHEN tx_type = 'AERO_SWAP' THEN CAST(event_data->>'amount_usdc' as DECIMAL) ELSE 0 END) as aero
            FROM transactions 
            WHERE user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
        """))
        
        row = result.fetchone()
        deposits = row[0] or 0
        withdrawals = row[1] or 0
        pos_created = row[2] or 0
        pos_closed = row[3] or 0
        aero = row[4] or 0
        
        balance = Decimal(str(deposits)) + Decimal(str(pos_closed)) + Decimal(str(aero)) - Decimal(str(pos_created)) - Decimal(str(withdrawals))
        
        print(f"Deposits:         +{deposits}")
        print(f"Position Closed:  +{pos_closed}")
        print(f"AERO Swaps:       +{aero}")
        print(f"Position Created: -{pos_created}")
        print(f"Withdrawals:      -{withdrawals}")
        print(f"\n💰 New Balance: {balance} USDC")
        
        if abs(balance) < Decimal('0.01'):
            print("✅ Balance successfully corrected to ~0!")
        else:
            print(f"⚠️  Balance is still off by {balance}")
    
    await engine.dispose()

if __name__ == "__main__":
    print("🔄 Recalculating POSITION_CREATED amounts...\n")
    asyncio.run(recalculate_positions())