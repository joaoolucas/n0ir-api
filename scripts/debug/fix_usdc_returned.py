#!/usr/bin/env python3
"""
Fix missing usdc_returned values in POSITION_CREATED transactions.
This script recalculates the USDC returned amount for all positions
and updates both transactions and positions tables.
"""

import asyncio
import os
from decimal import Decimal
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL").replace("postgresql://", "postgresql+asyncpg://")
RPC_URL = os.getenv("RPC_URL", "https://base-mainnet.g.alchemy.com/v2/your-api-key")

USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # Base USDC

web3 = Web3(Web3.HTTPProvider(RPC_URL))
TRANSFER_TOPIC = web3.keccak(text="Transfer(address,address,uint256)").hex()


async def get_usdc_returned_in_tx(tx_hash: str, cdp_wallet_address: str) -> float:
    """Check for USDC return transfers in the same transaction."""
    try:
        # Get the transaction receipt
        receipt = web3.eth.get_transaction_receipt(tx_hash)
        if not receipt or 'logs' not in receipt:
            return 0
        
        returned_amount = 0
        
        # Look for Transfer events in the logs
        for log in receipt['logs']:
            # Check if this is a USDC Transfer event
            if (log.get('address', '').lower() == USDC_ADDRESS.lower() and 
                len(log.get('topics', [])) > 0 and 
                log['topics'][0].hex() == TRANSFER_TOPIC):
                
                # Parse the Transfer event
                if len(log['topics']) >= 3:
                    # Get the 'to' address (remove padding)
                    to_address = '0x' + log['topics'][2].hex()[-40:]
                    
                    # Check if this transfer is TO the user's CDP wallet
                    if to_address.lower() == cdp_wallet_address.lower():
                        # Parse amount from data
                        amount_raw = int(log['data'].hex(), 16) if log['data'] else 0
                        amount_usdc = amount_raw / 1e6  # USDC has 6 decimals
                        returned_amount += amount_usdc
                        print(f"  Found return: {amount_usdc:.6f} USDC to {to_address[:10]}...")
        
        return returned_amount
    except Exception as e:
        print(f"  Error checking tx {tx_hash}: {e}")
        return 0


async def fix_missing_usdc_returned():
    """Main function to fix missing usdc_returned values."""
    engine = create_async_engine(DATABASE_URL)
    
    async with engine.begin() as conn:
        # Find all POSITION_CREATED transactions missing usdc_returned
        result = await conn.execute(text("""
            SELECT 
                t.transaction_id::text,
                t.tx_hash, 
                t.user_id,
                t.event_data,
                COALESCE(CAST(t.event_data->>'amount_usdc' AS NUMERIC), 0) as amount_usdc,
                u.cdp_wallet_address
            FROM transactions t
            JOIN users u ON t.user_id = u.user_id
            WHERE t.transaction_type = 'POSITION_CREATED'
            AND t.tx_hash IS NOT NULL
            AND t.tx_hash != ''
            AND (
                NOT (t.event_data ? 'usdc_returned')
                OR CAST(t.event_data->>'usdc_returned' AS NUMERIC) = 0
            )
            ORDER BY t.created_at DESC
            LIMIT 50
        """))
        
        transactions = result.fetchall()
        print(f"Found {len(transactions)} POSITION_CREATED transactions to check")
        
        fixed_count = 0
        total_returned = Decimal(0)
        
        for tx in transactions:
            tx_id, tx_hash, user_id, event_data, amount_usdc, cdp_wallet = tx
            
            print(f"\nChecking tx {tx_hash[:10]}... for user {user_id}")
            print(f"  CDP wallet: {cdp_wallet}")
            print(f"  Amount USDC: {amount_usdc}")
            
            # Get USDC returned amount
            returned = await get_usdc_returned_in_tx(tx_hash, cdp_wallet)
            
            if returned > 0:
                print(f"  ✅ Found USDC returned: {returned:.6f}")
                
                # Update transaction event_data
                await conn.execute(text("""
                    UPDATE transactions 
                    SET event_data = jsonb_set(
                        event_data,
                        '{usdc_returned}',
                        :returned::text::jsonb
                    )
                    WHERE transaction_id = :tx_id::uuid
                """), {
                    'returned': str(returned),
                    'tx_id': tx_id
                })
                
                # Also update the position's entry_amount_usdc if needed
                token_id = event_data.get('tokenId')
                if token_id:
                    # Calculate correct entry amount
                    correct_entry_amount = float(amount_usdc) - returned
                    
                    await conn.execute(text("""
                        UPDATE positions
                        SET entry_amount_usdc = :entry_amount
                        WHERE token_id = :token_id
                    """), {
                        'entry_amount': correct_entry_amount,
                        'token_id': int(token_id)
                    })
                    
                    print(f"  Updated position {token_id} entry amount to {correct_entry_amount:.6f}")
                
                fixed_count += 1
                total_returned += Decimal(str(returned))
            else:
                print(f"  No USDC returned found")
        
        print(f"\n{'='*60}")
        print(f"Summary:")
        print(f"  Fixed {fixed_count} transactions")
        print(f"  Total USDC returned found: {total_returned:.6f}")
        print(f"  Average return per position: {(total_returned/fixed_count if fixed_count > 0 else 0):.6f}")
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(fix_missing_usdc_returned())